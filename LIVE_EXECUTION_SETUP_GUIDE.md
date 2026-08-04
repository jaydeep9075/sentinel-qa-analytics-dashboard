# Adding Sentinel Live Execution to a Playwright Project — Step by Step

This is the "wire a repo up to Sentinel" guide: what to add to `playwright.config.ts`,
what to run, and what you should see on the dashboard when it works. It applies to
any Playwright project, not just `sfcc-qa-automation` (which is already fully wired
up and used as the reference example below).

---

## 0. Prerequisites

- Sentinel backend running: `http://localhost:8000` (health check: `/health`)
- Sentinel frontend running: `http://localhost:3000`
- You're logged into the dashboard (`http://localhost:3000/login`)
- Node.js ≥ 18, Playwright ≥ 1.40 in the target repo

Start both servers if they're not already up:

```powershell
# Terminal 1 - backend, from sentinel-qa-analytics-dashboard/
venv\Scripts\activate
python -m services.main

# Terminal 2 - frontend, from sentinel-qa-analytics-dashboard/frontend/
npm run dev
```

---

## 1. Install the reporter package

Sentinel ships its own Playwright reporter as an npm package: `@sentinel/playwright`,
at `sentinel-qa-analytics-dashboard/packages/sentinel-playwright`. It isn't published
to a registry yet, so link it locally by path in the target repo's `package.json`:

```json
"dependencies": {
  "@sentinel/playwright": "file:../sentinel-qa-analytics-dashboard/packages/sentinel-playwright"
}
```

(adjust the relative path to wherever `sentinel-qa-analytics-dashboard` actually sits
relative to the target repo), then:

```bash
npm install
```

---

## 2. Add the reporter to `playwright.config.ts`

Two things go into the config: the reporter itself, and (optionally) a Chrome launch
flag that lets Sentinel show a live browser view while the test runs.

```typescript
import { defineConfig } from "@playwright/test";

const useSentinel = !!process.env.SENTINEL_API_KEY;

export default defineConfig({
  reporter: [
    ["list"],
    ...(useSentinel
      ? [[
          "@sentinel/playwright",
          {
            baseUrl: process.env.SENTINEL_BASE_URL,   // default: http://localhost:8000
            apiKey: process.env.SENTINEL_API_KEY,
            projectId: "your-project-name",             // shows up in the run list
            environment: process.env.ENV,                // e.g. "dev", "stage"
            liveView: true,                                 // turn on the live browser feed
            liveViewPort: 9222,                             // must match the CDP flag below
          },
        ] as const]
      : []),
  ],
  use: {
    launchOptions: {
      args: useSentinel ? ["--remote-debugging-port=9222"] : [],
    },
  },
});
```

**Why the `useSentinel` flag pattern:** it makes Sentinel entirely opt-in per run
(via whether `SENTINEL_API_KEY` is set), so CI runs, other reporters, and local runs
that don't care about live view are completely unaffected.

**Why `--remote-debugging-port`:** the live browser view works by polling
`Page.captureScreenshot` over Chrome's own DevTools Protocol — no page objects,
fixtures, or existing test code need to change. It only works for Chromium-based
projects (not Firefox/WebKit).

**Multi-worker note:** if `workers > 1`, each worker needs its *own* CDP port, or
they'll all fight over the same one. The reporter already accounts for this — it
connects to `liveViewPort + workerIndex` per worker — but your launch args must match:

```typescript
const workerIndex = Number(process.env.TEST_PARALLEL_INDEX || 0);
// ...
launchOptions: {
  args: useSentinel ? [`--remote-debugging-port=${9222 + workerIndex}`] : [],
},
```

### Reporter options reference

| Option | Required | Default | Notes |
|---|---|---|---|
| `baseUrl` | no | `SENTINEL_BASE_URL` env, else `http://localhost:8000` | |
| `apiKey` | no | `SENTINEL_API_KEY` env | Must match the backend's `LIVE_INGEST_API_KEY` (auto-generated on first start if unset - see §3) |
| `projectId` | no | — | Free text, shown in the run list |
| `environment` | no | — | Free text, e.g. `dev`/`stage`/`prod` |
| `liveView` | no | `false` | Costs CPU/bandwidth — only turn on when someone's watching |
| `liveViewPort` | no | `9222` | Base port; add worker index for parallel runs |
| `liveViewIntervalMs` | no | `1000` | Screenshot poll rate (~1fps by default) |

**Don't use `--reporter=<name>` on the CLI.** It *replaces* the whole reporter array
from the config instead of adding to it, which silently disables Sentinel. Just run
`npx playwright test <file>` and let the config's `reporter` array stand.

---

## 3. Get the live-ingest key, set environment variables, and run

The backend authenticates every `/live/*` write with `x-api-key`. If
`LIVE_INGEST_API_KEY` isn't set in the backend's `.env`, one is generated on
first start into `state/live_ingest_api_key` and printed once in the
backend's own startup logs — grab it from either place:

```powershell
# from the backend's terminal output right after it starts, or:
Get-Content state\live_ingest_api_key
```

**PowerShell:**
```powershell
cd path\to\your-repo
$env:SENTINEL_API_KEY = "<the key from state/live_ingest_api_key>"
$env:SENTINEL_BASE_URL = "http://localhost:8000"
npx playwright test path/to/your.spec.ts
```

**Git Bash / WSL:**
```bash
cd path/to/your-repo
SENTINEL_API_KEY=<the key from state/live_ingest_api_key> SENTINEL_BASE_URL=http://localhost:8000 \
  npx playwright test path/to/your.spec.ts
```

`SENTINEL_API_KEY` must match the backend's `LIVE_INGEST_API_KEY` exactly —
a mismatched or missing value gets a 401 from every `/live/*` call, which
shows up as "nothing appears in Live Runs" (see Troubleshooting below). Set
`LIVE_INGEST_API_KEY` explicitly in the backend's `.env` if you'd rather pin
one fixed value than read a generated one back out of `state/`.

---

## 4. Watch it live

Open **http://localhost:3000/runs/live** *before* starting the test (or right after —
it polls every 2s). Within a second or two of the test starting, a new entry appears
named after the spec file. Click into it. You'll see, live, with no refresh needed:

- **Header counts** (running / passed / failed / skipped)
- **Test list** flipping from "running" → "passed"/"failed" per test
- **Log panel** — console output and step timings streaming in as they happen
- **Live browser tile(s)** — one per worker, a screenshot refreshing ~1x/sec, if
  `liveView: true` and the CDP flag are both set correctly

If a test fails, its screenshot/trace attachment (Playwright's own
`screenshot: 'only-on-failure'` output) uploads automatically and is visible on that
test's row.

## 5. Watch it finish

When the run ends, status flips to passed/failed on the same page — no redirect. A
few seconds later it's finalized in the background:

- Live logs are deleted (they've done their job)
- Video/screenshots are moved into permanent storage and stay reachable forever
- The run is folded into normal history — it shows up on the main **Dashboard** /
  **Build Trends** pages like any ingested build, after a refresh

---

## Quick local checklist

1. `curl http://localhost:8000/health` → `{"status":"ok"}`
2. Frontend loads at `http://localhost:3000`, you can log in
3. `@sentinel/playwright` is in the target repo's `package.json` (file: link) and `npm install` has run
4. `playwright.config.ts` has the reporter block + `useSentinel` gate + CDP launch arg
5. Run with `SENTINEL_API_KEY` and `SENTINEL_BASE_URL` set in the same shell as the test command
6. `http://localhost:3000/runs/live` open in a browser tab before/during the run

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Nothing appears in Live Runs | `SENTINEL_API_KEY` wasn't set in that shell, doesn't match the backend's `LIVE_INGEST_API_KEY` (401 - check the reporter's console output), or `--reporter=` was passed on the CLI | Re-check §3 for where to read the current key; drop any `--reporter=` flag |
| Run appears but no live browser tile | Chromium wasn't launched with `--remote-debugging-port`, or wrong port for that worker | Check `use.launchOptions.args`; console will log `[sentinel] live view disabled: ...` with the reason |
| "Run not found" / 401 on the live page | Not logged into the dashboard | Log in at `/login` first — the live page needs your session token |
| Logs never appear after the run starts | Backend unreachable from the test process | Check `SENTINEL_BASE_URL` matches where the backend actually listens |
| Attachments missing after the run finishes | Test passed and screenshot mode is `only-on-failure`/video is `retain-on-failure` | Expected — only failing tests produce attachments by design |
