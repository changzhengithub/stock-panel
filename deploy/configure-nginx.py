"""Apply the first deployment proxy, retaining BaoTa TLS and ACME configuration."""
from pathlib import Path
import re
import shutil
import subprocess

config = Path('/www/server/panel/vhost/nginx/guanshi.shop.conf')
alias = config.with_name('stock-panel-www.conf')
backup = Path('/var/backups/stock-panel/20261013-140313')
backup.mkdir(parents=True, exist_ok=True, mode=0o700)
saved = backup / config.name
if saved.exists() or alias.exists():
    raise SystemExit('First-deployment configuration already exists; inspect before updating')
subprocess.run(['curl', '-fsS', '-o', '/dev/null', 'http://127.0.0.1:8000/api/data-status'], check=True)
shutil.copy2(config, saved)
original = config.read_text()
updated = re.sub(r'    location ~ .*?\\\.\(gif\|jpg\|jpeg\|png\|bmp\|swf\)\$\s*\{[^}]*\}', '', original)
updated = re.sub(r'    location ~ .*?\\\.\(js\|css\)\?\$\s*\{[^}]*\}', '', updated)
if updated == original or 'location / {' in updated:
    raise SystemExit('Unexpected Nginx template; refused automatic edit')
proxy = '''
    # Guanshi application: preserve the separate BaoTa ACME validation location.
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 5s;
        proxy_read_timeout 60s;
        proxy_cache off;
    }
'''
updated = updated.replace('    access_log  /www/wwwlogs/guanshi.shop.log;', proxy + '\n    access_log  /www/wwwlogs/guanshi.shop.log;')
config.write_text(updated)
alias.write_text('''# Managed by the stock-panel deployment; www redirects to the canonical domain.
server {
    listen 80;
    server_name www.guanshi.shop;
    root /www/wwwroot/guanshi.shop;
    location ^~ /.well-known/acme-challenge/ { try_files $uri =404; }
    location / { return 301 https://guanshi.shop$request_uri; }
}
''')
try:
    subprocess.run(['/www/server/nginx/sbin/nginx', '-t'], check=True)
    subprocess.run(['/www/server/nginx/sbin/nginx', '-s', 'reload'], check=True)
except BaseException:
    shutil.copy2(saved, config)
    alias.unlink(missing_ok=True)
    raise
print('Proxy configured; original Nginx configuration saved at', saved)
