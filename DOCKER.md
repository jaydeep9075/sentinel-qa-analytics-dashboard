# Running Sentinel QA Analytics in Docker

> **New to this repo? Start with [SETUP.md](SETUP.md)** — it walks through
> first-time setup, everyday start/stop, rebuilding after a change, and
> relocating storage. This file is the deeper reference: scaling, Redis, and
> the full environment-variable breakdown.

**The one command that runs everything:**

```bash
docker compose up --build -d
```



Backend and frontend each get their own container — separate processes,
separate filesystems, separate resource limits — but that single command
builds and starts both together, and `docker compose down` stops both
together. You do **not** need two terminals; that's the point of compose.
(If you *want* to watch them live instead of detaching, drop the `-d` and
both services' logs stream interleaved into that one terminal.)

- Frontend → http://localhost:3000
- Backend → http://localhost:8000 (`/docs` for Swagger, `/health` for a ping)

First run only: read §1 below, since the app won't start without a
`SECRET_KEY` and a login account.

Everything else assumes Docker Desktop is installed and running. Three
double-click scripts are provided if you'd rather not touch the command
line at all: `docker-start.bat`, `docker-stop.bat`, `docker-ingest.bat`.

## 1. First-time setup

**a. Environment variables** — copy the template and edit it:

```bash
cp .env.example .env
```

Open `.env` and set at minimum:
- `SECRET_KEY` — the app refuses to start without this (must be 32+
  characters). Generate one:
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(48))"
  ```
- `LLM_PROVIDER` / `LLM_MODEL` / `LLM_API_KEY` — whichever LLM you're using.
  The key is resolved **per provider**: the active provider's own variable
  (`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or
  `<PROVIDER>_API_KEY` for anything else litellm supports) wins, and
  `LLM_API_KEY` is the fallback. Any litellm provider works; ones without a
  built-in default must name `LLM_MODEL` explicitly. See SETUP.md §3 step 1.
- `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD` — the first admin,
  created only when the user database is empty. Leave `BOOTSTRAP_ADMIN_PASSWORD`
  blank and one is generated into `state/bootstrap_admin_password` and printed
  in the backend's startup logs (`docker compose logs backend`) — there is no
  fixed "admin"/"admin" default anymore, on purpose (a well-known password on
  an appliance reachable before you've logged in is a race, not a safeguard).
  A forced password change on first login applies either way.

Every other variable has a working default (see the comments in
`.env.example` — it documents what each one does and what `services/config.py`
falls back to if it's left unset).

**b. Nothing.** `data/`, `state/` and `ingest-source/` are **directory**
mounts, so Docker creates any that are missing, and the backend seeds
`state/users.db` and `state/config2.json` inside on first start.

This used to require a `touch users.db` step: Docker passes a *single file*
through a bind mount only when that file already exists on the host, and
otherwise creates a directory with that name, which fails in a way that reads
as an application bug. Mounting the directory that contains those files
removes the failure mode, so `.env` is now the only thing a human supplies.

*Upgrading from the older layout?* With the stack stopped, move the two files
in once: `mkdir state && mv users.db config2.json state/`.

**d. A login account** — set `BOOTSTRAP_ADMIN_USERNAME` and
`BOOTSTRAP_ADMIN_PASSWORD` in `.env` before the first start and the admin is
created for you (only when the user table is empty — it can't override an
existing account). If `users.db` already has your accounts, skip this.

Everyone else gets an account by registering at `/register` and being approved
by an admin on the dashboard's **Users** page. See SETUP.md §3a for the full
model — accounts, approval, roles and workspaces.

The CLI still does everything the UI does, which is what you want when you're
locked out:

```bash
docker compose exec backend python -m services.admin_users list-users
docker compose exec backend python -m services.admin_users create-user     --username admin --role admin --workspace default --password 'pick-a-real-one'
docker compose exec backend python -m services.admin_users approve     --username jane --workspace platform --role sdet
```

Valid roles are the filenames in `roles/` (e.g. `cto`, `sdet`), plus
`admin`. Omit `--password` to be prompted instead — that needs an interactive
TTY: `docker compose exec -it backend ...`.

## 2. Start both frontend and backend

```bash
docker compose up --build
```

That's the whole command — it builds both images (first run only; later
runs reuse them unless code changed) and starts both containers together.
Each service runs in its **own container** (its own isolated process,
filesystem, and resource limits) but they're started/stopped as one unit
by this single command. Run with `-d` to detach and free up your terminal:

```bash
docker compose up --build -d
docker compose logs -f          # watch logs from both, or:
docker compose logs -f backend  # just one
```

- **Frontend**: http://localhost:3000
- **Backend**: http://localhost:8000 (Swagger docs at `/docs`, health at `/health`)

Stop everything:

```bash
docker compose down
```

Your data (`data/`, `users.db`) lives on the host via bind mounts, not
inside the containers — `docker compose down` never touches it.

## 3. Ingesting data (works with whatever you throw at it)

There are three ways in, and **all** need your raw data to be inside
`ingest-source/` on the host.

The third is the zero-effort one: set `AUTO_INGEST_ENABLED=true` in `.env` and
the backend ingests anything dropped into `ingest-source/` on its own, with no
click and no second command. See [SETUP.md §5a](SETUP.md#5a-auto-ingest-drop-a-file-and-walk-away)
for how it handles partial uploads, restarts, and duplicate watchers. The two
manual routes below keep working exactly as before either way. That folder is mounted into the backend and
the ingester at `/app/ingest-source`, so anything you drop there is
visible to both — and paths you type must be **container paths**
(`/app/ingest-source/my-results.zip`), never Windows paths
(`C:\Users\...`). The container has no access to the rest of your drive.

### 3a. From the dashboard ("Add Build") — the easy one

1. Drop your file/folder into `ingest-source/`.
2. In the dashboard, open **Add Build** and type the container path:
   `/app/ingest-source/my-results.zip`.
3. Hit ingest. It runs in the background inside the already-running
   backend; the new build appears when it finishes.

### 3b. From the command line (one-shot container)

Useful for large imports or scripted/CI runs — it doesn't need the
backend or frontend to be running at all.

The underlying tool (`universal_ingester/`) already handles a wide range
of input shapes generically — you don't need to tell it how to interpret
your data beyond picking the right `type`:

| `type` | Handles |
|---|---|
| `allure` | An Allure results folder, or a `.zip` of one (auto-extracted) |
| `file` | `.csv .tsv .xlsx .xls .json .jsonl .ndjson .parquet .xml .txt .log .pdf .png .jpg .yaml` — picked by file extension |
| `db` | A live database connection (MySQL/TiDB via `connection_string` + `tables`) |

**Steps:**

1. Drop your raw data into `ingest-source/` (a file, a folder, a `.zip` —
   whatever matches the `type` you'll use below). This folder is
   `.gitignore`'d — nothing you drop here gets committed.
2. Copy the Docker-specific config template and point it at what you dropped:
   ```bash
   cp config2.docker.json.example config2.json
   ```
   Edit `config2.json`'s `sources[0].path` to the container path of your
   data, e.g. `/app/ingest-source/my-results.zip` (the template has
   examples for `allure`, `file`, and `db`).

   > `config2.json` ships pointing at `/app/ingest-source/allure-results.zip`.
   > If yours still contains a `C:\...` path from local (non-Docker)
   > development, replace it — that path does not exist inside the container.
3. Run it:
   ```bash
   docker compose run --rm ingest
   ```

Output lands in `./data/ingestion_<timestamp>/`, the same folder the
`backend` container already reads from — if the backend is running, the
new ingestion shows up immediately via `GET /ingestions`, **no restart
needed**.

You can re-run step 3 any time with a different `config2.json` to ingest
more data; each run creates a new timestamped ingestion folder rather
than overwriting the last one.

## 4. The one thing you can't fix by editing `.env` and restarting

`NEXT_PUBLIC_API_URL` (the backend URL the **browser** calls, not
container-to-container traffic) gets baked into the frontend's JS bundle
at *build* time — Next.js does this for every `NEXT_PUBLIC_*` variable,
it's not something this project's Dockerfile chose. Changing it in `.env`
and restarting does nothing; you have to rebuild:

```bash
NEXT_PUBLIC_API_URL=https://your-real-backend-host:8000 docker compose build frontend
docker compose up -d frontend
```

## 5. Scaling the backend past one worker

`WEB_CONCURRENCY` in `.env` (default `1`) controls how many `uvicorn`
worker processes the backend runs. Before raising it, know the tradeoff:
`services/state.py` holds the currently-selected ingestion as **mutable
global state**, swapped per-request by `ensure_ingestion_loaded()`, not
scoped to that request.

- **Safe:** separate worker *processes* — each has its own independent
  copy of this state.
- **Not safe:** two requests against *different* ingestions landing on
  the *same* worker's event loop at the same time — one can start
  querying the other's ingestion mid-request.

Raising `WEB_CONCURRENCY` adds independent processes (fine) but doesn't
fix the intra-worker race. If your real usage pattern has people
concurrently querying different ingestions at once, that's worth fixing
properly (request-scoped state via `contextvars`) before you scale
traffic on it.

## 6. Optional: Redis (only for multiple backend replicas)

A single `backend` container (the default) doesn't need this — the live
run event stream and live-frame cache work fine in-process. Only relevant
if you run more than one backend instance behind a load balancer:

```bash
docker compose --profile multi-instance up --build
```

Then set `REDIS_URL=redis://redis:6379` in `.env` so all replicas share
live-run state.

## 7. Rebuilding after you change code

```bash
docker compose up -d --build backend    # after Python changes
docker compose up -d --build frontend   # after frontend changes
docker compose up -d --build            # both
```

Only changed layers rebuild. Python dependency layers (torch,
sentence-transformers — the slow ones) stay cached unless
`requirements.txt` itself changed, so a code-only backend rebuild takes
seconds, not minutes.

## 8. Publishing images so teammates don't need to build

The images already contain **no data and no secrets** — see "What never
gets baked into the images" below; this section is just about getting the
already-clean image onto Docker Hub so people can `pull` it instead of
cloning the repo and waiting for a build.

### 8a. One-time: log in and make sure the repos exist

```bash
docker login -u jaydeepjoshi9403
```

Docker Hub auto-creates a repo (as **public**, on the free plan) the first
time you push a tag that doesn't exist yet — nothing to create by hand on
hub.docker.com first. If you'd rather set visibility explicitly, or you want
these **private** instead, create `sentinel-qa-backend` and
`sentinel-qa-frontend` under your account on Docker Hub before the first
push and pick the visibility there. Private repos need every consumer added
as a Collaborator (or org Team member) before `pull` works — see
`DOCKERHUB.md` §2 for the exact steps and for what the failure looks like
when someone hasn't been granted access yet.

### 8b. Build and push

```bash
docker compose build backend frontend
docker compose push backend frontend
```

This builds using the `image:` tags already set in `docker-compose.yml`
(`jaydeepjoshi9403/sentinel-qa-backend:latest`,
`jaydeepjoshi9403/sentinel-qa-frontend:latest`) and pushes both. Re-run
this any time you want to publish a new version — `latest` moves to
whatever you just built. To publish a *pinned* version instead of moving
`latest`:

```bash
IMAGE_TAG=v1.2.0 docker compose build backend frontend
IMAGE_TAG=v1.2.0 docker compose push backend frontend
```

Note the frontend image bakes in `NEXT_PUBLIC_API_URL` at build time (§4).
The default (`http://localhost:8000`) is exactly right for teammates who
run the stack on their own machine with the default ports — their own
browser calls their own `localhost:8000`, not yours. Only override it if
you're publishing an image meant to point at one shared backend URL.

> **Everything a teammate needs to know as a Docker Hub *consumer*** —
> condensed `.env` reference, public-vs-private pull steps, feature
> gotchas, and how to wire a Playwright project's live-run reporter up to a
> Dockerized backend — is written up in **`DOCKERHUB.md`**, formatted to be
> pasted directly into the Docker Hub repo's Overview/Description field.
> This section stays focused on the maintainer side: building, tagging,
> pushing, and access control.

### 8c. What a teammate does — no clone required

They need exactly two files, not the repo:

```bash
curl -O https://raw.githubusercontent.com/jaydeep9075/sentinel-qa-analytics-dashboard/main/docker-compose.pull.yml
curl -O https://raw.githubusercontent.com/jaydeep9075/sentinel-qa-analytics-dashboard/main/.env.example
cp .env.example .env   # fill in section A/B - see .env.example
docker compose -f docker-compose.pull.yml pull
docker compose -f docker-compose.pull.yml up -d
```

`docker-compose.pull.yml` is a trimmed copy of `docker-compose.yml` with
every `build:` block removed — `image:` only, so there's nothing there that
needs source code. `DATA_DIR`/`STATE_DIR`/`INGEST_SOURCE_DIR` (§ env
reference, section D below) still default to plain folders next to that
file on **their** machine, and can point at any disk, network share, or
cloud-mounted volume they choose — nothing from your machine or your data
travels with the image. Two people running this independently get two
completely separate, empty datasets and two separate admin accounts unless
they deliberately point `DATA_DIR`/`STATE_DIR` at the same shared storage.

### 8d. Publishing a version bump later

Same as 8b — build, push, and anyone who already ran the stack picks it up
with:

```bash
docker compose -f docker-compose.pull.yml pull
docker compose -f docker-compose.pull.yml up -d
```

### 8e. The single combined image (`Dockerfile.allinone`)

Alongside the split images, `jaydeepjoshi9403/sentinel-qa` packages backend
+ frontend into one image (both processes supervised by `supervisord` inside
one container) for teammates who want the absolute simplest pull-and-run
path. See `Dockerfile.allinone`'s header comment for the full tradeoff
against the split images (independent restarts/resource limits/scaling vs.
one image, one command). Build and push it the same way:

```bash
docker compose -f docker-compose.allinone.yml build
docker compose -f docker-compose.allinone.yml push
```

Uses the same `IMAGE_NAMESPACE`/`IMAGE_TAG` vars as the split images (§8b),
just a different compose file and a different image name. Teammates run it
with `docker-compose.pull.allinone.yml` — see `DOCKERHUB.md` §1b.

**Note on build context:** `Dockerfile.allinone` needs `frontend/` in its
build context, but the root `.dockerignore` excludes that directory
entirely (the split `services/Dockerfile` never needs it). BuildKit resolves
a Dockerfile-specific ignore file when one exists
(`<dockerfile>.dockerignore` overrides the plain `.dockerignore` for that
build), which is what `Dockerfile.allinone.dockerignore` is for — if you
rename `Dockerfile.allinone`, rename its ignore file to match, or the build
will fail with a "not found" error on `COPY frontend/`.

## Environment variable reference

Three different things read env vars here, and they behave differently —
this is the part that trips people up.

### A. Backend runtime (`.env` → `env_file` → the container)

Read by `services/config.py` when the backend starts. Change one, run
`docker compose up -d backend`, done — no rebuild.

| Variable | Default | What it does |
|---|---|---|
| `SECRET_KEY` | *(none — required)* | JWT signing key, must be ≥32 chars. App refuses to start without it. |
| `LLM_PROVIDER` | `gemini` | Any litellm provider. `gemini`/`openai`/`anthropic`/`ollama` have built-in default models; others must set `LLM_MODEL`. |
| `LLM_API_KEY` | *(fallback only)* | LLM credential. The active provider's own variable (`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `<PROVIDER>_API_KEY`, …) takes precedence. Required unless the provider is keyless (`ollama`/`bedrock`/`vertex_ai`) or `LLM_API_BASE` is set. |
| `LLM_MODEL` | `models/gemini-2.5-flash` | Full model ID |
| `LLM_API_BASE` | *(empty)* | Only for proxies/self-hosted gateways |
| `OLLAMA_URL` | `http://localhost:11434` | ⚠️ `localhost` means *inside the container*. Use `http://host.docker.internal:11434` to reach Ollama on your host. |
| `BCRYPT_ROUNDS` | `12` | Password hash cost |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated. Must contain the frontend's origin or every browser call fails. |
| `AUTH_BACKEND` | `db` | `db` (SQLite `users.db`) or `memory` (wiped on restart) |
| `AUTH_USER_STORE_URL` | `sqlite:///./users.db` | Override only if not using the bind-mounted SQLite file |
| `AUTH_AUTO_SEED_USERS` | `false` | If `true`, also uncomment the `auth_seed_users.json` mount in `docker-compose.yml` |
| `LIVE_INGEST_API_KEY` | *(auto-generated)* | Shared secret for the Playwright reporter's `x-api-key`. Left unset, one is generated into `state/live_ingest_api_key` and logged once at startup — use that value as `SENTINEL_API_KEY` in reporting repos. Set it explicitly to pick your own, or to share one value across replicas that don't share a state directory. |
| `REDIS_URL` | *(empty)* | Only for >1 backend replica (see §6) |
| `INGEST_MAX_FILE_SIZE_BYTES` | `209715200` (200MB) | Raise if your Allure zips are bigger |
| `INGEST_MAX_ROWS` | `500000` | Per-ingestion row cap |
| `INGEST_TIMEOUT_SECONDS` | `600` | Ingestion hard timeout |
| `SENTINEL_DATA_DIR` | `<repo>/data` | Where ingestions are read/written. Compose pins it to `/app/data`; set it directly when running the image outside compose (k8s, ECS, plain `docker run`). |
| `AUTO_INGEST_ENABLED` | `false` | Watch the drop-box and ingest new arrivals automatically |
| `AUTO_INGEST_DIR` | `<repo>/ingest-source` | Watched folder. Compose pins it to `/app/ingest-source`. |
| `AUTO_INGEST_INTERVAL_SECONDS` | `30` | Rescan interval |
| `AUTO_INGEST_STABLE_SECONDS` | `20` | How long a file's size must hold steady before it's ingested (guards against half-written uploads). Clamped up to one scan interval. |
| `AUTO_INGEST_DEFAULT_WORKSPACE` | `default` | Workspace for files at the top level of the drop-box. A file under `<drop-box>/<team>/` goes to `<team>` if that workspace exists. |
| `INGEST_API_KEYS` | *(empty)* | `key:workspace` pairs for `POST /ingest/upload`. The key fixes the workspace. |
| `INGEST_UPLOAD_MAX_BYTES` | `524288000` | Cap on a single upload (500MB), enforced while streaming. |
| `BOOTSTRAP_ADMIN_USERNAME` | `admin` | First admin's username, created only when the user table is empty. |
| `BOOTSTRAP_ADMIN_PASSWORD` | *(auto-generated)* | Left unset, one is generated into `state/bootstrap_admin_password` and logged once at startup — no fixed "admin"/"admin" default. Forced password change on first login either way. |
| `AUTH_ALLOW_SELF_REGISTRATION` | `true` | Enable `/register`. New accounts are pending until approved. |
| `AUTH_AUTO_APPROVE_REGISTRATION` | `false` | Skip approval — registrations go straight to active. Trusted networks only. |
| `AUTH_DEFAULT_ROLE` | `sdet` | Role given on approval when unspecified. |
| `AUTH_DEFAULT_WORKSPACE` | `DEFAULT_WORKSPACE_ID` | Workspace given on approval when unspecified. |
| `LEGACY_BUILDS_WORKSPACE` | `DEFAULT_WORKSPACE_ID` | Workspace that builds with no ownership record count as. |
| `WEB_CONCURRENCY` | `1` | uvicorn workers — read §5 before raising |
| `HF_HOME` / `HF_HUB_OFFLINE` | `/opt/hf-cache` / `1` | Set in the Dockerfile. The `all-MiniLM-L6-v2` embedding model is baked into the image, so nothing is downloaded at runtime and the backend works with no outbound network. Only override if you switch models. |

### B. Frontend runtime (set in `docker-compose.yml`, not `.env`)

| Variable | Value | Why |
|---|---|---|
| `SENTINEL_DATA_DIR` | `/app/data` | Where `/api/builds` (the Build Trends page) looks for ingestion folders. From a plain checkout the code defaults to `../data`, which doesn't exist inside the container. |
| `SENTINEL_STATE_DIR` | `/app/state` | Mounted directory holding `users.db` and `config2.json`. |
| `SENTINEL_CONFIG2_PATH` | `/app/state/config2.json` | The file `/api/config2-path` reads/writes for the dashboard's path box. Same reason. |

### C. Build-time only (`docker compose build`)

| Variable | Default | Why it's different |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Next.js **inlines** this into the client JS bundle at build time. Editing `.env` and restarting does nothing — see §4. This is the URL your *browser* hits, so it must be reachable from your machine, not from inside the Docker network (`http://backend:8000` will **not** work here). |

### D. Compose-only knobs (read from `.env` by compose itself)

`BACKEND_PORT` (8000), `FRONTEND_PORT` (3000), `REDIS_PORT` (6379) — host
ports. Change these if something else already owns the port.

Host-side mount paths — the container-side paths are fixed, so these are what
you change to put storage on another disk, a cloud volume, or a network share.
No rebuild needed; see [SETUP.md §6](SETUP.md#6-moving-where-data-lives-cloud-or-another-disk).

| Variable | Default | Mounted at |
|---|---|---|
| `DATA_DIR` | `./data` | `/app/data` |
| `STATE_DIR` | `./state` | `/app/state` |
| `INGEST_SOURCE_DIR` | `./ingest-source` | `/app/ingest-source` |

## Where your data lives

Nothing important lives inside a container. Everything below is a bind
mount to the host, so `docker compose down`, image rebuilds, and container
recreation never destroy it.

| Host path | Mounted into | Contents |
|---|---|---|
| `./data/` | backend `/app/data` (rw), frontend `/app/data` (**ro**), ingest `/app/data` (rw) | Everything generated: `ingestion_*/` folders (LanceDB vectors + DuckDB tables + `summary.json`), `run_*/` finalized live runs, `live_runs.db`, `token_usage_store.json`. Chat and chart history live in LanceDB tables inside each ingestion folder. |
| `./state` | backend + frontend + ingest `/app/state` (rw) | `users.db` (accounts) and `config2.json`. A directory mount, created and seeded automatically. |
| `./ingest-source/` | backend + ingest `/app/ingest-source` (rw) | Your drop-box for raw data to import. `.gitignore`'d. |
| `./.env` | backend (via `env_file`) | Secrets/config — injected as environment, never copied into the image. |

**Backup = copy `data/` and `users.db`.** That's the whole state of the
system.

Two consequences worth knowing:

- The frontend gets `data/` **read-only** on purpose — only the backend
  and the ingester write there, so a frontend bug can never corrupt an
  ingestion.
- Because `data/` is a bind mount shared with the host, the older
  non-Docker workflow (`cd universal_ingester && python ingester.py` in a
  local venv) writes to the *same* folder the container reads. Both
  approaches can coexist; you don't have to migrate anything.

## What never gets baked into the images

Per `.gitignore`/`.dockerignore`: `.env`, `config.json`, `config2.json`,
`auth_seed_users.json`, `users.db`, `data/`, `ingest-source/`. All
secrets/runtime state, supplied via `env_file` and bind mounts instead —
none of it belongs in a portable image.

## Troubleshooting

- **Frontend can't reach the backend from your browser**: check
  `NEXT_PUBLIC_API_URL` was set correctly at *build* time (§4) and that
  `CORS_ALLOWED_ORIGINS` in `.env` includes the frontend's origin
  (`http://localhost:3000` by default).
- **Backend won't start, complains about `SECRET_KEY`**: it must be
  ≥32 characters — see §1a.
- **`docker compose run --rm ingest` can't find your file**: the `path`
  in `config2.json` must be the *container* path
  (`/app/ingest-source/...`), not your Windows path.
- **`users.db` bind mount error on first run**: see §1b — the file must
  exist on the host before the container starts. Same applies to
  `config2.json` (§1c). If Docker already created a *directory* where the
  file should be, delete it (`rm -rf users.db`), create the file, and
  bring the stack back up.
- **Can't log in / "Invalid credentials"**: no accounts exist yet in
  `users.db` — see §1d.
- **Build Trends page shows no builds**: the frontend reads
  `SENTINEL_DATA_DIR`. Confirm the mount is live:
  `docker compose exec frontend ls /app/data` should list your
  `ingestion_*` folders.
- **"Add Build" fails with a path error**: you typed a Windows path. The
  backend only sees what's mounted — use
  `/app/ingest-source/<your-file>` and make sure the file is really in
  `ingest-source/` on the host
  (`docker compose exec backend ls /app/ingest-source`).
- **Using Ollama on the host**: `OLLAMA_URL=http://localhost:11434` points
  at the *container*, which has no Ollama. Use
  `http://host.docker.internal:11434`.
- **Backend takes ~30-45s on its first request after start**: that's
  LanceDB/DuckDB opening the selected ingestion, not a model download —
  the embedding model is baked into the image. The healthcheck's
  `start_period` already accounts for it.
