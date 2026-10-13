"""Keep pytdxdata's writable server-probe cache outside the read-only release."""
import os
import pwd
import shutil
from pathlib import Path

package_file = Path('/opt/stock-panel/current/backend/.venv/lib/python3.12/site-packages/pytdxdata/servers.json')
cache_file = Path('/var/lib/stock-panel/tdx-servers.json')
backup = Path('/var/backups/stock-panel/20261013-140313/tdx-servers-original.json')
if not backup.exists():
    shutil.copyfile(package_file, backup)
if not cache_file.exists():
    shutil.copyfile(package_file, cache_file)
account = pwd.getpwnam('stockpanel')
os.chown(cache_file, account.pw_uid, account.pw_gid)
cache_file.chmod(0o600)
if not package_file.is_symlink():
    link = package_file.with_name('servers.stock-panel-link')
    link.symlink_to(cache_file)
    os.replace(link, package_file)
elif package_file.resolve() != cache_file:
    raise SystemExit('Unexpected pre-existing cache symlink')
print('pytdxdata probe cache:', cache_file)
