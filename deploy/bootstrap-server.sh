#!/usr/bin/env bash
# First installation only. Run as root after uploading the three verified artifacts.
set -euo pipefail
release=20261013-140313
base=/opt/stock-panel
source_dir=/home/ubuntu
test ! -e "$base/current"
test ! -e /etc/systemd/system/stock-panel.service
python3 - "$source_dir" <<'PY'
import hashlib, json, pathlib, sys
p = pathlib.Path(sys.argv[1])
manifest = json.loads((p / 'manifest.json').read_text())
for name, info in manifest['files'].items():
    with (p / name).open('rb') as f:
        assert hashlib.file_digest(f, 'sha256').hexdigest() == info['sha256'], name
print('Uploaded artifacts verified')
PY
if ! id stockpanel >/dev/null 2>&1; then
    useradd --system --user-group --home-dir /var/lib/stock-panel --shell /usr/sbin/nologin stockpanel
fi
install -d -m 755 "$base/releases/$release" "$base/bin" "$base/python" "$base/uv-cache"
install -d -o stockpanel -g stockpanel -m 750 /var/lib/stock-panel /var/lib/stock-panel/backups
test ! -e /var/lib/stock-panel/stock-panel.sqlite3
install -o stockpanel -g stockpanel -m 600 "$source_dir/stock-panel.sqlite3" /var/lib/stock-panel/stock-panel.sqlite3
tar -xzf "$source_dir/guanshi-app.tar.gz" -C "$base/releases/$release"
curl -fsSL https://astral.sh/uv/install.sh -o "$base/uv-install.sh"
UV_INSTALL_DIR="$base/bin" UV_NO_MODIFY_PATH=1 sh "$base/uv-install.sh"
export UV_PYTHON_INSTALL_DIR="$base/python" UV_CACHE_DIR="$base/uv-cache"
"$base/bin/uv" sync --project "$base/releases/$release/backend" --python 3.12 --locked --no-dev
ln -s "$base/releases/$release" "$base/current"
cat > /etc/stock-panel.env <<'EOF'
DATA_PROVIDER=free
STOCK_DB_PATH=/var/lib/stock-panel/stock-panel.sqlite3
FREE_MIN_INTERVAL=0.35
TZ=Asia/Shanghai
PYTHONUNBUFFERED=1
EOF
chown root:stockpanel /etc/stock-panel.env
chmod 640 /etc/stock-panel.env
cat > /etc/systemd/system/stock-panel.service <<'EOF'
[Unit]
Description=Guanshi stock market browser
After=network.target

[Service]
User=stockpanel
Group=stockpanel
WorkingDirectory=/opt/stock-panel/current
EnvironmentFile=/etc/stock-panel.env
ExecStart=/opt/stock-panel/current/backend/.venv/bin/python -m uvicorn app.main:app --app-dir /opt/stock-panel/current/backend --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
UMask=0027

[Install]
WantedBy=multi-user.target
EOF
cat > /etc/systemd/system/stock-panel-sync.service <<'EOF'
[Unit]
Description=Refresh Guanshi market data
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=stockpanel
Group=stockpanel
WorkingDirectory=/opt/stock-panel/current
EnvironmentFile=/etc/stock-panel.env
ExecStart=/opt/stock-panel/current/backend/.venv/bin/python /opt/stock-panel/current/scripts/run.py sync
TimeoutStartSec=4h
NoNewPrivileges=true
PrivateTmp=true
UMask=0027
EOF
cat > /etc/systemd/system/stock-panel-sync.timer <<'EOF'
[Unit]
Description=Daily Guanshi market refresh at 18:30 Shanghai time

[Timer]
OnCalendar=*-*-* 18:30:00 Asia/Shanghai
Persistent=true
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
EOF
cat > "$base/backup.py" <<'PY'
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

root = Path('/var/lib/stock-panel')
stamp = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d-%H%M%S-%f')
dest = root / 'backups' / f'market-{stamp}.sqlite3'
with sqlite3.connect((root / 'stock-panel.sqlite3').as_uri() + '?mode=ro', uri=True) as source, sqlite3.connect(dest) as target:
    source.backup(target)
    assert target.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
os.chmod(dest, 0o600)
# Rotate only backups created by this script; keep the latest fourteen.
for old in sorted((root / 'backups').glob('market-*.sqlite3'), reverse=True)[14:]:
    old.unlink()
print(dest, flush=True)
PY
cat > /etc/systemd/system/stock-panel-backup.service <<'EOF'
[Unit]
Description=Consistent SQLite backup for Guanshi

[Service]
Type=oneshot
User=stockpanel
Group=stockpanel
ExecStart=/opt/stock-panel/current/backend/.venv/bin/python /opt/stock-panel/backup.py
NoNewPrivileges=true
PrivateTmp=true
UMask=0077
EOF
cat > /etc/systemd/system/stock-panel-backup.timer <<'EOF'
[Unit]
Description=Daily Guanshi database backup

[Timer]
OnCalendar=*-*-* 03:30:00 Asia/Shanghai
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemd-analyze verify /etc/systemd/system/stock-panel*.service /etc/systemd/system/stock-panel*.timer
systemctl daemon-reload
systemctl enable --now stock-panel.service stock-panel-sync.timer stock-panel-backup.timer
sleep 3
systemctl is-active stock-panel.service
curl -fsS http://127.0.0.1:8000/api/data-status
