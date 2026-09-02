# Hosting & Resources

What it takes to run TR-Insight for real: sizing, storage, the full environment-variable reference, scaling, and hosting options.

## Resource sizing

TR-Insight is designed to run as **one VM, one Docker host** — no database server, no Kubernetes required. As configured in the compose files:

| Service | Memory limit | CPU limit |
|---|---|---|
| Backend | 3 GB | 2.0 cores |
| Frontend | 1 GB | 1.0 core |
| Redis (optional, multi-instance only) | 256 MB | — |

For a real VM (not just container limits), the documented starting point is a **`t3.large`** (2 vCPU, 8 GB RAM) — sized for the backend's embedding model, which is loaded into memory. `t3.medium` is enough to kick the tires. These aren't hard requirements, just the tested baseline — scale up if you're running a large ingestion or a busy multi-user deployment, and treat them as defaults to verify against your own load, not guarantees.

Disk: no fixed number is documented. Plan for the size of your Allure results history plus room to grow — see storage layout below. A 50 GB volume is the default in the Terraform hosting path (§4).

## Storage layout

Nothing important lives inside a container — everything is a bind mount to the host, so `docker compose down`, rebuilds and image deletion never destroy it.

| Path | Host default | Contents |
|---|---|---|
| `DATA_DIR` | `./data` | Every ingestion (`ingestion_*/` — LanceDB vectors + DuckDB tables + `summary.json`), finalized live runs (`run_*/`), `live_runs.db` (in-progress runs only, **not** worth backing up), `token_usage_store.json` |
| `STATE_DIR` | `./state` | `users.db` (accounts), `config2.json` (ingester config), `secret_key`, `bootstrap_admin_password`, `live_ingest_api_key` — the auto-generated secrets |
| `INGEST_SOURCE_DIR` | `./ingest-source` | Drop-box for raw data to import (watched by auto-ingest if enabled) |

Growth is driven by ingestion volume: each build's LanceDB/DuckDB tables, chat history and saved charts live inside that build's own folder under `DATA_DIR`. Deleting a build from the dashboard removes its entire folder — nothing to garbage-collect separately.

**Backup = copy `DATA_DIR` and `STATE_DIR`.** That's the whole state of the system; there's no database server to dump, it's all just files. A nightly `rsync`/`tar` of both to off-VM storage is enough. `data/live_runs.db` and unfinalized run attachments don't need backing up — by design, nothing there is meant to outlive an in-progress run.

All three directories relocate with a one-line `.env` change (`DATA_DIR=/mnt/qa-storage/data`, etc.) and no rebuild — Docker creates the new location if it doesn't exist. Two things to get right when relocating: move the *contents*, don't just repoint (an empty new `STATE_DIR` means an empty user database), and leave `AUTH_USER_STORE_URL` unset so it stays pointed at the mounted path rather than somewhere inside the container's own filesystem.

## Full environment-variable reference

The authoritative source is `.env.example` at the repo root — every variable is documented there with what it does and its default. Summary by section:

### Required to actually be useful (all have safe defaults for a first look)

| Variable | Default if unset |
|---|---|
| `SECRET_KEY` | Auto-generated into `state/secret_key` |
| `LLM_API_KEY` (or `GEMINI_API_KEY`/`ANTHROPIC_API_KEY`/etc.) | none — finish later in Admin → Settings |
| `BOOTSTRAP_ADMIN_USERNAME` | `admin` |
| `BOOTSTRAP_ADMIN_PASSWORD` | Auto-generated into `state/bootstrap_admin_password`, logged once at startup |

### LLM

`LLM_PROVIDER`, `LLM_MODEL`, per-provider keys (`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, …), `LLM_API_BASE` (proxy/gateway), `OLLAMA_URL` (only for `LLM_PROVIDER=ollama`).

### Storage locations

`DATA_DIR`, `STATE_DIR`, `INGEST_SOURCE_DIR` — see storage layout above.

### Ports and browser-facing URL

`BACKEND_PORT` (default `8000`), `FRONTEND_PORT` (default `3000`), `NEXT_PUBLIC_API_URL` (the URL your **browser** calls — build-time only, see [`05-docker.md`](05-docker.md)), `CORS_ALLOWED_ORIGINS`.

### Ingestion triggers

`AUTO_INGEST_ENABLED`, `AUTO_INGEST_INTERVAL_SECONDS`, `AUTO_INGEST_STABLE_SECONDS`, `AUTO_INGEST_DEFAULT_WORKSPACE` (drop-box watcher); `INGEST_API_KEYS` (`key:workspace` pairs for `POST /ingest/upload`), `INGEST_UPLOAD_MAX_BYTES`.

### Accounts, registration and visibility

`AUTH_BACKEND` (`db`/`memory`), `AUTH_AUTO_SEED_USERS`, `AUTH_SEED_FILE`, `AUTH_ALLOW_SELF_REGISTRATION`, `AUTH_AUTO_APPROVE_REGISTRATION`, `AUTH_DEFAULT_ROLE`, `AUTH_DEFAULT_WORKSPACE`, `DEFAULT_WORKSPACE_ID`, `LEGACY_BUILDS_WORKSPACE`.

### Advanced

`PROJECTS_ROOT`, `ROLES_ROOT`, `LIVE_INGEST_API_KEY` (the shared secret the reporter package sends — auto-generates if unset), `INGEST_MAX_FILE_SIZE_BYTES` (default 200MB), `INGEST_MAX_ROWS` (default 500k), `INGEST_TIMEOUT_SECONDS` (default 600s), `INGESTION_POOL_SIZE`, `MAX_TREND_BUILDS`, `MAX_CROSS_BUILD_QUERY_BUILDS`, `WEB_CONCURRENCY` (uvicorn workers — see the scaling note below before raising it), `REDIS_URL` / `REDIS_PORT` (multi-instance only).

### Published image (Docker Hub pulls only)

`IMAGE_NAMESPACE`, `IMAGE_TAG` — ignored by `docker compose build`, only read by the `.pull.yml` variants.

## Scaling

- **Single instance is the default and needs nothing extra.** `WEB_CONCURRENCY` defaults to `1` deliberately — `services/state.py` holds the selected ingestion as mutable global state, so raising worker count isn't a free lunch; understand that coupling before changing it.
- **More than one backend replica behind a load balancer** needs `REDIS_URL` (`docker compose --profile multi-instance up`) so the live-run SSE bus and live-frame cache work across instances instead of just within one process.
- There is no database server to scale separately — LanceDB and DuckDB are both file-based, living entirely under `DATA_DIR`.

## Hosting options

### Docker Compose on any host (recommended default)

Covered fully in [`05-docker.md`](05-docker.md). Works on any machine with Docker — a laptop, a VM, a bare-metal box.

### AWS via Terraform (`terraform/`)

A documented, working path exists in the `terraform/` folder: `terraform apply` provisions one EC2 instance (default `t3.large`), an Elastic IP, and a security group allowing only SSH + 80/443; `deploy.sh` then syncs the application code onto it and starts it via systemd, behind nginx.

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # set ssh_public_key_path, allowed_ssh_cidr
terraform init && terraform plan && terraform apply
./deploy.sh
```

Prerequisites: an AWS account with the CLI configured, Terraform installed, an SSH key pair, and a working local `.env` (`deploy.sh` copies it up as-is). Re-running `./deploy.sh` alone re-syncs code and restarts services without touching the AWS infrastructure. `terraform destroy` tears everything down — the LanceDB data on that instance's disk is **not** backed up automatically, so back up `data/` and `state/` (or `users.db`) yourself first, per the backup guidance above.

Approximate cost (US East, on-demand, check AWS's own pricing page for current numbers): `t3.large` 24/7 ≈ $60/month, `t3.medium` ≈ $30/month, a 50GB gp3 volume ≈ $4/month.

This path looks actively maintained (the deploy script, `.tf` files and bootstrap logic are all present and internally consistent as of this writing) but is a single-VM setup with no managed failover — treat it as a solid starting point for a self-hosted production instance, not a fully managed offering.

### Bring your own VM (no Terraform)

Anything that can run Docker works: install Docker, copy `docker-compose.yml` (or the `.pull` variant) and `.env`, `docker compose up -d`. The `terraform/user_data.sh` bootstrap script is a reasonable reference for what a from-scratch Ubuntu setup needs even if you don't use Terraform itself.

For TLS in front of the backend, there's now a one-command option instead of hand-rolling nginx/certbot: point a domain's DNS A record at the VM's IP, set `PUBLIC_DOMAIN=that-domain` in `.env`, and run `docker compose --profile proxy up -d`. This starts a `caddy` container (config in the repo-root `Caddyfile`) that reverse-proxies to the backend and requests + auto-renews its own Let's Encrypt certificate — no certbot, no cron job, no nginx config to write by hand. Skip this profile entirely if the frontend is split off to Vercel (which already terminates TLS for itself) and something else — a cloud load balancer, Cloudflare, the `terraform/` nginx path — already handles TLS for the backend.

### Split hosting (frontend on Vercel, backend on its own host)

This is the shape most teams end up wanting: Vercel builds and hosts `frontend/` directly from the git repo (no Docker involved on that side — Vercel's own Next.js build pipeline handles it), while the backend runs from `services/Dockerfile` on any host with a persistent volume, per above.

Frontend side (Vercel dashboard, one time):

1. Import the repo, set **Root Directory** to `frontend`.
2. Add environment variable `NEXT_PUBLIC_API_URL` = your backend's real public URL (e.g. `https://api.yourdomain.com`) — this is inlined at build time, so changing it later needs a redeploy, not just a restart.
3. Deploy. No Dockerfile is used for this path; `frontend/Dockerfile` stays for teams who'd rather self-host the frontend too (see `05-docker.md`).

Backend side, on the host you picked:

1. Set `CORS_ALLOWED_ORIGINS` to the Vercel domain (and any preview domains you use), comma-separated.
2. Give it a persistent volume for `DATA_DIR`/`STATE_DIR` (see storage layout above) — this is the one hard requirement; a purely serverless/ephemeral platform loses all data and accounts on every redeploy.
3. Optionally put the `caddy` profile above in front of it for HTTPS, or terminate TLS however your platform already does.

Full detail on what does and doesn't change when splitting this way — including the two now-fixed Next.js routes that used to read the backend's filesystem directly — is in [`08-split-hosting-and-production-readiness.md`](08-split-hosting-and-production-readiness.md).
