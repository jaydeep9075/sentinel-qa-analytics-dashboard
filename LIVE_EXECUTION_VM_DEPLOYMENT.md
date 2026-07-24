# Hosting Sentinel Live Execution on a VM

How this actually runs once it's on a server, not your laptop. One VM, no containers required (Docker is optional, not necessary).

## What's running on the VM

| Process | What it is | Port |
|---|---|---|
| `services.main` (uvicorn) | FastAPI backend — dashboard API + live-execution ingestion/SSE | 8000 |
| Next.js (`npm start`) | Frontend dashboard | 3000 |
| nginx | Reverse proxy — the only thing exposed to the internet | 443 (80 → redirect) |

Everything else (SQLite live-run DB, LanceDB folders, uploaded attachments) is just files on the VM's disk under `data/`. Nothing extra to install — no Postgres, no Redis, no message broker.

## Why nginx matters specifically for live execution

The live view depends on **SSE** (a long-lived HTTP response that stays open and streams events). Two nginx settings matter or the "live" part silently stops working:

```nginx
location /live/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;        # <-- without this, nginx buffers the SSE
                                  #     stream and updates arrive in bursts,
                                  #     not live
    proxy_read_timeout 3600s;    # <-- without this, nginx kills the
                                  #     connection after ~60s and the browser
                                  #     has to silently reconnect
}

location / {
    proxy_pass http://127.0.0.1:3000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
}
```

`X-Accel-Buffering: no` is already sent by the backend itself (see `services/live_exec/router.py`); `proxy_buffering off` is nginx's side of the same requirement.

## Process management — systemd (recommended over a screen/tmux session)

`/etc/systemd/system/sentinel-backend.service`:
```ini
[Unit]
Description=Sentinel backend
After=network.target

[Service]
WorkingDirectory=/opt/sentinel/sentinel-qa-analytics-dashboard
ExecStart=/opt/sentinel/sentinel-qa-analytics-dashboard/venv/bin/python -m uvicorn services.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure
EnvironmentFile=/opt/sentinel/sentinel-qa-analytics-dashboard/.env

[Install]
WantedBy=multi-user.target
```

**`--workers 1` is not a typo — it's required.** The live pub/sub (§ architecture doc §12) lives in one process's memory. Running multiple uvicorn workers would split live runs across processes that can't see each other's connections, silently breaking the live view for some users. If you ever need more backend capacity, scale the VM up (more CPU/RAM), not out (more workers) — see the architecture doc's Redis Streams note for what "out" eventually looks like, not needed here.

`/etc/systemd/system/sentinel-frontend.service`:
```ini
[Unit]
Description=Sentinel frontend
After=network.target

[Service]
WorkingDirectory=/opt/sentinel/sentinel-qa-analytics-dashboard/frontend
ExecStart=/usr/bin/npm start
Restart=on-failure
EnvironmentFile=/opt/sentinel/sentinel-qa-analytics-dashboard/frontend/.env.local

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now sentinel-backend sentinel-frontend
sudo systemctl status sentinel-backend
```

Both restart automatically on crash and on VM reboot — this is what makes SQLite's WAL crash-recovery actually matter: a run in progress survives a `systemctl restart` because the file on disk is the source of truth, not the process's memory.

## Environment variables that matter for this feature specifically

Add to the backend's `.env` (everything else — `LLM_PROVIDER`, `SECRET_KEY`, etc. — is unchanged from today):

```bash
LIVE_INGEST_API_KEY=<generate a long random string>   # required once exposed beyond localhost
CORS_ALLOWED_ORIGINS=https://sentinel.yourcompany.com
```

Whoever runs `playwright test` (locally or in CI) needs two values pointed at your VM:

```bash
SENTINEL_BASE_URL=https://sentinel.yourcompany.com
SENTINEL_API_KEY=<same value as LIVE_INGEST_API_KEY>
```

## Reaching the VM from CI

- **Self-hosted runners** (Jenkins on your own network, self-hosted GitHub/Azure/Bitbucket runners): trivial — same network as the VM, no extra config.
- **Cloud-hosted runners** (GitHub-hosted Actions runners, etc.): the VM's `https://sentinel.yourcompany.com` must be reachable from the public internet (behind nginx + a real TLS cert, e.g. via Certbot). This is the same requirement you already have for anything that reports back to a self-hosted tool from GitHub-hosted CI — not new to this feature.

## Backups — what actually needs backing up

| Path | What it is | Back up? |
|---|---|---|
| `data/ingestion_*/` | LanceDB — permanent history | **Yes**, this is the product's data |
| `users.db` | Auth | **Yes** |
| `data/live_runs.db` | In-progress runs only | **No** — by design, nothing here is meant to outlive the run (see architecture doc §6) |
| `data/runs/*/attachments/` | Screenshots/videos for runs not yet finalized | Optional — becomes part of the permanent record once finalized |

A nightly `rsync`/`tar` of `data/ingestion_*` and `users.db` to off-VM storage is enough. There's no database server to dump — it's all just files, which is the entire point of this stack.

## Firewall / exposure

Only nginx (443/80) needs to be open to the internet. Ports 8000 (backend) and 3000 (frontend) should be bound to `127.0.0.1` only (already the case in the systemd units above) — nginx is the sole entry point, same as any standard reverse-proxy setup.

## Upgrading

```bash
cd /opt/sentinel/sentinel-qa-analytics-dashboard
git pull
venv/bin/pip install -r requirements.txt
sudo systemctl restart sentinel-backend

cd frontend && npm install && npm run build
sudo systemctl restart sentinel-frontend
```

Any run in progress during a backend restart is not lost — SQLite's WAL survives it, and the reporter's offline buffer covers the few seconds the backend is down (see architecture doc §18, "network blip" row) — it just resumes.
