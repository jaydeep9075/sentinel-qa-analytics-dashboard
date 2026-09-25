# Developer map — where to do what

A lookup table for "I need to change X, which file?". Deeper explanations live
in [`03-architecture-guide.md`](03-architecture-guide.md).

## The shape of it

```
Browser ──► frontend/ (Next.js :3000) ──HTTP──► services/ (FastAPI :8000)
                                                    │
                                    ┌───────────────┼───────────────┐
                                    ▼               ▼               ▼
                              DuckDB (SQL)   LanceDB (vectors)   LLM (litellm)
                                    ▲
                                    │ writes
                          universal_ingester/ (separate process)
```

The ingester is **not** part of the web app. It writes build folders into
`data/`; the backend reads them. They never call each other at runtime.

---

## Backend — `services/`

| I want to… | File |
|---|---|
| Add or change an HTTP route | `main.py` (`@app.get/post/...`) |
| Add a whole feature area of routes | New package with an `APIRouter`, then `app.include_router(...)` — copy `live_exec/` |
| Read a new env var | `config.py`, **and** document it in `.env.example` |
| Add a setting an admin can change at runtime | `app_settings.py` (SQLite-backed; env still wins) |
| Change login, tokens, password rules | `auth.py` |
| Change who can do what | `permissions.py` (constants + role→permission map) |
| Change the users table / CRUD | `user_store.py` |
| Change how a question becomes SQL | `handlers.py` |
| Change the wording sent to the LLM | `prompts.py` (chat/chart), `production_prompts.py` (validation) |
| Swap or add an LLM provider | `llm_client.py` (litellm wrapper) |
| Change how a chart is drawn | `chart_builder.py` (figure), `chart_spec.py` (intent→spec), `chart_theme.py` (colors) |
| Change what schema the LLM is shown | `schema_context.py` |
| Change how builds are loaded/pooled | `data_loader.py`, `state.py` |
| Change conversation memory / history | `memory.py` |
| Change background ingestion jobs | `ingestion_jobs.py`, `ingestion_service.py` |
| Change the drop-folder watcher | `auto_ingest.py` |
| Change live-run ingest, SSE, screencast | `live_exec/` (`router.py`, `store.py`, `bus.py`, `screencast.py`) |
| Change how a finished live run is archived | `finalize/job.py` |
| Change project/workspace scoping | `project_manager.py`, `project_access.py`, `project_builds.py` |
| Change persona wording | `roles/*.md` (plain markdown, loaded by `role_manager.py`) |
| Change token-spend accounting | `token_usage_store.py` |
| Change the audit trail | `audit_log.py` |

> Speech-to-text / text-to-speech still lives in `voice.py` and the `/voice/*`
> routes still exist, but **the dashboard UI does not use them**.

## Frontend — `frontend/`

| I want to… | File |
|---|---|
| Add a page | `app/<route>/page.tsx` (App Router) |
| Guard a route behind login | `app/<area>/layout.tsx` — copy `app/dashboard/layout.tsx` |
| Call a backend endpoint | `lib/api.ts` — **never** `fetch` a hardcoded URL from a component |
| Read the signed-in user's permissions | `lib/usePermissions.ts` → `has("perm")`, `isAdmin` |
| Read the selected role/project | `lib/RBContext.tsx` (`useRB()`) |
| Read the selected build | `lib/IngestionContext.tsx` (`useIngestion()`) |
| Change chat suggestions | `lib/SuggestionsContext.tsx`, `lib/roleSuggestions.ts` |
| Change chart colors/theme | `lib/chartTheme.ts`, `lib/theme.ts` |
| Change the chat panel | `components/FloatingChat.tsx` |
| Change the chart generator popover | `components/FloatingChart.tsx` |
| Change the build/ingestion picker | `components/IngestionSelector.tsx` |
| Change the Add Build wizard | `components/AddBuildWizard.tsx` |
| Change branding | `lib/brand.ts`, `components/BrandLogo.tsx`, `app/icon.tsx` |
| Add a shared type | `types/analytics.ts` |

## Ingestion — `universal_ingester/`

| I want to… | File |
|---|---|
| Add a source type (Jira, TestRail, …) | New `connectors/<name>_connector.py` + register in `ingester.py` |
| Change Allure parsing | `connectors/allure_connector.py` |
| Add a file format | `connectors/file_connector.py` |
| Change field-type detection | `schema/runtime_detector.py` |
| Change how rows are written / deduped | `core/storage.py` |
| Change JSON flattening | `core/normalizer.py` |
| Change the embedding model | `utils.py` (single source of truth; `config.py` imports it) |
| Change the post-ingest summary | `summary.py` |

See [`09-connect-an-automation-repo.md`](09-connect-an-automation-repo.md) for
the config file and the full wiring walkthrough.

## Config and secrets

| Thing | Where | Committed? |
|---|---|---|
| Backend env | `.env` (template: `.env.example`) | No — template only |
| Frontend env | `frontend/.env.local` (template: `frontend/.env.example`) | No — template only |
| Ingestion sources | `state/config2.json` (template: `config2.json.example`) | No — template only |
| Auth DB, JWT key, live ingest key | `state/` | No |
| Ingested builds | `data/` | No |
| Runtime LLM settings | SQLite via `app_settings.py`, edited in Admin → Settings | n/a |

Precedence for LLM settings is **last writer wins** between `.env` and
Admin → Settings. `.env` edits need a backend restart; admin-UI edits are
immediate.

## Ops

| Thing | Where |
|---|---|
| Backend image | `services/Dockerfile` |
| Frontend image | `frontend/Dockerfile` |
| Single-container image | `Dockerfile.allinone` + `supervisord.allinone.conf` |
| Compose (build locally) | `docker-compose.yml` |
| Compose (pull prebuilt) | `docker-compose.pull.yml`, `*.allinone.yml` |
| TLS reverse proxy | `Caddyfile` (`--profile proxy`) |
| CI | `.github/workflows/docker-publish.yml` |
| AWS single VM | `terraform/` |

## Tests and checks

| Thing | Where |
|---|---|
| Backend tests | `tests/` — the only path pytest collects (`pyproject.toml`) |
| Backend lint | `ruff` — config in `pyproject.toml` |
| Frontend lint | `frontend/eslint.config.mjs` |
| Dev-only deps | `requirements-dev.txt` |
| Throwaway diagnostics | `scripts/` — standalone `__main__` scripts, not tests |

```bash
python -m pytest tests/ -q
python -m ruff check services universal_ingester tests scripts
cd frontend && npm run lint && npx tsc --noEmit && npm run build
```

## Gotchas

- The backend runs without `--reload`: **code edits need a manual restart**.
- `NEXT_PUBLIC_API_URL` is inlined at **build** time. Changing it for Docker
  means a rebuild with the build arg, not an env var at container start.
- CORS must list both `localhost:3000` and `127.0.0.1:3000` — the browser
  treats them as different origins, and a block surfaces as an opaque
  `TypeError: Failed to fetch`, never a status code.
- `data/` and `state/` are bind mounts. Deleting `state/` loses users and the
  JWT key (everyone gets signed out); deleting `data/` loses ingested builds.
- Never put real credentials in a `*.example` file.
