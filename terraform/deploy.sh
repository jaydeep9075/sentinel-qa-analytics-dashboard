#!/usr/bin/env bash
# Pushes the local sentinel-qa-analytics-dashboard code to the VM Terraform
# just created, and starts it. Run this AFTER `terraform apply`.
#
# Usage:
#   ./deploy.sh                    # reads the IP from `terraform output`
#   ./deploy.sh 203.0.113.4        # or pass the IP explicitly
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REMOTE_USER="ubuntu"
REMOTE_DIR="/opt/sentinel/sentinel-qa-analytics-dashboard"

IP="${1:-}"
if [ -z "$IP" ]; then
    IP="$(cd "$SCRIPT_DIR" && terraform output -raw instance_public_ip 2>/dev/null || true)"
fi
if [ -z "$IP" ]; then
    echo "Could not determine the VM's IP. Run 'terraform apply' first, or pass the IP: ./deploy.sh <ip>" >&2
    exit 1
fi

echo "==> Target: $REMOTE_USER@$IP:$REMOTE_DIR"

echo "==> Waiting for the VM to finish its cloud-init bootstrap (can take ~2-4 min on first boot)..."
until ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 "$REMOTE_USER@$IP" '[ -f /var/log/sentinel-bootstrap.log ] && grep -q "bootstrap complete" /var/log/sentinel-bootstrap.log' 2>/dev/null; do
    sleep 10
    echo "    still waiting..."
done
echo "==> Bootstrap confirmed complete."

if [ ! -f "$REPO_ROOT/.env" ]; then
    echo "WARNING: no local .env found at $REPO_ROOT/.env - the backend won't start without one." >&2
    echo "         Copy your local .env there (same one 'python -m services.main' uses locally) and rerun." >&2
fi
if [ ! -f "$REPO_ROOT/frontend/.env.local" ]; then
    echo "WARNING: no local frontend/.env.local found - the frontend needs NEXT_PUBLIC_API_URL set." >&2
fi

echo "==> Syncing code (excluding venv, node_modules, data, .git, reports)..."
rsync -az --delete \
    --exclude 'venv' \
    --exclude 'node_modules' \
    --exclude 'data' \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude 'frontend/.next' \
    --exclude 'frontend/node_modules' \
    --exclude 'users.db' \
    "$REPO_ROOT/" "$REMOTE_USER@$IP:$REMOTE_DIR/"

echo "==> Installing backend dependencies + starting services on the VM..."
ssh "$REMOTE_USER@$IP" bash -s <<REMOTE
set -euo pipefail
cd "$REMOTE_DIR"

if [ ! -d venv ]; then
    python3.11 -m venv venv
fi
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

echo "==> Frontend: npm install + build..."
cd frontend
npm install
npm run build
cd ..

sudo systemctl daemon-reload
sudo systemctl enable sentinel-backend sentinel-frontend
sudo systemctl restart sentinel-backend sentinel-frontend
sudo systemctl reload nginx

echo "==> Services status:"
sudo systemctl --no-pager status sentinel-backend | head -5
sudo systemctl --no-pager status sentinel-frontend | head -5
REMOTE

echo ""
echo "==> Done. Dashboard: http://$IP"
echo "    Backend health:  http://$IP/health"
echo "    Logs:             ssh $REMOTE_USER@$IP 'sudo journalctl -u sentinel-backend -f'"
