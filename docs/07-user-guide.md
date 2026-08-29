# User Guide

How to actually use TR-Insight once it's running. For install/first-run, see [`02-getting-started.md`](02-getting-started.md).

## Logging in and accounts

Three ways an account gets created, in the order you'll actually use them:

1. **The first admin** — from `BOOTSTRAP_ADMIN_*` in `.env`, applied only while the user database is empty.
2. **Self-service** — visit `/register`, fill in username, email, password and the team you think you're on. This creates a **pending** account: it exists but can't log in and has no workspace until an admin approves it. Signing up gets you into a queue, not into the data.
3. **Admin-created** — an admin adds the account directly on **Users → New user**, already active.

An admin approves a pending request from the Users page — picking the actual workspace and role; the team the person requested is shown only as a hint.

### Roles

| Role | Access |
|---|---|
| `admin` / `cto` | Everything — all workspaces, user management, settings, audit log |
| `qa-manager` | Read/ingest access, scoped to their own workspace |
| `sdet` | Read/ingest access, scoped to their own workspace |

Don't confuse this with the AI **persona** picker inside the chat — that's a separate concept (see below).

### Workspaces

A workspace is a team. Every build belongs to exactly one; a normal user sees only their own workspace's builds, an admin sees all of them, labelled by workspace. There's no separate "create a workspace" step — assigning a user to a new workspace name is what creates it.

## Ingesting a build

Four routes in, one result: a new `data/ingestion_<timestamp>/` folder that appears in the dashboard immediately, no restart needed.

| Route | Use it when |
|---|---|
| Drop-box watcher | Your CI or a mounted volume can write files directly |
| `POST /ingest/upload` | It can't (hosted runner, Lambda, another network) |
| Dashboard "Add Build" | A person is importing something by hand |
| One-shot container/CLI | Bulk or offline import, backend needn't be running |

**Drop-box watcher**: with `AUTO_INGEST_ENABLED=true`, drop a folder or `.zip` (treated as Allure) or a supported file (`.csv .tsv .xlsx .xls .json .jsonl .ndjson .parquet .xml .txt .log .pdf .png .jpg .yaml`) into `ingest-source/`. It appears within ~30 seconds. A subdirectory routes to that workspace by name (`ingest-source/platform/report.zip` → workspace "platform"), if that workspace already exists.

**HTTP upload**: `curl -X POST http://your-host:8000/ingest/upload -H "x-api-key: ci-abc123" -F "file=@allure-results.zip"` — the API key (issued as `key:workspace` pairs in `INGEST_API_KEYS`) decides which workspace the build lands in.

**Dashboard "Add Build"**: type the container path to the file (e.g. `/app/ingest-source/my-results.zip`) and hit ingest — it runs in the background inside the running backend, attributed to your account and workspace.

**One-shot container**: `docker compose run --rm ingest` after pointing `config2.json`'s source path at your data — doesn't need the backend or frontend running.

### Deleting a build

Removes everything that build produced — test results, saved charts, chat history, the summary and ownership record — since everything a build produces lives inside that build's own folder. Who can delete: the person who created it, or an admin; a build with no human creator (CI/drop-box) can be deleted by anyone in its workspace; a build predating ownership tracking (`source: legacy`) is admin-only.

## Dashboard and Build Trends

- **Dashboard** (`/dashboard`) — the main analytics UI: KPI monitoring, test status visualization, module stability metrics, slow-test detection, mobile vs. desktop breakdowns, and the AI chat/chart panel.
- **Build Trends** (`/build-trends`) — compares metrics across multiple ingestions: pass-rate trend (line), test results breakdown (stacked bar: passed/failed/skipped), total duration and average test duration across builds. Choose a display range (last 5, 10, 20, or all builds).

## AI chat

Ask a question in plain English in the chat panel. Your message goes out with context headers (which ingestion, which role persona, which project) and the backend decides whether to run a SQL query, a vector similarity search, or answer directly from context.

Example questions:
- "How many tests passed vs failed?"
- "What's the pass rate for the FSA module?"
- "Show me the slowest 5 tests"
- "How does this build compare to the last one?"
- "What are the top failure reasons?"

### Role personas (`x-role`)

Independent of your account role, you can pick which **persona** the AI answers as — a Markdown instruction file under `roles/` (`cto.md`, `qa-manager.md`, `sdet.md`) that shapes tone and framing (executive risk summary vs. technical failure detail) without changing what data you can see.

### Project context (`x-project`)

Selecting a project scopes the AI to that project's context file under `projects/` (used for retrieval alongside the SQL results) — check what's currently configured under `projects/` in your install, since these are maintained per-deployment.

## AI chart generation

Ask for a chart the same way, in plain English — the form is auto-detected from your prompt:

- "Show pass/fail distribution as a pie chart"
- "Bar chart of tests per module"
- "Line chart showing test duration trend"
- "Breakdown of mobile vs desktop test results"
- "Show passed vs failed by suite as a grouped bar chart"

Generated charts are saved to a per-session history, shown in a gallery on the dashboard — reorder, view or delete them from there.

## Live test runs

Watch a Playwright or Cypress run as it happens, before it's even finished, at **`/runs/live`**.

### Connecting a repo (as an admin)

Open **Live Runs → Connect a repo** — it shows this install's real URL, real ingest key, and the exact install command for your framework, with a copy button. A **Rotate key** button is there for when a key ends up somewhere it shouldn't.

The short version, for a Playwright repo:

```bash
npm i -D sentinel-qa-reporter
```

```ts
// playwright.config.ts
import { defineConfig } from "@playwright/test";
import { withSentinel } from "sentinel-qa-reporter/playwright/config";

export default defineConfig(withSentinel({ /* your existing config, unchanged */ }));
```

```bash
SENTINEL_URL=https://your-dashboard-host \
SENTINEL_API_KEY=<from Connect a repo> \
  npx playwright test
```

`withSentinel` is a no-op unless `SENTINEL_URL` is set, so it's safe to commit — an unconfigured pipeline behaves exactly as before. Cypress needs two small wiring points instead of one (a Node half and a browser half) — the exact snippets are in the Connect a repo panel. Full settings reference (`SENTINEL_ENV`, `SENTINEL_PROJECT`, `SENTINEL_RUN_KEY` for sharded suites, `SENTINEL_LIVE_VIEW`, `SENTINEL_DEBUG`) is shown there too.

### What you see

Open `/runs/live` before or during a run — within a second or two it appears, named after the spec file(s), with pass/fail counts and progress. Click through for live progress, failures with error messages, the test list flipping running → passed/failed, a streaming log, one live browser tile per worker (Playwright + Chromium only), and automatically uploaded failure screenshots/video/traces. When the run ends it finalizes in the background and joins normal history on the Dashboard and Build Trends.

## Admin console (`/admin`)

Five tabs, all requiring `admin` or `cto`:

| Tab | What it's for |
|---|---|
| **Overview** | Population by status, workspace count, build count, lifetime token spend, and whether the LLM is actually configured |
| **Users** | Approve pending signups, create/edit accounts, set per-account token limits and force-password-change |
| **Usage** | Every account's lifetime token spend against its limit, with a per-account reset |
| **Settings** | LLM provider/model/key/base URL, editable at runtime with a live "Test connection" check. Fields pinned in `.env` show a "locked by env" badge |
| **Audit** | Append-only trail of logins, registrations, user edits, credential changes, settings edits and build deletions |

Everything on the Users page also works from a terminal — useful when you're locked out:

```bash
python -m services.admin_users list-users
python -m services.admin_users approve --username jane --workspace platform --role sdet
python -m services.admin_users create-user --username bob --role sdet --workspace platform --password '...'
python -m services.admin_users reset-password --username admin
```

(Docker: prefix with `docker compose exec backend`.)
