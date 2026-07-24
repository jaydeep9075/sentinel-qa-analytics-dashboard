# Manually Testing Live Execution — Step by Step

Both servers are already running for you:
- Backend: http://localhost:8000 (health check: http://localhost:8000/health)
- Frontend: http://localhost:3000

If you ever need to restart them yourself, that's just:
```bash
# Terminal 1 - backend, from sentinel-qa-analytics-dashboard/
venv\Scripts\activate
python -m services.main

# Terminal 2 - frontend, from sentinel-qa-analytics-dashboard/frontend/
npm run dev
```

## Step 1 — Log into Sentinel

Open http://localhost:3000/login, sign in with your usual Sentinel account.

## Step 2 — Open Live Runs (do this *before* starting the test, so you can watch it appear)

Either click **"Live Runs"** in the dashboard header (top right, next to Build Trends — it's there now), or go straight to **http://localhost:3000/runs/live**. Right now it'll say "Nothing running" — that's correct, nothing's running yet.

## Step 3 — In a separate terminal, run the login test

**⚠️ Shell matters here.** `VAR=value command` (all on one line, no `$env:` or `export`) is **bash/Git Bash syntax only** — in PowerShell it does nothing to the environment and Playwright silently runs without those variables set, which is exactly what caused the `Invalid URL` error (it means `FSAURL` never made it in). Use the version that matches the terminal you actually have open:

**PowerShell** (this is almost certainly what you're using — Windows' default):
```powershell
cd "C:\Users\JAIDEEP JOSHI\Desktop\ai_dashboard\sfcc-qa-automation"
$env:SENTINEL_API_KEY = "dev-local-test"
$env:SENTINEL_BASE_URL = "http://localhost:8000"
$env:ENV = "dev"
$env:FSAURL = "https://fsa.devhec.com"
npx playwright test src/tests/Platforms/SFRA/Header_Auth/FSA/Login.spec.ts --project=storefront-fsa-desktop
```
(`$env:X = "..."` sets it for the rest of that PowerShell session — every line after it sees it. Setting `FSAURL` explicitly is a belt-and-suspenders fallback in case `.env.dev` doesn't load for some other reason, e.g. wrong working directory.)

**Git Bash / WSL:**
```bash
cd "/c/Users/JAIDEEP JOSHI/Desktop/ai_dashboard/sfcc-qa-automation"
SENTINEL_API_KEY=dev-local-test SENTINEL_BASE_URL=http://localhost:8000 ENV=dev FSAURL=https://fsa.devhec.com \
  npx playwright test src/tests/Platforms/SFRA/Header_Auth/FSA/Login.spec.ts --project=storefront-fsa-desktop
```

**Do not add `--reporter=list` or any other `--reporter=` flag** — that overrides the whole reporter list in `playwright.config.ts` (which is how Sentinel gets wired in) instead of adding to it. Just running `npx playwright test <file>` is correct.

## Step 4 — Watch it live

Within a second or two of the command starting, your **Live Runs** tab (still open from Step 2) will show a new entry — click into it. You'll see, updating in real time with no refresh needed:

- **Header counts** (running / passed / failed / skipped) ticking up
- **Test list** — each of the two tests (`TS_39.1-LogInTest`, `TS_39.2-LogInTestinNewPages`) flips from "running" to "passed"/"failed" the moment it finishes
- **Log panel** — real console output and step timings streaming in as they happen (e.g. `Navigating to https://fsa.devhec.com`, `Login using email-id...`, step durations)

The whole run takes a few minutes (it's driving a real browser against the real site with deliberate slow-motion delays the repo configures) — that's expected, not a hang.

## Step 5 — Watch it finish

When the test ends, the run's status flips to passed/failed and the page stays exactly where it is — no redirect, no reload. A few seconds later (in the background), it gets written permanently into history. If you go to the main **Dashboard** or **Build Trends** page afterward and refresh, this run now shows up there like any other build.

## What you're actually looking at (quick reference)

| What you see | Where it's coming from |
|---|---|
| Run appears the instant the test starts | The reporter's `onBegin` hook POSTs to Sentinel before any test runs |
| Status flips live, no refresh | A live push connection (SSE) — Sentinel notifies the open browser tab the instant something changes, it doesn't wait to be asked |
| Log lines streaming in | Every console line and Playwright step gets sent as its own small message, in order |
| Run becomes a normal report after finishing | A background step exports everything about the run and feeds it through the same pipeline that already turns an Allure report into a dashboard build |

## Screenshots and video — how to actually see one

The current test file (`Login.spec.ts`) is expected to **pass**, so it won't produce a screenshot (by design — only failures get one, see below). To actually see the screenshot path work, either:

- **Temporarily break an assertion** in a copy of the test (e.g., check for the wrong email) and rerun, or
- **Pick a test elsewhere in the repo that's currently failing**, if one exists.

When a test does fail, look at the failed test's row in the live view (or the finished report afterward) — its attachment will be listed there, pointing at a file under `sentinel-qa-analytics-dashboard/data/runs/<run_id>/attachments/` (or, once finalized, wherever that run's permanent record keeps it).

## In short: how logs and screenshots actually work

**Logs**: every time your test prints something to the console, or Playwright finishes a step (like "navigate to page" or "click button"), the reporter packages that up as a tiny message and sends it to Sentinel immediately. Sentinel saves it and, in the same motion, pushes it to your open browser tab. That's the entire mechanism — no polling, no delay, just "something happened → tell whoever's watching, right now."

**Screenshots**: Playwright itself takes the screenshot (Sentinel doesn't do anything special here) — it's configured to do this **only when a test fails**, which is a normal Playwright setting (`screenshot: 'only-on-failure'`). The moment a test ends, the reporter checks "did this produce a screenshot file?" — if yes, it uploads that one file to Sentinel and attaches it to that test's record. Passing tests never generate one, on purpose — nobody needs a picture of something that worked.

## Troubleshooting

- **Nothing appears in Live Runs**: double check you didn't pass `--reporter=` on the command line (see Step 3's warning). Also confirm `SENTINEL_BASE_URL`/`SENTINEL_API_KEY` were actually set in that same command.
- **"Run not found" or it 401s**: make sure you're logged into the Sentinel dashboard (Step 1) — the live view needs your session token.
- **It shows the run but logs never appear**: check the backend terminal/log for errors reaching `/live/runs/.../events` — most likely a stale `SENTINEL_BASE_URL`.
