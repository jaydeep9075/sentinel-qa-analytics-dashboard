# TR-Insight — AI-Powered Test Analytics Dashboard

**AI QE that knows your results.**

TR-Insight ingests the test results your team already produces — Allure reports,
spreadsheets, an existing database, an HTTP API, or a live Playwright/Cypress run —
and lets you ask questions about them in plain English, with AI-generated charts and
a defensible release call.

Two things run: a **FastAPI backend** on `:8000` and a **Next.js dashboard** on `:3000`.
Data lands in **LanceDB** (vector search) and **DuckDB** (SQL analytics), stored per-build
under `data/`.

---

## Project structure

```
.
├── services/                  FastAPI backend (the API + all business logic)
│   ├── main.py                App entry point; all HTTP routes except /live/*
│   ├── config.py              Env-var resolution; read once at import
│   ├── app_settings.py        Runtime-editable settings (LLM, embedding, SECRET_KEY)
│   ├── auth.py                JWT login, bcrypt hashing, bootstrap admin
│   ├── handlers.py            Chat/chart SQL generation and LLM prompting
│   ├── data_loader.py         Ingestion handling, DuckDB/LanceDB warm pool
│   ├── live_exec/             Live test-run API (APIRouter, prefix /live)
│   └── ...
├── universal_ingester/        Ingestion engine (CLI + imported by the backend)
│   ├── ingester.py            Orchestrator and CLI entry point
│   ├── connectors/            allure, file, db, api, live_run
│   ├── core/                  storage, normalizer, chunking, report
│   └── schema/                Runtime schema/type detection
├── frontend/                  Next.js 16 App Router dashboard
│   ├── app/                   Routes (dashboard, admin, projects, runs, login)
│   ├── components/            React components
│   ├── lib/                   API client, contexts, voice, theming
│   └── types/                 Shared TS types
├── packages/sentinel-qa-reporter/  npm package installed in YOUR test repo
├── tests/                     pytest suite (the only one pytest collects)
├── scripts/                   Standalone dev/diagnostic scripts
├── roles/                     LLM persona prompts, loaded at runtime
├── docs/                      Deep-dive documentation (see table below)
├── terraform/                 Single-VM AWS deployment
├── data/                      Ingestion output      (gitignored)
├── state/                     users.db, config2.json (gitignored)
└── ingest-source/             Drop-box for raw data (gitignored)
```

| Doc | What's in it |
|---|---|
| [`docs/01-overview.md`](docs/01-overview.md) | What TR-Insight is, architecture at a glance |
| [`docs/02-getting-started.md`](docs/02-getting-started.md) | Install and first run — Docker or local dev |
| [`docs/03-architecture-guide.md`](docs/03-architecture-guide.md) | Modules, data flow, chart/chat pipelines, live execution |
| [`docs/04-marketing.md`](docs/04-marketing.md) | Pitch, personas, differentiators |
| [`docs/05-docker.md`](docs/05-docker.md) | Images, compose files, build/run |
| [`docs/06-hosting-and-resources.md`](docs/06-hosting-and-resources.md) | Sizing, storage layout, full env-var reference, scaling |
| [`docs/07-user-guide.md`](docs/07-user-guide.md) | Accounts, ingestion, chat, charts, live runs, admin console |
| [`docs/08-split-hosting-and-production-readiness.md`](docs/08-split-hosting-and-production-readiness.md) | Split hosting, production hardening log |

`CLAUDE.md` is the AI-agent brief for this repo, not user documentation.

---

## Setup

### Docker (recommended)

```bash
cp .env.example .env
docker compose up --build -d
```

Dashboard: http://localhost:3000 · API docs: http://localhost:8000/docs

An empty `.env` still produces a working deployment — the JWT key and first admin
password self-generate. The generated password is printed once in
`docker compose logs backend`, and a password change is forced on first login.

### Local development

```bash
python -m venv venv
.\venv\Scripts\activate                      # Linux/macOS: source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env

cd frontend && npm install && cp .env.example .env.local && cd ..
```

Requires Python 3.12+ and Node 24+.

---

## Environment variables

There is **one** `.env` at the repo root and it configures both services.
`frontend/.env.local` exists only for running `npm run dev` directly.
Never hardcode credentials — everything below is read from the environment.
See [`.env.example`](.env.example) for the annotated full list and
[`docs/06-hosting-and-resources.md`](docs/06-hosting-and-resources.md) for the reference table.

### API keys and secrets

| Variable | Required | Purpose |
|---|---|---|
| `LLM_API_KEY` | For AI features | Provider credential. Can instead be set at runtime in **Admin → Settings**. |
| `SECRET_KEY` | No | JWT signing key (32+ chars). Auto-generated into `state/secret_key` if blank. |
| `BOOTSTRAP_ADMIN_PASSWORD` | No | First admin password. Auto-generated if blank; change forced on first login. |
| `LIVE_INGEST_API_KEY` | No | Shared key for test reporters. Auto-generated; read it from **Live Runs → Connect a repo**. |
| `INGEST_API_KEYS` | No | Machine keys for `POST /ingest/upload`, as `key1:workspace1,key2:workspace2`. |

### Commonly changed

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | — | `openai`, `anthropic`, `gemini`, `ollama`, or any litellm provider |
| `LLM_MODEL` | per provider | Model id |
| `LLM_API_BASE` | — | Gateway/proxy URL |
| `VOICE_PROVIDER` | `auto` | `auto` \| `gemini` \| `openai` \| `browser` |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Sentence-transformers model |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Frontend origins |
| `SENTINEL_DATA_DIR` | `./data` | Ingestion output root |
| `SENTINEL_STATE_DIR` | `./state` | Auth DB, config2.json, generated secrets |
| `AUTO_INGEST_ENABLED` | `false` | Watch `AUTO_INGEST_DIR` and ingest dropped files |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Frontend → backend origin (**build-time** for Docker) |

> `.env` is gitignored and must stay that way. Commit changes to `.env.example` only.
> `config.json`, `auth_seed_users.json`, `state/`, and `data/` are gitignored too.
> `.env` edits require a backend restart — `config.py` reads the environment at import.

---

## Running

### Backend + dashboard together

```bash
docker compose up -d                       # both services
```

Locally, in two terminals:

```bash
python -m services.main                    # backend  :8000  (no --reload; restart manually)
cd frontend && npm run dev                 # dashboard :3000
```

### Ingest

Ingestion is a separate one-shot process. It writes into `data/`, which a running
backend picks up immediately — no restart needed.

```bash
# 1. Drop raw data (Allure zip, CSV, JSON, ...) into ingest-source/
# 2. Point state/config2.json at it (seeded on first backend start)
# 3. Run one of:

docker compose run --rm ingest             # Docker
docker-ingest.bat                          # Windows wrapper for the above

cd universal_ingester && python ingester.py    # local
```

Other ways in: **Add Build** in the dashboard (`POST /ingest/build`),
`POST /ingest/upload` with a machine key from CI, or set `AUTO_INGEST_ENABLED=true`
to have `ingest-source/` watched continuously.

### Live runs

"Live" streams a Playwright or Cypress run into the dashboard while it is still
running. Install [`sentinel-qa-reporter`](packages/sentinel-qa-reporter/README.md)
in **your test repo**, then:

```bash
SENTINEL_URL=http://localhost:8000 \
SENTINEL_API_KEY=<from Live Runs → Connect a repo> \
SENTINEL_DASHBOARD_URL=http://localhost:3000 \
  npx playwright test
```

Watch it at http://localhost:3000/runs/live.

---

## Adding an API

**Backend.** Routes are defined on the FastAPI app in [`services/main.py`](services/main.py):

```python
@app.get("/my/endpoint")
async def my_endpoint(user: dict = Depends(get_current_user)):
    require_permission(user, PERM_VIEW_DATA)
    ...
```

- Protect it with `Depends(get_current_user)` and a `require_permission(...)` /
  `require_admin(...)` check from [`services/permissions.py`](services/permissions.py).
- For a cohesive feature area, add an `APIRouter` in its own package and
  `app.include_router(...)` it — `services/live_exec/` is the existing example.
- Add the endpoint's env knobs to `services/config.py` **and** `.env.example`.
- Add a test under `tests/`.

**Frontend.** Add the call to [`frontend/lib/api.ts`](frontend/lib/api.ts), which already
handles `API_BASE`, the auth token, the `x-ingestion-id` header, timing and caching.
Do not call `fetch` with a hardcoded URL from a component.

**Ingestion source.** Add a connector under `universal_ingester/connectors/` that
subclasses `BaseConnector` and yields `name` / `type` / `data` / `metadata`, then
register it in `universal_ingester/ingester.py`.

---

## Commands

| Command | What it does |
|---|---|
| `docker compose up -d` | Start backend + frontend |
| `docker compose down` | Stop everything |
| `docker compose run --rm ingest` | One-shot ingestion |
| `docker compose logs -f backend` | Tail backend logs |
| `python -m services.main` | Run the backend locally on `:8000` |
| `python -m services.admin_users init-db` | Create the auth database |
| `python -m services.admin_users create-user --username admin --role cto` | Create a user |
| `python -m services.admin_users reset-password --username admin` | Reset a password |
| `cd universal_ingester && python ingester.py` | Run an ingestion locally |
| `python scripts/verify_system.py` | Dependency / storage / import sanity check |

Windows wrappers: `docker-start.bat`, `docker-stop.bat`, `docker-ingest.bat`.

### Test, lint, build

```bash
# Backend
python -m pytest tests/ -q                                   # full suite
python -m pytest tests/test_chart_pipeline.py -v              # one file
python -m ruff check services universal_ingester tests scripts

# Frontend (from frontend/)
npm run lint
npx tsc --noEmit
npm run build
```

CI runs the same backend lint + tests and the frontend lint on every PR
(`.github/workflows/docker-publish.yml`).
