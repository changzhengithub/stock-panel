#!/usr/bin/env python3
"""Project launcher. Use the backend virtualenv's Python to run this file."""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.settings import data_provider, token

parser = argparse.ArgumentParser()
parser.add_argument(
    "mode",
    choices=[
        "dev",
        "serve",
        "sync",
        "bootstrap",
        "doctor",
        "backfill",
        "sync-leaders",
        "sync-concepts",
        "backup",
        "migrate",
    ],
)
args, extra = parser.parse_known_args()
os.chdir(ROOT)
if args.mode not in ("dev", "serve"):
    raise SystemExit(subprocess.call([sys.executable, "-m", "app.cli", args.mode, *extra]))
subprocess.run([sys.executable, "-m", "app.cli", "migrate"], check=True)
if args.mode == "serve" and not (ROOT / "frontend/dist/index.html").exists():
    raise SystemExit("请先运行 npm --prefix frontend run build")
children = []
if data_provider() == "free" or token():
    # The job has a process lock; it cannot overlap the scheduled sync.
    children.append(subprocess.Popen([sys.executable, "-m", "app.cli", "sync"]))
else:
    print("未配置 TUSHARE_TOKEN；已启动网页，配置后运行 doctor 与 bootstrap。", flush=True)
children.append(
    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            *(["--reload"] if args.mode == "dev" else []),
        ]
    )
)
if args.mode == "dev":
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("找不到 npm")
    children.append(subprocess.Popen([npm, "--prefix", "frontend", "run", "dev"]))
print("访问 http://127.0.0.1:" + ("5173" if args.mode == "dev" else "8000"), flush=True)
try:
    while children[-1].poll() is None:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    for child in children:
        if child.poll() is None:
            child.terminate()
    for child in children:
        try:
            child.wait(timeout=8)
        except subprocess.TimeoutExpired:
            child.kill()
