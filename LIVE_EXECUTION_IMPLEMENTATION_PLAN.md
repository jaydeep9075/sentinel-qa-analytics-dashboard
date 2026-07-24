# Sentinel Live Execution — Implementation Plan (build-ready)

Reference doc for full reasoning: `LIVE_EXECUTION_ARCHITECTURE.md`. This file is the short, actionable checklist — read this first, work top to bottom.

## What we're building

A Playwright reporter that streams test events to Sentinel in real time. The dashboard shows the run live (status, logs, optional live browser). When the run ends, results are exported to one JSON file and ingested through the **existing** Allure-style pipeline — no separate write path to maintain.

## Data lifecycle

```
Playwright test  →  reporter (npm pkg)  →  POST events  →  SQLite (temporary, live only)
                                                              │
                                             dashboard reads live from here (SSE push)
                                                              │
                                         run ends → export all rows for run_id → run_result.json
                                                              │
                                    feed into universal_ingester as a new "live_run" connector
                                       (same code path as allure_connector.py: schema-detect →
                                        write structured_test_results → embed text → documents)
                                                              │
                                          on success → delete SQLite rows + temp JSON for that run
```


**Why export to JSON instead of writing Lance directly:** reuses the ingestion pipeline you already have, tested and working, instead of building/maintaining a second Lance-writing code path. The "live" connector is just another input format next to Allure/CSV/DB.

## Artifacts policy

| Attachment | Rule | Playwright config |
|---|---|---|
| Screenshot | Only on failure | `screenshot: 'only-on-failure'` |
| Video | Final video kept per test | `video: 'retain-on-failure'` (or `'on'` if you want every test's video, not just failures) |
| Trace | Only on failure (for debugging) | `trace: 'retain-on-failure'` |

Playwright already produces these files — the reporter just uploads whatever exists when a test ends. No custom capture logic to write.

## Live view — what's on screen during the run

- Run header: pass/fail/running/skipped counts, updating live.
- Per-test list: status flips (running → passed/failed) as it happens.
- Log panel: streams console/stdout lines as they arrive.
- "Watch Live" toggle per worker (optional, off by default): shows the actual browser via Chrome's built-in screencast — works in headless CI too.
- When the run ends, the same page becomes the normal historical report (no page switch).

## How you'll actually run it

**Local:**
```bash
npm install -D @sentinel/playwright
# playwright.config.ts:
#   reporter: [['@sentinel/playwright', { projectId: 'proj_abc', apiKey: process.env.SENTINEL_API_KEY }]]
export SENTINEL_BASE_URL=http://localhost:8000
export SENTINEL_API_KEY=sk_xxx
npx playwright test
```
Open Sentinel → **Live Runs** → your run appears the moment `playwright test` starts.

**CI (GitHub Actions / Jenkins / Azure DevOps / Bitbucket) — identical steps:**
```bash
npm install -D @sentinel/playwright   # same install
npx playwright test                    # same command
```
Set `SENTINEL_BASE_URL` and `SENTINEL_API_KEY` as CI secrets/env vars. Nothing else changes — the reporter auto-detects the CI provider from standard env vars (`GITHUB_ACTIONS`, `JENKINS_URL`, etc.) and tags the run with branch/commit/build link automatically. Same code path as local, no CI-specific code to write.

## Build checklist (do in this order)

**Backend**
1. `services/ingestion/schema.py` — event model (run started/finished, test started/finished, log, attachment).
2. `services/ingestion/store.py` — SQLite (WAL mode) tables: `run`, `test`, `log_line`, `attachment`, `worker_heartbeat`.
3. `services/ingestion/api.py` — `POST /runs`, `POST /runs/:id/events` (batched), `PATCH /runs/:id`, `POST /runs/:id/attachments`.
4. `services/live/bus.py` — in-process pub/sub per `run_id`.
5. `services/live/sse.py` — `GET /runs/:id/stream` (SSE), pushes on every write from step 3.
6. `services/live/screencast.py` — in-memory latest-frame cache per worker (no DB), `POST /runs/:id/live-frame`.
7. `universal_ingester/connectors/live_run_connector.py` — reads `run_result.json`, feeds the existing pipeline.
8. `services/finalize/job.py` — on `run.finished`: export SQLite rows → `run_result.json` → call `live_run_connector` → on success, delete the run's SQLite rows + temp JSON.

**SDK**
9. `packages/reporter-core` — HTTP client (batched, retry, offline ndjson buffer), CI-env auto-detect.
10. `packages/playwright` — Playwright `Reporter` implementation using core; attachment upload on test end (§ artifacts policy above); optional CDP screencast module.

**Frontend**
11. `app/runs/[runId]/live/page.tsx` — connects to SSE, renders status/logs/live-browser toggle.
12. Wire `app/runs/[runId]/page.tsx` to show the finalized (LanceDB) report once done — reuse existing report components.

**Verify**
13. Run locally end-to-end: `playwright test` → see it live → confirm it becomes a normal historical report after finish, with only-on-failure screenshots + video attached.
14. Repeat in one real CI provider (GitHub Actions first) — confirm identical behavior, no code changes needed.
15. Confirm SQLite rows for a finished run are actually deleted after successful ingestion (no leftover live data).
