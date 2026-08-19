---
name: run-sentinel-dashboard
description: Build, launch, drive and screenshot the Sentinel QA Analytics dashboard (FastAPI backend + Next.js frontend). Use when asked to run, start, boot, serve, smoke-test, screenshot, or reproduce a bug in the Sentinel dashboard, or to hit its API as a logged-in user.
---

# Run the Sentinel QA Analytics dashboard

Two processes behind a login wall: **FastAPI on :8000** (Python venv, `services.main`)
and **Next.js 16 on :3000** (`frontend/`). Nothing useful is reachable without a
bearer token, and the dashboard renders skeletons until `/dashboard/overview`
answers — so `npm run dev` alone gets you a login form and no way in.

Drive it with **`driver.mjs`**, committed next to this file. It starts both
servers, signs in, makes authenticated API calls, and screenshots real pages
with Playwright.

All paths below are relative to `sentinel-qa-analytics-dashboard/`. Run every
command from there.

## Prerequisites

Verified on Windows 11 + PowerShell/Git Bash, Node v24.18.0, Python 3.14.
The venv and `node_modules` already exist in this checkout. From scratch:

```bash
python -m venv venv
./venv/Scripts/pip install -r requirements.txt
cd frontend && npm install && cd ..
```

`frontend/.env.local` must point at the backend:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

The driver needs **Playwright + a Chromium build** for screenshots. It borrows
them from the sibling `sfcc-qa-automation` repo by default. If that repo isn't
present, install locally and point the driver at it:

```bash
npm i -D playwright && npx playwright install chromium
SENTINEL_PLAYWRIGHT_FROM=$PWD/package.json node .claude/skills/run-sentinel-dashboard/driver.mjs shot /dashboard
```

## Run (agent path)

**Inside an agent harness (Claude Code, CI runner), start each server with
`serve` and let the harness own the process** — `up` detaches its children,
which is not enough on Windows (see Gotchas). Two background shells:

```bash
node .claude/skills/run-sentinel-dashboard/driver.mjs serve backend    # run backgrounded
node .claude/skills/run-sentinel-dashboard/driver.mjs serve frontend   # run backgrounded
```

Then poll until both answer — cold start is ~40s here, most of it Next.js:

```bash
for i in $(seq 12); do
  node .claude/skills/run-sentinel-dashboard/driver.mjs status | grep -q DOWN || break
  sleep 10
done
node .claude/skills/run-sentinel-dashboard/driver.mjs status
# backend   UP    http://localhost:8000/health -> 200
# frontend  UP    http://localhost:3000/login -> 200
```

In a normal interactive shell (not an agent harness), one command replaces both
`serve`s and the poll:

```bash
node .claude/skills/run-sentinel-dashboard/driver.mjs up
```

Everything below works the same either way. Under Git Bash, prefix any command
taking a `/route`-shaped argument with `MSYS_NO_PATHCONV=1`:

```bash
# sign in - caches the token in .driver-state.json
SENTINEL_USER=admin SENTINEL_PASS='<password>' \
  node .claude/skills/run-sentinel-dashboard/driver.mjs login
# -> Logged in as admin (role=admin, workspace=default)

# authenticated API call (x-ingestion-id is filled in with the newest build)
MSYS_NO_PATHCONV=1 \
  node .claude/skills/run-sentinel-dashboard/driver.mjs api GET /dashboard/overview

# screenshot real pages as a signed-in user -> .claude/skills/run-sentinel-dashboard/shots/
MSYS_NO_PATHCONV=1 \
  node .claude/skills/run-sentinel-dashboard/driver.mjs shot /dashboard /admin/users

# end-to-end check; exits non-zero if anything is wrong
node .claude/skills/run-sentinel-dashboard/driver.mjs smoke

node .claude/skills/run-sentinel-dashboard/driver.mjs status
node .claude/skills/run-sentinel-dashboard/driver.mjs down   # frees 8000 + 3000
```

`up` output:

```
Starting Sentinel...
  backend pid=26464 -> .claude/skills/run-sentinel-dashboard/logs/backend.log
  frontend pid=6160 -> .claude/skills/run-sentinel-dashboard/logs/frontend.log
  backend is up (http://localhost:8000/health -> 200)
  frontend is up (http://localhost:3000/login -> 200)
```

`smoke` output:

```
Smoke:
  PASS  backend /health — {"status":"ok","data_path":"C:\Users\...
  PASS  has an ingested build — ingestion_20260819_075910
  PASS  overview returns rows — total=2500
  PASS  runtime reports elapsed time — elapsed=570m across 0 workers (machine time 9.5h)
  PASS  screenshot written
All checks passed.
```

Server logs land in `.claude/skills/run-sentinel-dashboard/logs/`. Read those
first when something fails to start — the driver only reports the timeout.

### Getting a password

Accounts are local. List them, then reset one you own:

```bash
./venv/Scripts/python.exe -m services.admin_users list-users
./venv/Scripts/python.exe -m services.admin_users reset-password --username admin
```

Non-interactive, for a throwaway driver account:

```bash
./venv/Scripts/python.exe -m services.admin_users create-user \
  --username sentinel_driver --role admin --password '<generated>'
# -> Upserted user: sentinel_driver role=admin workspace=default status=active
./venv/Scripts/python.exe -m services.admin_users delete-user --username sentinel_driver
```

Valid roles are exactly `admin`, `cto`, `qa-manager`, `sdet`
(`services/permissions.py` `KNOWN_ROLES`); anything else is rejected at the API
boundary with a 400. `admin` and `cto` both hold every permission — use one of
them for a driver account or `/admin/*` returns 403. Three retired roles
(`qa-engineer`, `developer`, `viewer`) still *resolve* for accounts that
already carry them but can no longer be assigned.

`auth_seed_users.json` only seeds an **empty** user DB (`seed_if_empty`), so on
an existing checkout its passwords are usually stale — that file failing to log
you in means nothing is broken.

### Targeting a specific build

Every data endpoint keys off the `x-ingestion-id` header. The driver defaults to
the newest ingestion under `data/`; override it to reproduce a build-specific
bug:

```bash
SENTINEL_INGESTION=ingestion_20260709_110143 \
  node .claude/skills/run-sentinel-dashboard/driver.mjs smoke
```

### Calling backend code directly

Most backend changes don't need the servers at all — import and call:

```bash
./venv/Scripts/python.exe -c "
from universal_ingester.ingester import structured_table_name
print(structured_table_name('Testresults (1)'))
"
# -> structured_Testresults_1
```

The LLM path works the same way, which is the fastest way to debug a chat reply:

```bash
./venv/Scripts/python.exe -c "
import asyncio
from services.llm_client import LLMClient
print('REPLY:', repr(asyncio.run(LLMClient().agenerate('Say OK'))))
" 2>&1 | grep REPLY:
# REPLY: 'OK'
```

Tag and grep the line: aiohttp dumps an `Unclosed connector` traceback at
interpreter exit (the client is torn down without an `async with`), and it is
long enough to push a short reply off the top of the output. The warning is
cosmetic — the call already returned.

## Run (human path)

Two terminals, from the repo root and `frontend/` respectively:

```bash
./venv/Scripts/python.exe -m services.main
cd frontend && npm run dev
```

Then open http://localhost:3000/login. There is also `start-sentinel.ps1` at the
**parent** directory (`ai_dashboard/`), which opens both in their own PowerShell
windows. Neither path gives you a programmatic handle — use the driver instead.

## Test

```bash
./venv/Scripts/python.exe -m pytest tests/ -q
cd frontend && npx tsc --noEmit    # clean as of this writing
```

## Gotchas

These all cost real time here.

- **`/auth/login` takes query parameters, not a JSON body.** They're bare `str`
  args on the FastAPI handler, so a JSON body returns 422 and reads like your
  payload is malformed. `POST /auth/login?username=…&password=…`.

- **The dashboard skips its data fetch when the tab isn't visible.**
  `app/dashboard/page.tsx` guards `refreshOverview()` on
  `document.visibilityState !== "visible"`. A backgrounded browser tab sits on
  skeleton cards forever and looks like a hung backend — the request is simply
  never made. Headless Playwright reports `visible`, so the driver is unaffected;
  hand-driving a background tab is what breaks.

- **`detached: true` does not survive an agent harness on Windows.** It maps to
  `DETACHED_PROCESS`, which does *not* imply `CREATE_BREAKAWAY_FROM_JOB` — so a
  harness that runs each tool call inside a Job Object kills every "detached"
  server when it closes the job. The failure is genuinely confusing: `up`
  reports *both* servers timing out after 120s while `logs/frontend.log` says
  `✓ Ready in 783ms` and `logs/backend.log` is empty. Nothing is broken; the
  processes were reaped between the spawn and the health check. Use
  `serve <backend|frontend>` and let the harness own the lifetime.

- **Never spawn with `shell: true` on Windows here.** The checkout path contains
  a space (`C:\Users\JAIDEEP JOSHI\...`); under a shell the command is
  concatenated, not escaped, and you get
  `'C:\Users\JAIDEEP' is not recognized as an internal or external command`.

- **But `npm.cmd` can't be spawned without a shell either** — Node ≥18.20 throws
  `spawn EINVAL` (the CVE-2024-27980 fix). The driver runs
  `node <path>/npm-cli.js run dev` to escape both horns.

- **Child processes must be `detached: true` on Windows too.** Otherwise the
  servers die the instant the driver process exits, and the next command gets
  `ECONNREFUSED` on a port that was answering seconds ago.

- **Git Bash rewrites `/dashboard`-style arguments into Windows paths** before
  node sees them (`http://localhost:3000C:/Users/.../Git/dashboard`). The driver
  detects and undoes this; if you call the API another way, prefix the command
  with `MSYS_NO_PATHCONV=1` or drop the leading slash.

- **A role change takes effect on the next request, not the next login.**
  `get_current_user` prefers the *stored* role and workspace over the token's
  claims (it is already reading the row for the account-exists check). Before
  that, `admin_users set-role` looked like it did nothing for up to 24h — the
  JWT kept reporting the old role back through `/auth/permissions`. If you are
  chasing a role bug, the DB row is the truth, not the token.

- **`/auth/permissions` carries identity, not just permissions.** It returns
  `username`, `full_name` and `workspace_id` alongside `role`/`is_admin`/
  `permissions`, because the header's account menu needs them and this is a
  call the frontend already makes on every page. Don't add a `/auth/me` round
  trip for those three strings.

- **The backend holds one build in memory at a time.** Switching
  `x-ingestion-id` evicts the previous one from the warm pool and reloads from
  LanceDB, so the first request after a switch is slow (~250ms → seconds on big
  builds). Not a leak.

- **Ports are never auto-selected.** Both servers fail on a taken port rather
  than picking another; `up` clears 8000/3000 first for exactly this reason.

- **Ingestion is slow and mostly invisible.** A 2,500-row CSV took ~9 minutes,
  almost all of it embedding, with `job_status.json` sitting at
  `phase: processing, rows: 0` the whole time. Poll
  `data/<build_id>/job_status.json` rather than assuming it hung.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `up` says both timed out, but `logs/frontend.log` says `Ready in 783ms` | Job Object reaped the detached children. Use `serve` (see agent path). |
| `up` reports the backend never answered | Read `logs/backend.log`. A missing venv gives a clear message; a port conflict does not. |
| `'C:\Users\JAIDEEP' is not recognized` | Something spawned through a shell. See the Windows gotchas above. |
| `spawn EINVAL` | Spawning a `.cmd` without a shell on Node ≥18.20. Run the JS entrypoint under `process.execPath`. |
| `ECONNREFUSED ::1:8000` right after a successful `up` | Child wasn't detached, so it died with the driver. |
| `Failed to parse URL from http://localhost:8000C:/...` | MSYS path conversion. `MSYS_NO_PATHCONV=1` or omit the leading slash. |
| `400 Unknown role 'viewer'. Valid roles: admin, cto, qa-manager, sdet` | Retired role. Assign one of the four current ones. |
| `Login failed (401): Invalid credentials` | Stale `auth_seed_users.json`. Use `admin_users reset-password`. |
| Screenshot shows the login form | Token missing or expired — re-run `login`. The driver seeds `localStorage` before first paint; setting it after `goto()` bounces you to `/login`. |
| Cards render but stay empty | Confirm `/dashboard/overview` returns rows for that `x-ingestion-id`; an ingestion with no structured tables loads but has nothing to show. |
| `Could not load Playwright` | Sibling `sfcc-qa-automation` missing. Set `SENTINEL_PLAYWRIGHT_FROM` (see Prerequisites). |
| Chat replies "AI service unavailable" | `LLMClient.agenerate` returned empty. Check `logs/backend.log` — a `finish_reason=length` line means the model spent its whole budget on reasoning tokens. |
