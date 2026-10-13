#!/usr/bin/env python3
"""Generate a plist to stdout; never installs a system task."""

import plistlib
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
plist = {
    "Label": "local.stock-panel.sync",
    "ProgramArguments": [
        str(root / "backend/.venv/bin/python"),
        str(root / "scripts/run.py"),
        "sync",
    ],
    "WorkingDirectory": str(root),
    "StartCalendarInterval": {"Hour": 18, "Minute": 30},
    "EnvironmentVariables": {"TZ": "Asia/Shanghai"},
    "StandardOutPath": str(root / "data/sync.log"),
    "StandardErrorPath": str(root / "data/sync-error.log"),
}
sys.stdout.buffer.write(plistlib.dumps(plist))
