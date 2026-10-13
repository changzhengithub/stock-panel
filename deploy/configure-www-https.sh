#!/usr/bin/env bash
# Issue an independent certificate for www without replacing BaoTa's apex certificate.
set -euo pipefail
base=/opt/stock-panel
test -f /www/server/panel/vhost/nginx/stock-panel-www.conf
export UV_PYTHON_INSTALL_DIR="$base/python" UV_CACHE_DIR="$base/uv-cache"
"$base/bin/uv" venv --python "$base/current/backend/.venv/bin/python" "$base/certbot-env"
"$base/bin/uv" pip install --python "$base/certbot-env/bin/python" 'certbot==5.8.0'
"$base/certbot-env/bin/certbot" certonly --non-interactive --agree-tos \
  --register-unsafely-without-email --webroot -w /www/wwwroot/guanshi.shop \
  --cert-name stock-panel-www -d www.guanshi.shop
cp -p /www/server/panel/vhost/nginx/stock-panel-www.conf /var/backups/stock-panel/20261013-140313/www-http.conf
cat >> /www/server/panel/vhost/nginx/stock-panel-www.conf <<'EOF'
server {
    listen 443 ssl;
    http2 on;
    server_name www.guanshi.shop;
    ssl_certificate /etc/letsencrypt/live/stock-panel-www/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/stock-panel-www/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    return 301 https://guanshi.shop$request_uri;
}
EOF
if ! /www/server/nginx/sbin/nginx -t; then
    cp -p /var/backups/stock-panel/20261013-140313/www-http.conf /www/server/panel/vhost/nginx/stock-panel-www.conf
    exit 1
fi
/www/server/nginx/sbin/nginx -s reload
cat > "$base/reload-nginx.sh" <<'EOF'
#!/bin/sh
set -e
/www/server/nginx/sbin/nginx -t
/www/server/nginx/sbin/nginx -s reload
EOF
chmod 755 "$base/reload-nginx.sh"
cat > /etc/systemd/system/stock-panel-cert-renew.service <<'EOF'
[Unit]
Description=Renew Guanshi www redirect certificate
After=network-online.target

[Service]
Type=oneshot
ExecStart=/opt/stock-panel/certbot-env/bin/certbot renew --cert-name stock-panel-www --quiet --deploy-hook /opt/stock-panel/reload-nginx.sh
EOF
cat > /etc/systemd/system/stock-panel-cert-renew.timer <<'EOF'
[Unit]
Description=Check Guanshi www certificate twice daily

[Timer]
OnCalendar=*-*-* 04,16:00:00 Asia/Shanghai
RandomizedDelaySec=1800
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now stock-panel-cert-renew.timer
"$base/certbot-env/bin/certbot" renew --cert-name stock-panel-www --dry-run
