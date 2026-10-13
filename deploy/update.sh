#!/usr/bin/env bash
# Run from any directory. Passwords are entered directly into SSH, never saved.
set -euo pipefail
exec python3 "$(cd -- "$(dirname -- "$0")" && pwd)/update.py" "$@"
