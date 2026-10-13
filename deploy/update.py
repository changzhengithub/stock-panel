"""Build and publish a code-only release to the existing Guanshi installation."""

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {"__pycache__", ".venv", ".pytest_cache", ".ruff_cache", "node_modules", "tests"}


def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def package(root, output):
    """Explicit allowlist: never ship .env, a local database, or SSH credentials."""
    sources = [
        "backend/app",
        "backend/migrations",
        "backend/pyproject.toml",
        "backend/uv.lock",
        "backend/alembic.ini",
        "scripts",
        "config",
        "frontend/dist",
        "deploy",
        "README.md",
    ]
    with tarfile.open(output, "w:gz") as archive:
        for name in sources:
            source = root / name
            if not source.exists():
                raise RuntimeError(f"缺少发布文件：{source}")
            for path in sorted(source.rglob("*")) if source.is_dir() else [source]:
                relative = path.relative_to(root)
                if any(part in EXCLUDED or part.startswith(".") for part in relative.parts):
                    continue
                if path.is_symlink():
                    raise RuntimeError(f"发布包不接受软链接：{relative}")
                if path.is_file():
                    if path.suffix in {".sqlite3", ".sqlite", ".db", ".pem", ".key", ".pyc"}:
                        raise RuntimeError(f"发布目录含不应上传的文件：{relative}")
                    archive.add(path, arcname=str(relative), recursive=False)
    return hashlib.sha256(output.read_bytes()).hexdigest()


class SSH:
    def __init__(self, args, socket):
        self.host = args.host
        self.options = [
            "-p",
            str(args.port),
            "-o",
            "ConnectTimeout=15",
            "-o",
            "ServerAliveInterval=15",
            "-o",
            "ServerAliveCountMax=3",
            "-o",
            "StrictHostKeyChecking=ask",
            "-S",
            str(socket),
        ]
        if args.identity:
            self.options += [
                "-i",
                str(Path(args.identity).expanduser()),
                "-o",
                "IdentitiesOnly=yes",
            ]

    def connect(self):
        # A single interactive authentication; later uploads use the same connection.
        run(["ssh", *self.options, "-M", "-o", "ControlPersist=3600", "-fN", self.host])

    def command(self, args, **kwargs):
        return run(
            [
                "ssh",
                *self.options,
                "-o",
                "BatchMode=yes",
                self.host,
                shlex.join([str(x) for x in args]),
            ],
            **kwargs,
        )

    def close(self):
        subprocess.run(
            ["ssh", *self.options, "-O", "exit", self.host],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def publish(ssh, directory, release, digest):
    unit = f"stock-panel-update-{release}"
    remote = f"/var/lib/stock-panel-deploy/{release}"
    log = f"/var/log/{unit}.log"
    print(f"发布编号：{release}\n服务器日志：{log}", flush=True)
    # Root-owned staging avoids changing the script/archive while the unit runs.
    ssh.command(["sudo", "-n", "install", "-d", "-m", "700", remote])
    for source, name in [
        (directory / "app.tar.gz", "app.tar.gz"),
        (ROOT / "deploy/update_server.py", "update_server.py"),
    ]:
        with source.open("rb") as stream:
            ssh.command(
                ["sudo", "-n", "tee", f"{remote}/{name}"], stdin=stream, stdout=subprocess.DEVNULL
            )
    ssh.command(
        [
            "sudo",
            "-n",
            "systemd-run",
            "--no-block",
            f"--unit={unit}",
            "--property=Type=oneshot",
            "--property=RemainAfterExit=yes",
            "--property=TimeoutStartSec=30min",
            "--property=TimeoutStopSec=120",
            "--property=KillMode=mixed",
            f"--property=StandardOutput=append:{log}",
            "--property=StandardError=inherit",
            "/usr/bin/python3",
            "-u",
            f"{remote}/update_server.py",
            "--release",
            release,
            "--archive",
            f"{remote}/app.tar.gz",
            "--sha256",
            digest,
        ]
    )
    print("服务器正在安装并检查新版本；SSH 断开后服务器任务仍会继续。", flush=True)
    try:
        for attempt in range(400):
            result = ssh.command(
                [
                    "sudo",
                    "-n",
                    "systemctl",
                    "show",
                    unit,
                    "-p",
                    "ActiveState",
                    "-p",
                    "SubState",
                    "-p",
                    "Result",
                ],
                capture_output=True,
                text=True,
            )
            state = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
            if state.get("SubState") == "exited" and state.get("Result") == "success":
                break
            if state.get("ActiveState") == "failed" or (
                state.get("ActiveState") == "inactive" and attempt >= 3
            ):
                raise RuntimeError("服务器更新失败，请查看以下日志确认是否已恢复旧版本。")
            if attempt % 6 == 0:
                ssh.command(["sudo", "-n", "tail", "-n", "4", log])
            time.sleep(5)
        else:
            raise RuntimeError("等待超时；服务器任务可能仍在执行，请先检查日志，勿重复发布。")
    finally:
        print(
            f"可重新 SSH 登录后执行：sudo journalctl -u {unit}；sudo tail -n 80 {log}", flush=True
        )
        ssh.command(["sudo", "-n", "tail", "-n", "40", log])


def main():
    parser = argparse.ArgumentParser(
        description="更新观市：构建、备份、切换、验证；保留线上数据和 HTTPS。"
    )
    parser.add_argument("--host", default="ubuntu@43.129.204.116", help="SSH 用户@地址或 SSH 别名")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--identity", help="可选 SSH 私钥路径；不传时使用 SSH 配置/密钥或密码")
    parser.add_argument(
        "--prepare-only", action="store_true", help="仅测试、构建和打包，不连接服务器"
    )
    parser.add_argument(
        "--check", action="store_true", help="只验证 SSH、免密 sudo 和现有服务，不发布"
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.@-]+", args.host) or args.host.startswith("-"):
        parser.error("host 只能是 SSH 别名或 用户@主机名/IPv4")
    if not 1 <= args.port <= 65535 or (args.prepare_only and args.check):
        parser.error("端口无效或 --prepare-only 与 --check 冲突")
    release = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid4().hex[:8]
    with tempfile.TemporaryDirectory(prefix="stock-update-") as temporary:
        # macOS ControlPath has a short Unix socket path limit.
        ssh = SSH(args, Path(temporary) / "ssh")
        try:
            if not args.prepare_only:
                ssh.connect()
                ssh.command(["sudo", "-n", "test", "-L", "/opt/stock-panel/current"])
                ssh.command(["sudo", "-n", "systemctl", "is-active", "stock-panel.service"])
            if args.check:
                print("SSH、免密 sudo 与现有网站服务检查通过，未修改部署。")
                return
            print("安装锁定依赖并运行测试、生产构建……", flush=True)
            run([sys.executable, "-m", "unittest", "discover", "-s", ROOT / "deploy/tests", "-q"])
            run(["uv", "sync", "--project", ROOT / "backend", "--python", "3.12", "--locked"])
            run(
                [ROOT / "backend/.venv/bin/python", "-m", "pytest", ROOT / "backend/tests", "-q"],
                cwd=ROOT,
            )
            run(["npm", "--prefix", ROOT / "frontend", "ci"])
            run(["npm", "--prefix", ROOT / "frontend", "run", "test:unit"])
            run(["npm", "--prefix", ROOT / "frontend", "run", "build"])
            directory = ROOT / "deploy-artifacts" / release
            directory.mkdir(parents=True, mode=0o700)
            digest = package(ROOT, directory / "app.tar.gz")
            (directory / "manifest.json").write_text(
                json.dumps(
                    {
                        "release": release,
                        "sha256": digest,
                        "database_included": False,
                    },
                    indent=2,
                )
                + "\n"
            )
            print(f"发布包已生成：{directory}", flush=True)
            if args.prepare_only:
                return
            publish(ssh, directory, release, digest)
            try:
                with urllib.request.urlopen("https://guanshi.shop/", timeout=20) as response:
                    if response.read() != (ROOT / "frontend/dist/index.html").read_bytes():
                        raise RuntimeError("公网首页与本次构建不一致")
                with urllib.request.urlopen(
                    "https://guanshi.shop/api/data-status", timeout=20
                ) as response:
                    if not isinstance(json.load(response), dict):
                        raise RuntimeError("公网 API 返回格式错误")
            except Exception as error:
                raise RuntimeError(
                    f"服务器更新已完成，但公网验证未通过（未自动回退）：{error}"
                ) from error
            print("更新完成，公网首页与 API 验证通过：https://guanshi.shop")
        finally:
            if not args.prepare_only:
                ssh.close()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, OSError) as error:
        print(f"更新未完成：{error}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("本地已中断。如果服务器发布任务已启动，请先查看发布日志确认结果。", file=sys.stderr)
        sys.exit(130)
