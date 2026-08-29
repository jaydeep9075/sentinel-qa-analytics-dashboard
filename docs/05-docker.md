# Docker

TR-Insight ships two distribution shapes. Pick the one that matches what you're optimizing for.

| | Split images (`docker-compose.yml`) | All-in-one (`Dockerfile.allinone`) |
|---|---|---|
| Containers | 2 (`backend`, `frontend`) | 1 (`app`, both processes under `supervisord`) |
| Independent restart/scale/resource limits | Yes | No — both go down together |
| Best for | A real deployment you actually operate | "Try it in five minutes" or a single-host demo |

Storage is identical either way — the same `DATA_DIR`/`STATE_DIR`/`INGEST_SOURCE_DIR` bind mounts, described in [`06-hosting-and-resources.md`](06-hosting-and-resources.md).

## Which compose file

| File | Use it when |
|---|---|
| `docker-compose.yml` | You have the source and want to build the split images yourself |
| `docker-compose.pull.yml` | You just want to *run* the split images — no git clone, images pulled from Docker Hub |
| `docker-compose.allinone.yml` | Maintainer-side: build and publish the combined image |
| `docker-compose.pull.allinone.yml` | The simplest possible run: one image, one container, pulled not built |

For the pull-only files, all you need on disk is that one file plus `.env`:

```bash
curl -O https://raw.githubusercontent.com/jaydeep9075/sentinel-qa-analytics-dashboard/main/docker-compose.pull.allinone.yml
curl -O https://raw.githubusercontent.com/jaydeep9075/sentinel-qa-analytics-dashboard/main/.env.example
cp .env.example .env      # fill in what you need — see §2 below
docker compose -f docker-compose.pull.allinone.yml pull
docker compose -f docker-compose.pull.allinone.yml up -d
```

## 1. Build and run (split images, from source)

```bash
docker compose up --build -d
```

Backend and frontend each get their own container, own filesystem, own resource limit — but this one command builds and starts both, and `docker compose down` stops both. First build takes a few minutes (the backend installs `torch` and bakes in an embedding model); later builds reuse cached layers.

Windows helper scripts, if you'd rather not use a terminal: `docker-start.bat` (build + start, prompts you through `.env`), `docker-stop.bat`, `docker-ingest.bat` (one-shot ingestion — see §4).

## 2. Environment variables that matter for a Docker run

Full reference: `.env.example` (heavily commented) and [`06-hosting-and-resources.md`](06-hosting-and-resources.md). The essentials:

| Variable | What it's for |
|---|---|
| `SECRET_KEY` | JWT signing. Auto-generates into `state/secret_key` if unset. |
| `LLM_PROVIDER` / `LLM_MODEL` / `LLM_API_KEY` (or `GEMINI_API_KEY`/etc.) | Which AI backend to use. Can be finished later from Admin → Settings instead. |
| `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD` | The first admin account. Auto-generated and logged once if left unset. |
| `DATA_DIR` / `STATE_DIR` / `INGEST_SOURCE_DIR` | Host-side storage locations (container-side paths are fixed). |
| `NEXT_PUBLIC_API_URL` | The URL your **browser** calls — baked into the frontend at *build* time, needs a rebuild to change. |
| `CORS_ALLOWED_ORIGINS` | Must include the frontend's actual origin or every browser call fails CORS. |

Only `NEXT_PUBLIC_API_URL` requires a rebuild to change (`docker compose build frontend`). Everything else in `.env` is read at container start — edit and `docker compose up -d`, no rebuild.

## 3. Resource limits (as configured in the compose files)

| Service | Memory | CPU |
|---|---|---|
| `backend` (split) | 3g | 2.0 |
| `frontend` (split) | 1g | 1.0 |
| `app` (all-in-one) | 3g | 2.0 |
| `redis` (optional, multi-instance profile) | 256m | — |

Container logs are capped (`json-file`, 10MB × 3 files) on every service so a long-running deployment can't fill the disk with logs.

## 4. One-shot ingestion

The `ingest` service reuses the backend image with a different entrypoint — not started by a plain `docker compose up`:

```bash
docker compose run --rm ingest
```

Drop your data under `ingest-source/`, point `config2.json`'s source `path` at the container path (`/app/ingest-source/<file>`), then run the command above. Output lands in the same `data/` volume the running backend reads from — it shows up in `GET /ingestions` immediately, no restart. `docker-ingest.bat` wraps this for Windows.

## 5. `.dockerignore` scope

`.dockerignore` (split images) and `Dockerfile.allinone.dockerignore` (all-in-one) both exclude runtime state and secrets from the build context: `.env`, `config.json`, `config2.json`, `auth_seed_users.json`, `users.db`, `data/`, `ingest-source/`, plus the usual `node_modules`/`venv`/`.git`. None of that belongs in a portable image — it's supplied at runtime via `env_file` and bind mounts instead.

## 6. Multi-instance (optional)

Only relevant once you run more than one `backend` replica behind a load balancer — a single replica (the default) needs none of this.

```bash
docker compose --profile multi-instance up
```

This starts a `redis` container and wires `REDIS_URL` so the live-run SSE bus and live-frame cache work across instances instead of just within one. See [`03-architecture-guide.md`](03-architecture-guide.md#live-execution-servicesliveexec--packagessentinel-qa-reporter) for what that subsystem does.

## Troubleshooting

- **Frontend can't reach the backend from the browser** — confirm `NEXT_PUBLIC_API_URL` was correct at *build* time, and `CORS_ALLOWED_ORIGINS` includes the frontend's origin (`http://localhost:3000` by default).
- **Backend won't start, complains about `SECRET_KEY`** — must be 32+ characters if set explicitly.
- **`docker compose run --rm ingest` can't find your file** — the `path` in `config2.json` must be the *container* path (`/app/ingest-source/...`), not a host path.
- **Build Trends shows no builds** — confirm the mount is live: `docker compose exec frontend ls /app/data` should list `ingestion_*` folders.
- **Using Ollama on the host** — `OLLAMA_URL=http://localhost:11434` points at the container itself. Use `http://host.docker.internal:11434`.
- **Backend takes ~30–45s on its first request** — that's LanceDB/DuckDB opening the selected ingestion, not a model download (the embedding model is already baked into the image). The healthcheck's `start_period` already accounts for it.

Where the data actually lives, backups, and scaling further belong in [`06-hosting-and-resources.md`](06-hosting-and-resources.md).
