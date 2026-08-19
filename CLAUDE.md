# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start Commands

### Environment Setup
```bash
# Python virtual environment (Windows)
python -m venv venv
venv\Scripts\activate

# Python (macOS/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install python-jose[cryptography] bcrypt
```

### Backend
```bash
# Start API server (from repo root, activates venv)
python -m services.main

# Initialize auth database
python -m services.admin_users init-db

# Create test user
python -m services.admin_users create-user --username admin --role cto

# Reset password
python -m services.admin_users reset-password --username admin

# List users
python -m services.admin_users list-users
```

### Frontend (in `frontend/` directory)
```bash
# Install dependencies
npm install

# Start dev server (auto-regenerates builds.json via predev script)
npm run dev

# Production build
npm build

# Start production server
npm start

# Lint
npm run lint
```

### Data Ingestion
```bash
# Ingest Allure results (uses config2.json)
cd universal_ingester
python ingester.py
```

### Tests
```bash
# Run all tests
python -m pytest tests/ -q

# Chart pipeline (intent parsing + figure construction) and chat helpers
python -m pytest tests/test_chart_pipeline.py tests/test_chat_helpers.py -v

# Run adaptive ingestion tests
python -m pytest tests/test_adaptive_ingestion.py -v

# Run specific test file
python test_edge_cases.py
python test_full_pipeline.py

# Run verification system checks
python verify_system.py
```

## Architecture Overview

**Sentinel QA Analytics** is a full-stack AI-powered test analytics platform with three main layers:

### Backend (FastAPI + Python)
- **Entry Point**: `services/main.py` — FastAPI app with CORS, auth routes, API endpoints
- **Core Modules**:
  - `auth.py` — JWT login, password hashing (bcrypt), user store (SQLite or memory)
  - `data_loader.py` — Loads ingested LanceDB/DuckDB tables; abstracts test results queries
  - `handlers.py` — Chat and chart request processing; prompt templates, LLM calls
  - `chart_spec.py` — Deterministic chart-intent parser (no LLM): chart form,
    measure, dimension, breakdown, top-N, sort direction, filters
  - `chart_builder.py` — Deterministic Plotly figure construction from a ChartSpec
  - `chart_theme.py` — Validated colour palette + both-mode theme payload
  - `llm_client.py` — LLM abstraction (Gemini, OpenAI, Anthropic, Ollama) with unified interface
  - `memory.py` — Chat and chart history storage; session management
  - `ingestion_service.py` — Orchestrates Allure → LanceDB pipeline
  - `role_manager.py` — Loads persona instructions from `roles/*.md`
  - `project_manager.py` — Loads project context from `projects/*.md`
  - `query_executor.py` — Executes adaptive SQL queries against DuckDB
  - `rag_service.py` — Semantic retrieval of historical context
  - `schema_context.py` — Generates schema summaries for LLM prompt context

**Data Flow**: Allure JSON → `universal_ingester/` → LanceDB (vector embeddings) + DuckDB (analytics queries) → API → Frontend

### Frontend (Next.js 16 + React 18 + TypeScript)
- **App Structure**: 
  - `app/page.tsx` — Landing page
  - `app/login/` — Login UI with JWT token storage
  - `app/dashboard/` — Main analytics UI
  - `app/build-trends/` — Multi-build comparison charts
  - `app/api/` — Route handlers for builds.json, config2-path
- **Key Components**:
  - `FloatingChat.tsx` — Conversational AI interface
  - `AIGeneratedChart.tsx` — Dynamic chart rendering from LLM output
  - `BuildTrendCharts.tsx` — Multi-build trend analysis
  - `IngestionSelector.tsx`, `RoleSelector.tsx`, `ProjectSelector.tsx` — Context pickers
- **API Client**: `lib/api.ts` — Axios wrapper with Bearer token auth

**Theme**: Tailwind CSS 4 + dark/light mode toggle (ThemeInitializer.tsx)

### Live Execution (`services/live_exec/` + `packages/sentinel-qa-reporter/`)
Streams a test run to `/runs/live` while it is still running, then folds it
into normal history. **Framework-agnostic by contract** — four plain HTTP
calls (`POST /live/runs`, `POST /live/runs/{id}/events`, optional attachment
upload, `PATCH /live/runs/{id}`), and `framework` is free text. Don't
reintroduce Playwright-specific wording into the UI or the schemas.

- **One client package, both frameworks**: `sentinel-qa-reporter` ships a
  framework-neutral `src/core/` (HTTP client, CI detection, config
  resolution, redaction) plus `src/playwright/` and `src/cypress/` adapters,
  exposed as subpath exports. The Cypress adapter is two halves — a node
  plugin and a browser support file — bridged over `cy.task`; the browser half
  is gated on a flag the node half sets, so an unconfigured repo never calls
  the task and reporting cannot fail a test. Their shared constants live in
  `cypress/constants.ts` precisely because the support file is bundled *for
  the browser* and must not pull `node:fs` in.
- **The client never fails a run.** Every request has a deadline, the event
  queue has a ceiling and sheds log lines before test results, `finish()` is
  idempotent, and the worst available outcome is one `[sentinel]` warning.
  Covered by `packages/sentinel-qa-reporter/test/`.
- **Repo setup is one call**: `withSentinel(config)` appends the reporter and
  injects `--remote-debugging-port` into the top-level *and every Chromium
  project's* `launchOptions.args`. That last part is the whole reason the
  helper exists — Playwright *replaces* rather than merges project-level
  `launchOptions`, so hand-wiring silently breaks live view in any repo whose
  projects set their own args.
- **Hot layer**: SQLite WAL (`store.py`) for in-progress runs only;
  `finalize/job.py` promotes a finished run into LanceDB and deletes the hot
  rows. Abandoned runs are swept by `store.reap_stale_runs`.
- **Sharding**: `external_id` attaches several runner processes to one run
  (`store._join_existing`), summing `total_tests`/`worker_count` and counting
  `active_runners`. `update_run_status` decrements that count and returns
  `True` only for the last runner out, so an early shard cannot finalize a run
  the others are still writing to; an early failure is parked in
  `pending_status` so `status` keeps reading `running` for viewers.
- **Push**: in-process pub/sub (`bus.py`) → SSE. Multi-replica needs `REDIS_URL`.
- **Distribution**: the Docker images build the package tarball in a
  `reporter-builder` stage and the backend serves it at `GET /live/package`
  (unauthenticated — public client code, and `npm install` carries no JWT;
  the filename is whitelisted against the one file present rather than
  sanitised). So a team that pulls the image installs a client that matches
  their server by construction, with no npm registry involved.
- **Key distribution**: `GET /live/connection-info` (admin-only) serves this
  install's ingest key, a request-derived base URL and the exact install
  command, rendered as copy-paste snippets under **Live Runs → Connect a
  repo**. `POST /live/connection-info/rotate` reissues it without a restart,
  and 409s when the key is pinned in the environment.

### Universal Ingester (`universal_ingester/`)
- **Connectors**: Allure JSON, files, databases, APIs
- **Output**: Timestamped `data/ingestion_YYYYMMDD_HHMMSS/` folders with:
  - LanceDB tables (vector embeddings for semantic search)
  - DuckDB tables (analytics queries)
  - `summary.json` (metadata)

## Key Technology Decisions

### Authentication & Security
- **JWT + bcrypt**: `python-jose` for token generation, `bcrypt` for password hashing
- **User Store**: SQLite (default, `users.db`) or in-memory (config via `AUTH_BACKEND`)
- **Auto-Seeding**: Optional bootstrap from `auth_seed_users.json` via `AUTH_AUTO_SEED_USERS=true`
- **Secret Key**: If `SECRET_KEY` is unset, one is generated into `state/secret_key` on first
  start and reused after that (env always wins when set) — see `config._resolve_secret_key()`.
- **Live ingest key**: If `LIVE_INGEST_API_KEY` is unset, one is generated into
  `state/live_ingest_api_key` and logged once at startup (same pattern as `SECRET_KEY`) — see
  `config._resolve_live_ingest_api_key()`. `services/live_exec/router.py`'s `require_ingest_key`
  only falls back to "unauthenticated" if generation itself fails (unwritable state dir).
- **Zero-config first run**: `BOOTSTRAP_ADMIN_USERNAME` defaults to `admin`. `BOOTSTRAP_ADMIN_PASSWORD`,
  if unset, is generated into `state/bootstrap_admin_password` and logged once at startup — there
  is no fixed `admin`/`admin` default anymore (see `config._resolve_bootstrap_admin_password()`).
  That account is created with `must_change_password=true`, and
  `main.credential_change_middleware` refuses every route except `/auth/me`,
  `/auth/permissions`, `POST /auth/account/password` and `POST /auth/account/username` until it's
  cleared — the default password is a one-time door, not a standing credential. An admin
  password reset (`POST /admin/users/{u}/password`) can set the same flag via `force_change`
  (default true).
- **Roles vs. permissions**: `services/permissions.py` is the source of truth for what a role
  (`admin`/`cto`/`qa-manager`/`qa-engineer`/`developer`/`viewer`) may do — `data.view`,
  `data.ingest`, `data.delete`, `usage.view_own`/`usage.view_all`, `users.manage`,
  `settings.manage`, `audit.view`. `admin`/`cto` are wildcard-everything. `require_permission()`
  is a FastAPI dependency factory; `GET /auth/permissions` is what the frontend gates on instead
  of hardcoding role-name checks. Not to be confused with `roles/*.md` (`role_manager.py`), which
  are LLM chat personas selected per-request via `x-role` — a completely different "role".
- **Token quotas**: `users.token_limit` (0 = unlimited), enforced in `main._enforce_token_quota()`
  at the top of `/chat` and `/chart`, checked *before* any LLM call. Compared against
  `token_usage_store.get_lifetime_total()` — account-wide across workspaces, not per-workspace.
- **Audit log**: `services/audit_log.py`, append-only, `GET /admin/audit`. Records logins,
  registrations, user/role/settings edits, credential changes, build deletions.

### LLM Integration
- **Provider Abstraction**: `llm_client.py` — any provider litellm supports, not just a fixed list
- **Three-tier config resolution** (`services/app_settings.py`), decided **per field**:
  **env > database > built-in default**. A field pinned in `.env` is locked and can't be
  overridden from the admin UI (`config.LLM_PROVIDER_FROM_ENV` etc. record which fields env
  claimed at import time); otherwise an admin can set/change it live from **Admin → Settings**
  (`GET`/`PUT /admin/settings/llm`, `POST /admin/settings/llm/test` for a real one-shot
  connectivity check) with no restart — `llm_client.LLMClient` reads `app_settings.get_llm_settings()`
  fresh on every call rather than caching provider/model at construction time.
  - `LLM_PROVIDER` (gemini | openai | anthropic | ollama | any litellm provider)
  - `LLM_API_KEY` — Universal key; falls back to provider-specific vars (OPENAI_API_KEY, GEMINI_API_KEY, etc.)
  - `LLM_MODEL` — Full model ID (e.g., `models/gemini-2.5-flash`)
  - `OLLAMA_URL` — Local inference endpoint (if using Ollama)
- **Not a startup requirement**: an unconfigured LLM no longer prevents the backend from starting
  (`config.validate_runtime_config()` dropped the LLM checks; `config.validate_llm_config()` is
  the reusable validator called from both the Settings-tab save path and the old startup path
  used to call). Chat/chart requests fail clearly (`LLMNotConfiguredError`) instead.
- **Context Management**: Role/project personas injected via `x-role`, `x-project` headers

### Chart Generation Pipeline
Charts are built **deterministically**; the LLM's only job is writing SQL.

```
prompt → chart_spec.parse()      intent: form, measure, dimension, breakdown,
                                 top-N, direction, filters (regex, no LLM)
       → CHART_SQL_PROMPT        LLM writes SQL, constrained by the parse via
                                 handlers._spec_sql_directives()
       → execute + repair loop   fallback map, then one LLM repair with the error
       → chart_spec.reconcile()  can the returned data support the requested
                                 form? downgrade if not (400-slice pie, 2-point
                                 "trend", scatter with one measure)
       → chart_builder.build_figure()
```
- **17 chart forms**: bar, stacked_bar, horizontal_bar, line, area, pie, donut,
  scatter, bubble, heatmap, treemap, sunburst, funnel, histogram, box, gauge,
  radar, plus `platform_comparison`.
- **Colour by job, never by rank** (`chart_theme.py`): categorical hues in fixed
  slot order; the reserved status palette (good/warning/serious/critical) only
  where colour genuinely means state; one hue light→dark for sequential. The
  palette is validated for colourblind separation in **both** themes — re-run
  `node scripts/validate_palette.js` (dataviz skill) before changing any hex.
  The previous palette failed: `#F59E0B`↔`#22C55E` sat at protan ΔE 5.7.
- **Theming is client-side.** The backend emits the light rendering plus both
  palettes and a per-trace `meta.slot` in `layout.meta.sentinel`;
  `frontend/lib/chartTheme.ts` remaps colour *by slot* on theme change, so a
  series keeps its identity. Never hardcode theme colours in a figure.
- Every figure carries an **insight subtitle** (computed from the drawn frame,
  so it can't drift from what's on screen), a **scope note** when truncated or
  filtered, and a **table-view twin** in `meta.sentinel.table`.
- `services/prompts.py` no longer generates Plotly code. `CHART_CODE_PROMPT`,
  `CHART_TEMPLATES` and `detect_chart_type()` were removed — do not reintroduce
  an `exec()` path for charts.

### Chat Answer Pipeline
- `CHAT_DECISION_PROMPT` returns `sql`, `sql_multi` (a labelled list of queries
  for multi-part questions), `vector`, or `answer`.
- `handlers._extract_json_object()` does a balanced-brace scan — the old
  `\{[^{}]+\}` regex could not match a nested decision object at all.
- `handlers._run_sql_with_repair()` feeds DuckDB's error back to the model
  before resorting to the keyword fallback map (a fallback answers a *simpler*
  question, so it must be last, not first).
- `handlers._dataset_facts()` computes sums/extremes/distributions over **all**
  rows and injects them, since only the first 50 rows are sent to the model.

### Data Storage
- **LanceDB**: Vector embeddings for semantic search (historical context retrieval)
- **DuckDB**: SQL analytics engine for aggregations, filters, trends
- **Multi-Table Fallback**: If new schema exists, queries fall back to old names for compatibility (`structured_test_results` → `flattened_tests`)

### Frontend Build Pipeline
- **Pre-build Script** (`scripts/generate-builds-json.js`): Runs on `npm install`, `npm run dev`, `npm run build`
- **Theme Persistence**: `data-theme` attribute on `<root>` (light | dark)
- **CORS**: Allowed origins in `.env` via `CORS_ALLOWED_ORIGINS`; dev-only IP allowlist in `frontend/next.config.ts`

## Project Structure Details

### Backend Structure
```
services/
├── main.py                   # FastAPI app, all routes
├── auth.py                   # JWT + user store
├── permissions.py            # Role → permission matrix, require_permission()
├── app_settings.py           # Runtime LLM settings (env > DB > default)
├── audit_log.py              # Append-only admin/auth action log
├── handlers.py                # Chat/chart logic
├── data_loader.py            # Query LanceDB/DuckDB
├── ingestion_service.py      # Allure ingestion orchestration
├── llm_client.py             # LLM abstraction
├── memory.py                 # Session/history storage
├── role_manager.py           # Persona loading (LLM chat personas — NOT user roles)
├── project_manager.py        # Project context
├── query_executor.py         # SQL execution + error handling
├── rag_service.py            # Semantic retrieval
├── schema_context.py         # Schema summarization
├── adaptive_query_builder.py  # Dynamic SQL construction
├── config.py                 # .env parsing + validation
├── state.py                  # Global state (DuckDB conn)
└── token_usage_store.py      # Token usage tracking + quota totals

universal_ingester/
├── ingester.py               # Entry point
├── connectors/
│   ├── allure_connector.py
│   ├── file_connector.py
│   ├── db_connector.py
│   └── api_connector.py
```

### Frontend Structure
```
frontend/
├── app/
│   ├── page.tsx              # Landing
│   ├── login/page.tsx        # Login UI
│   ├── dashboard/            # Analytics dashboard
│   ├── build-trends/         # Multi-build trends
│   ├── api/builds/route.ts   # builds.json endpoint
│   └── api/config2-path/     # config2.json path setter
├── components/
│   ├── FloatingChat.tsx       # AI chat UI
│   ├── AIGeneratedChart.tsx   # Chart rendering
│   ├── BuildTrendCharts.tsx   # Trend analysis
│   ├── RoleSelector.tsx       # Role/persona picker
│   ├── ProjectSelector.tsx    # Project context picker
│   └── ... (other UI components)
├── lib/
│   └── api.ts                # Axios client + Bearer auth
├── next.config.ts            # Dev IP allowlist
└── package.json
```

### Configuration Files
- **`.env`** — LLM config (provider, key, model), auth secrets, project/role paths
- **`config2.json`** — Allure ingestion source path + output directory
- **`frontend/.env.local`** — `NEXT_PUBLIC_API_URL` for backend connection
- **`auth_seed_users.json`** — Optional bootstrap users (must be `.gitignore`'d)

## Common Workflows

### Adding a New Ingestion Source
1. Create connector in `universal_ingester/connectors/my_connector.py`
2. Register in `universal_ingester/ingester.py`
3. Update `config2.json` with source type and path
4. Run ingester or use dashboard "Add Build" flow

### Modifying API Responses
- Edit prompts in `services/production_prompts.py` or `services/prompts.py`
- Pass role/project context via `x-role`, `x-project` headers
- Update `role_manager.py` or `project_manager.py` if loading new context files

### Debugging Data Issues
- Check LanceDB tables: `data/ingestion_YYYYMMDD_HHMMSS/` folder
- Verify DuckDB schema: `services/data_loader.py` queries
- Test queries manually against DuckDB: See `query_executor.py` for SQL patterns
- Review ingestion logs in `ingestion_service.py` for validation errors

### Testing Changes
- Unit tests in `tests/` (e.g., `test_adaptive_ingestion.py`)
- Integration tests: `test_full_pipeline.py`, `test_edge_cases.py`
- Manual verification: `verify_system.py` (checks dependencies, DB, API)
- Frontend: Start `npm run dev`, browse to http://localhost:3000

## Important Caveats

### Cache & Performance
- **Status Cache**: 10-second TTL on `/data/status` (see `_STATUS_CACHE_TTL_SECONDS`)
- **Quality Cache**: 20-second TTL on `/data/quality` (see `_QUALITY_CACHE_TTL_SECONDS`)
- **Schema Context**: Computed from table metadata and cached per ingestion_id for the process lifetime (`schema_context.py`, capped at 50 ingestions); first computation per ingestion can be slow on large datasets, subsequent lookups are free until `invalidate_cache()` or the process restarts

### Multi-Ingestion Support
- Each ingestion creates a timestamped folder under `data/`
- Frontend pulls list via `/ingestions` (requires auth token)
- `x-ingestion-id` header selects which ingestion's tables to query

### Database Migration
- Old table name: `flattened_tests`
- New table name: `structured_test_results`
- Code uses `_get_test_results_table()` to auto-detect; queries try new name first, fall back to old

### Error Handling
- **SQL Validation**: `query_executor.py` sanitizes and validates queries before execution
- **Multi-Table Fallback**: If schema changes, query falls back to alternative table names
- **Auth Validation**: `authenticate_user()` checks token validity on protected routes

## Frontend Build System

The frontend has a custom pre-build step that generates `builds.json`:

1. **Script**: `frontend/scripts/generate-builds-json.js`
2. **Trigger**: Runs automatically via `predev`, `prebuild`, `preinstall` npm hooks
3. **Source**: Reads from `frontend/public/builds.json` or API `/api/builds`
4. **Usage**: Used by build selector components

Make sure to run `npm install` or `npm run dev` at least once after pulling changes to regenerate this file.

## Environment Variable Reference

**Backend (`.env`)** — nothing here is actually required any more; every
value below has a working default or is settable later from the admin
console (see `services/config.py` and `services/app_settings.py`).
```
LLM_PROVIDER         # gemini, openai, anthropic, ollama, or any litellm provider
LLM_API_KEY          # API key (or provider-specific: OPENAI_API_KEY, etc.) — or set later in Admin → Settings
LLM_MODEL            # Full model ID
OLLAMA_URL           # http://localhost:11434 (if using Ollama)
SECRET_KEY           # ≥32 chars, random — auto-generated into state/secret_key if unset
LIVE_INGEST_API_KEY  # Reporter's x-api-key — auto-generated into state/live_ingest_api_key
                      # and logged once at startup if unset. Pinning it here disables the
                      # admin UI's Rotate key button (config.LIVE_INGEST_API_KEY_FROM_ENV)
LIVE_PACKAGE_DIR     # Where the served client tarball lives (default packages/dist-pack)
BOOTSTRAP_ADMIN_USERNAME   # default: admin
BOOTSTRAP_ADMIN_PASSWORD   # default: auto-generated into state/bootstrap_admin_password, logged
                            # once at startup (forces a password change on first login either way)
BOOTSTRAP_ADMIN_FORCE_PASSWORD_CHANGE # default: true
MIN_PASSWORD_LENGTH  # default: 8
BCRYPT_ROUNDS        # 10–16 (default 12)
CORS_ALLOWED_ORIGINS # Comma-separated list
AUTH_BACKEND         # db or memory
AUTH_AUTO_SEED_USERS # true/false
AUTH_SEED_FILE       # Path to JSON seed file
PROJECTS_ROOT        # Path to projects/ directory
ROLES_ROOT           # Path to roles/ directory
INGEST_MAX_FILE_SIZE_BYTES # Max ingestion file size (default 200MB)
INGEST_MAX_ROWS      # Max rows to ingest (default 500k)
INGEST_TIMEOUT_SECONDS # Ingestion timeout (default 600s)
```

**Test repo (live execution)** — set in the repo running the tests, not here:
```
SENTINEL_URL         # Sentinel API origin. The on/off switch: nothing reports without it
SENTINEL_API_KEY     # Must equal the backend's LIVE_INGEST_API_KEY
SENTINEL_DASHBOARD_URL # Only when the UI is on a different origin (local dev: :3000 vs :8000)
SENTINEL_ENV / SENTINEL_PROJECT # Free-text labels shown in the run list
SENTINEL_RUN_KEY     # Joins sharded processes into one run (sent as external_id)
SENTINEL_LIVE_VIEW   # on|off. Defaults on locally, off in CI (screenshots leave the network)
SENTINEL_DEBUG       # 1 to log what the reporter is doing
```

**Frontend (`frontend/.env.local`)**
```
NEXT_PUBLIC_API_URL  # http://localhost:8000 (backend API URL)
```

## Access Points (Local Development)

| Service | URL |
|---------|-----|
| Landing Page | http://localhost:3000 |
| Login | http://localhost:3000/login |
| Dashboard | http://localhost:3000/dashboard |
| Build Trends | http://localhost:3000/build-trends |
| Your account (password/username) | http://localhost:3000/account |
| Admin console (Overview/Users/Usage/Settings/Audit) | http://localhost:3000/admin |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |

## Notes for Future Work

- **Scaling**: Consider Redis for multi-instance cache (status/quality)
- **Async Ingestion**: Background ingestion already implemented via `ingestion_jobs.py`
- **Analytics**: Token usage tracked in `token_usage_store.py` for cost monitoring
- **Extensibility**: LLM provider abstraction makes it easy to add new providers (see `llm_client.py`)
