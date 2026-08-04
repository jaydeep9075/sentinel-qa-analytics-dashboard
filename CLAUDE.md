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
- **Zero-config first run**: `BOOTSTRAP_ADMIN_USERNAME`/`_PASSWORD` default to `admin`/`admin`
  when unset. That account is created with `must_change_password=true`, and
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
BOOTSTRAP_ADMIN_USERNAME   # default: admin
BOOTSTRAP_ADMIN_PASSWORD   # default: admin (forces a password change on first login)
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
