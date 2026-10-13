"""Code-only update transaction, executed by a detached systemd unit as root.

Database migrations are deliberately rejected: a code rollback must not require
overwriting production data. Existing installation/configuration stays intact.
"""

import argparse
import fcntl
import hashlib
import json
import os
import pwd
import re
import shutil
import signal
import sqlite3
import subprocess
import tarfile
import time
import urllib.request
from contextlib import closing, contextmanager
from pathlib import Path, PurePosixPath

BASE = Path("/opt/stock-panel")
DATA = Path("/var/lib/stock-panel")
ENV_FILE = Path("/etc/stock-panel.env")
SERVICE = "stock-panel.service"
TIMER = "stock-panel-sync.timer"


def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def systemctl(*args):
    return run(["systemctl", *args], capture_output=True, text=True).stdout.strip()


def active(unit):
    return systemctl("show", unit, "-p", "ActiveState", "--value")


@contextmanager
def exclusive(path):
    with path.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(f"任务正在运行，未切换版本；请稍后重试：{path.name}") from error
        yield


def extract(archive, destination, digest):
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        raise RuntimeError("上传包 SHA256 校验失败")
    with tarfile.open(archive, "r:gz") as source:
        members = source.getmembers()
        names = set()
        for member in members:
            path = PurePosixPath(member.name)
            allowed = path.parts and path.parts[0] in {
                "backend",
                "scripts",
                "config",
                "frontend",
                "deploy",
                "README.md",
            }
            if (
                not allowed
                or path.is_absolute()
                or ".." in path.parts
                or any(part.startswith(".") for part in path.parts)
                or not member.isfile()
                or member.name in names
                or path.suffix in {".sqlite3", ".sqlite", ".db", ".pem", ".key", ".pyc"}
            ):
                raise RuntimeError(f"拒绝不安全的发布包条目：{member.name}")
            names.add(member.name)
        destination.mkdir(mode=0o755)  # refuse to overwrite any existing release
        for member in members:
            target = destination / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.extractfile(member) as reader, target.open("xb") as writer:
                shutil.copyfileobj(reader, writer)
            target.chmod(0o755 if member.mode & 0o111 else 0o644)


def schema_files(release):
    files = [release / "backend/alembic.ini", release / "backend/app/db.py"]
    files += sorted((release / "backend/migrations").rglob("*.py"))
    if not (release / "backend/migrations/versions").is_dir():
        raise RuntimeError("发布包缺少数据库迁移目录")
    return {
        str(path.relative_to(release)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files
    }


def guard_schema(previous, candidate):
    if schema_files(previous) != schema_files(candidate):
        raise RuntimeError(
            "检测到数据库迁移或启动迁移逻辑变化。快速更新已停止，旧版继续服务；请安排单独的迁移部署。"
        )


def guard_database(candidate, db):
    script = (
        "import json; from alembic.config import Config; "
        "from alembic.script import ScriptDirectory; "
        "c=Config(); c.set_main_option('script_location','backend/migrations'); "
        "print(json.dumps(ScriptDirectory.from_config(c).get_heads()))"
    )
    result = run(
        [candidate / "backend/.venv/bin/python", "-c", script],
        cwd=candidate,
        capture_output=True,
        text=True,
    )
    with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as source:
        revisions = {row[0] for row in source.execute("SELECT version_num FROM alembic_version")}
    if revisions != set(json.loads(result.stdout)):
        raise RuntimeError("线上数据库版本与发布代码不一致，拒绝自动迁移。")


def configure_cache(candidate):
    packages = list(
        (candidate / "backend/.venv/lib").glob("python*/site-packages/pytdxdata/servers.json")
    )
    if len(packages) != 1:
        raise RuntimeError("pytdxdata 缓存路径发生变化，请检查新依赖。")
    cache = DATA / "tdx-servers.json"
    account = pwd.getpwnam("stockpanel")
    if not cache.exists():
        shutil.copyfile(packages[0], cache)
    os.chown(cache, account.pw_uid, account.pw_gid)
    cache.chmod(0o600)
    link = packages[0].with_name("servers.update-link")
    link.symlink_to(cache)
    os.replace(link, packages[0])  # replace directory entry, not uv's shared hardlink contents


def backup_database(db, destination):
    with destination.open("xb"):
        pass
    destination.chmod(0o600)
    with (
        closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as source,
        closing(sqlite3.connect(destination)) as target,
    ):
        source.backup(target)
        if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("更新前数据库备份完整性检查失败")
    print(f"更新前备份：{destination}", flush=True)


def switch(release):
    link = BASE / f".current-{os.getpid()}"
    link.symlink_to(release)
    try:
        os.replace(link, BASE / "current")
    finally:
        link.unlink(missing_ok=True)


def health(release, timeout=60):
    expected = (release / "frontend/dist/index.html").read_bytes()
    assets = re.findall(rb'(?:src|href)="(/assets/[^"?]+)', expected)
    if not assets:
        raise RuntimeError("前端入口没有生产资源引用")
    last_error = None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if active(SERVICE) != "active":
                raise RuntimeError("网站服务尚未启动")
            with urllib.request.urlopen("http://127.0.0.1:8000/", timeout=5) as response:
                if response.read() != expected:
                    raise RuntimeError("首页不是预期版本")
            with urllib.request.urlopen(
                "http://127.0.0.1:8000/api/data-status", timeout=5
            ) as response:
                if not isinstance(json.load(response), dict):
                    raise RuntimeError("API 返回格式错误")
            for asset in assets:
                with urllib.request.urlopen(
                    "http://127.0.0.1:8000" + asset.decode(), timeout=5
                ) as response:
                    if (
                        response.read()
                        != (release / "frontend/dist" / asset.decode().lstrip("/")).read_bytes()
                    ):
                        raise RuntimeError("前端资源与预期版本不一致")
            return
        except Exception as error:
            last_error = error
            time.sleep(2)
    raise RuntimeError(f"健康检查失败：{last_error}")


def activate(previous, candidate):
    """With unchanged schema, restore only code on failure; never restore the DB."""
    touched = False
    try:
        touched = True
        systemctl("stop", SERVICE)
        switch(candidate)
        systemctl("start", SERVICE)
        health(candidate)
    except BaseException:
        if touched:
            print("新版本未通过检查，正在恢复上一版……", flush=True)
            systemctl("stop", SERVICE)
            switch(previous)
            systemctl("reset-failed", SERVICE)
            systemctl("start", SERVICE)
            health(previous)
            print(f"已恢复并验证上一版：{previous.name}；数据库未覆盖。", flush=True)
        raise


def deploy(release, archive, digest):
    if os.geteuid() != 0:
        raise RuntimeError("请由更新脚本通过 sudo 启动服务器任务")
    os.umask(0o022)
    if not (BASE / "current").is_symlink():
        raise RuntimeError("未检测到现有部署，不能使用更新脚本首次安装")
    previous = (BASE / "current").resolve(strict=True)
    if previous.parent != BASE / "releases" or active(SERVICE) != "active":
        raise RuntimeError("现有发布路径或服务状态异常，请先修复旧版本")
    database_setting = [
        line.partition("=")[2].strip().strip("\"'")
        for line in ENV_FILE.read_text().splitlines()
        if line.startswith("STOCK_DB_PATH=")
    ]
    db = DATA / "stock-panel.sqlite3"
    if database_setting != [str(db)] or not db.is_file():
        raise RuntimeError("数据库配置与已知部署路径不一致，拒绝继续")
    if shutil.disk_usage(BASE).free < archive.stat().st_size * 4 + db.stat().st_size * 2 + 1024**3:
        raise RuntimeError("可用空间不足：需容纳新环境、数据库备份并预留至少 1 GB")
    candidate = BASE / "releases" / release
    extract(archive, candidate, digest)
    guard_schema(previous, candidate)
    print("安装新版本依赖（旧网站继续运行）……", flush=True)
    run(
        [
            BASE / "bin/uv",
            "sync",
            "--project",
            candidate / "backend",
            "--python",
            "3.12",
            "--locked",
            "--no-dev",
        ],
        env={
            **os.environ,
            "UV_PYTHON_INSTALL_DIR": str(BASE / "python"),
            "UV_CACHE_DIR": str(BASE / "uv-cache"),
        },
    )
    configure_cache(candidate)
    guard_database(candidate, db)
    timer_was_active = active(TIMER) == "active"
    try:
        if timer_was_active:
            systemctl("stop", TIMER)
        if active("stock-panel-sync.service") in {"active", "activating", "deactivating"}:
            raise RuntimeError("行情同步正在运行，未切换版本，请在同步结束后重试。")
        lock_path = db.with_suffix(".sync.lock")
        # Existing lock must retain the app account's ability to open it for writing.
        if not lock_path.exists():
            lock_path.touch(mode=0o600)
            account = pwd.getpwnam("stockpanel")
            os.chown(lock_path, account.pw_uid, account.pw_gid)
        with exclusive(lock_path):
            guard_database(candidate, db)
            backup = DATA / "backups" / f"before-update-{release}.sqlite3"
            backup_database(db, backup)
            print(f"切换 {previous.name} -> {candidate.name}……", flush=True)
            activate(previous, candidate)
    finally:
        if timer_was_active:
            systemctl("start", TIMER)
    (candidate / "deployment.json").write_text(
        json.dumps(
            {
                "release": release,
                "previous": str(previous),
                "backup": str(backup),
                "sha256": digest,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"更新成功：{release}；本机首页、静态资源与 API 检查通过。", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{8}", args.release) or not re.fullmatch(
        r"[0-9a-f]{64}", args.sha256
    ):
        parser.error("无效发布编号或校验值")

    def interrupted(signum, frame):
        raise RuntimeError(f"更新被信号 {signum} 中断")

    signal.signal(signal.SIGTERM, interrupted)
    with exclusive(BASE / ".update.lock"):
        deploy(args.release, args.archive.resolve(strict=True), args.sha256)


if __name__ == "__main__":
    main()
