#!/usr/bin/env bash
# Cloud-init bootstrap: installs the runtime (Python, Node, nginx) and lays
# down systemd/nginx config templates. Deliberately does NOT clone or start
# the app - there's no git remote for this repo yet, so deploy.sh (run
# locally, after `terraform apply`) pushes the code via rsync and starts the
# services. Keeping "provision the box" and "ship the code" as two separate
# steps is standard practice and avoids baking secrets into cloud-init logs.
set -euo pipefail
exec > >(tee /var/log/sentinel-bootstrap.log) 2>&1

echo "=== apt update/upgrade ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y

echo "=== base packages ==="
apt-get install -y software-properties-common curl git build-essential nginx rsync ufw

echo "=== Python 3.11 (deadsnakes) ==="
# Not the OS-default python3 on purpose: pins to a version known compatible
# with the backend's pinned torch==2.1.0 (see requirements.txt), rather than
# whatever Python the base image happens to ship.
add-apt-repository -y ppa:deadsnakes/ppa
apt-get update -y
apt-get install -y python3.11 python3.11-venv python3.11-dev

echo "=== Node.js 24 (NodeSource) ==="
# sfcc-qa-automation and the frontend both require Node >= 24 (see their
# package.json "engines" fields).
curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
apt-get install -y nodejs

echo "=== certbot (for HTTPS later, once a domain is pointed at this IP) ==="
apt-get install -y certbot python3-certbot-nginx

echo "=== app directories ==="
mkdir -p /opt/sentinel
chown -R ubuntu:ubuntu /opt/sentinel

echo "=== systemd unit: sentinel-backend ==="
cat > /etc/systemd/system/sentinel-backend.service <<'UNIT'
[Unit]
Description=Sentinel backend (FastAPI)
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/sentinel/sentinel-qa-analytics-dashboard
ExecStart=/opt/sentinel/sentinel-qa-analytics-dashboard/venv/bin/python -m uvicorn services.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure
RestartSec=5
EnvironmentFile=/opt/sentinel/sentinel-qa-analytics-dashboard/.env

[Install]
WantedBy=multi-user.target
UNIT
# --workers 1 is required, not a default left unconfigured: the live-run
# pub/sub lives in one process's memory (see LIVE_EXECUTION_ARCHITECTURE.md
# #12/#19) - more workers would silently split live runs across processes
# that can't see each other's connections.

echo "=== systemd unit: sentinel-frontend ==="
cat > /etc/systemd/system/sentinel-frontend.service <<'UNIT'
[Unit]
Description=Sentinel frontend (Next.js)
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/sentinel/sentinel-qa-analytics-dashboard/frontend
ExecStart=/usr/bin/npm start
Restart=on-failure
RestartSec=5
EnvironmentFile=/opt/sentinel/sentinel-qa-analytics-dashboard/frontend/.env.local

[Install]
WantedBy=multi-user.target
UNIT

echo "=== nginx site: sentinel ==="
cat > /etc/nginx/sites-available/sentinel <<'NGINX'
server {
    listen 80;
    server_name _;

    # Live execution depends on this endpoint staying a real streaming
    # connection - buffering it would turn "live" updates into bursty,
    # delayed ones. See LIVE_EXECUTION_VM_DEPLOYMENT.md for why each of
    # these specifically matters.
    location /live/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_buffering off;
        proxy_read_timeout 3600s;
    }

    location /docs {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    # Everything else the frontend doesn't own is the backend API.
    location ~ ^/(health|auth|ingest|chat|chart|data|dashboard|debug|ingestions|suggestions|feedback|projects|roles|test|usage)(/|$) {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGINX

ln -sf /etc/nginx/sites-available/sentinel /etc/nginx/sites-enabled/sentinel
rm -f /etc/nginx/sites-enabled/default
systemctl reload nginx || systemctl restart nginx

echo "=== firewall (allow OpenSSH + nginx; AWS security group is the primary control, this is defense-in-depth) ==="
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

systemctl daemon-reload

echo "=== bootstrap complete ==="
