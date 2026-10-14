"""Release deployment with opt-in rehearsed migrations and code-only rollback."""

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
import tempfile
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


def guard_schema(previous, candidate, migrate=False):
    old, new = schema_files(previous), schema_files(candidate)
    changed = sorted(name for name in old.keys() | new.keys() if old.get(name) != new.get(name))
    if changed:
        print("数据库相关文件变更：\n  " + "\n  ".join(changed), flush=True)
    if changed and not migrate:
        raise RuntimeError(
            "检测到数据库迁移。尚未切换版本，旧版继续服务。需要迁移时使用 ./deploy/update.sh --migrate。"
        )
    if migrate:
        # Add revisions and register new metadata; never rewrite deployed history.
        rewritten = [
            name
            for name in old
            if old[name] != new.get(name) and name != "backend/migrations/env.py"
        ]
        if rewritten:
            raise RuntimeError("不支持重写已部署的迁移/启动逻辑：" + ", ".join(rewritten))


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


def migration_plan(candidate, db):
    with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as source:
        current = [row[0] for row in source.execute("SELECT version_num FROM alembic_version")]
    script = (
        "import json,sys; from alembic.config import Config; from alembic.script import ScriptDirectory; "
        "c=Config(); c.set_main_option('script_location','backend/migrations'); "
        "s=ScriptDirectory.from_config(c); old=json.loads(sys.argv[1]); "
        "assert len(old)==1 and len(s.get_heads())==1, 'Only linear migrations supported'; "
        "pending=list(s.iterate_revisions('heads', tuple(old))); "
        "print(json.dumps([r.revision for r in reversed(pending)]))"
    )
    result = run(
        [candidate / "backend/.venv/bin/python", "-c", script, json.dumps(current)],
        cwd=candidate,
        capture_output=True,
        text=True,
    )
    pending = json.loads(result.stdout)
    print(f"数据库版本：{','.join(current)}；待执行迁移：{', '.join(pending) or '无'}", flush=True)
    return pending


def run_migration(candidate, db):
    account = pwd.getpwnam("stockpanel")
    credentials = (
        {"user": account.pw_uid, "group": account.pw_gid, "extra_groups": []}
        if os.geteuid() != account.pw_uid
        else {}
    )
    # Only schema work: do not start HTTP handlers or background data workers.
    run(
        [candidate / "backend/.venv/bin/python", "-c", "from app.db import migrate; migrate()"],
        cwd=candidate,
        env={
            "PATH": "/usr/bin:/bin",
            "TZ": "Asia/Shanghai",
            "PYTHONPATH": str(candidate / "backend"),
            "STOCK_DB_PATH": str(db),
            "DATA_PROVIDER": "free",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        **credentials,
    )


def check_integrity(db):
    with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as source:
        if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("迁移后数据库完整性检查失败")
        if source.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError("迁移后数据库外键检查失败")


def rehearse_migration(candidate, db):
    print("在独立数据库副本上演练迁移，旧站继续服务……", flush=True)
    account = pwd.getpwnam("stockpanel")
    with tempfile.TemporaryDirectory(prefix=".migration-", dir=DATA) as directory:
        work = Path(directory)
        os.chown(work, account.pw_uid, account.pw_gid)
        snapshot = work / "rehearsal.sqlite3"
        backup_database(db, snapshot)
        os.chown(snapshot, account.pw_uid, account.pw_gid)
        run_migration(candidate, snapshot)
        guard_database(candidate, snapshot)
        check_integrity(snapshot)
    print("数据库副本迁移与完整性检查通过。", flush=True)


def activate_with_migration(previous, candidate, db, backup):
    state_file = candidate / "migration-state.json"
    state = {
        "previous": str(previous),
        "candidate": str(candidate),
        "backup": str(backup),
        "database": str(db),
        "state": "stopping",
    }

    def record(status):
        state["state"] = status
        state_file.write_text(json.dumps(state, indent=2) + "\n")

    record("stopping")
    try:
        systemctl("stop", SERVICE)
        # Final backup after all application workers have stopped.
        backup_database(db, backup)
        record("migrating")
        run_migration(candidate, db)
        guard_database(candidate, db)
        check_integrity(db)
        record("starting")
        switch(candidate)
        systemctl("start", SERVICE)
        health(candidate)
        record("healthy")
    except BaseException:
        systemctl("stop", SERVICE)
        print(
            f"迁移发布失败：网站与同步定时器保持停止，不自动回退数据库或启动旧版。"
            f"\n检查 {state_file} 及备份 {backup}（若备份步骤失败，文件可能不存在或不完整）。"
            "\n恢复前请保留当前数据库与 WAL 文件，并核对迁移进度。",
            flush=True,
        )
        raise


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


def deploy(release, archive, digest, migrate=False):
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
    if shutil.disk_usage(BASE).free < archive.stat().st_size * 4 + db.stat().st_size * 4 + 1024**3:
        raise RuntimeError("可用空间不足：需容纳新环境、数据库备份并预留至少 1 GB")
    candidate = BASE / "releases" / release
    extract(archive, candidate, digest)
    guard_schema(previous, candidate, migrate=migrate)
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
    guard_database(previous if migrate else candidate, db)
    needs_migration = bool(migration_plan(candidate, db)) if migrate else False
    if needs_migration:
        rehearse_migration(candidate, db)
    timer_was_active = active(TIMER) == "active"
    resume_timer = True
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
            guard_database(previous if needs_migration else candidate, db)
            backup = DATA / "backups" / f"before-update-{release}.sqlite3"
            print(f"切换 {previous.name} -> {candidate.name}……", flush=True)
            if needs_migration:
                resume_timer = False
                activate_with_migration(previous, candidate, db, backup)
                resume_timer = True
            else:
                backup_database(db, backup)
                activate(previous, candidate)
    finally:
        if timer_was_active and resume_timer:
            systemctl("start", TIMER)
    (candidate / "deployment.json").write_text(
        json.dumps(
            {
                "release": release,
                "previous": str(previous),
                "backup": str(backup),
                "sha256": digest,
                "migrated": needs_migration,
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
    parser.add_argument("--migrate", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{8}", args.release) or not re.fullmatch(
        r"[0-9a-f]{64}", args.sha256
    ):
        parser.error("无效发布编号或校验值")

    def interrupted(signum, frame):
        raise RuntimeError(f"更新被信号 {signum} 中断")

    signal.signal(signal.SIGTERM, interrupted)
    with exclusive(BASE / ".update.lock"):
        deploy(args.release, args.archive.resolve(strict=True), args.sha256, migrate=args.migrate)


if __name__ == "__main__":
    main()
