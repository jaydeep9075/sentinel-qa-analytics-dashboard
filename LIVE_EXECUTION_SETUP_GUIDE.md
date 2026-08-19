# Connecting a Test Repo to Sentinel Live Execution

How a Playwright or Cypress repo streams its runs to the dashboard's **Live
Runs** page as they happen.

**The whole thing is: install one package, wrap one config, set two
environment variables.** Everything after §3 is "a different framework",
"hosting", or "something went wrong".

---

## 0. What you actually need

| Where | What | Notes |
|---|---|---|
| Server | *nothing* | The ingest key generates itself on first start. |
| Test repo | `sentinel-qa-reporter` | One package, both frameworks. |
| Test repo | a wrapped config | One line for Playwright, three for Cypress. |
| Test repo | `SENTINEL_URL` | Where to report to. **This is the on/off switch.** |
| Test repo | `SENTINEL_API_KEY` | Shared secret, copied off the dashboard. |

There is no server-side setting you must change to make live runs work.

**Where the key comes from:** log in as an admin and open **Live Runs →
Connect a repo**. The panel shows this install's real URL, real key, and the
exact install command, with a copy button and a framework switch. Nothing in
it has to be adapted by hand. The same panel has a **Rotate key** button for
when a key ends up somewhere it should not have.

---

## 1. Install

If you host Sentinel yourself, install the build your own dashboard is
running — the image serves its own client package:

```bash
npm i -D https://sentinel.your-company.com/live/package/sentinel-qa-reporter-1.0.0.tgz
```

No npm account, no registry reachability, and the client version matches the
server version by construction. The exact line is on **Connect a repo**.

Otherwise, from npm:

```bash
npm i -D sentinel-qa-reporter
```

(Publishing that npm version is a one-time job — see `PUBLISHING.md`. Until
it's done, use the hosted-tarball line above, or a `file:` path to
`packages/dist-pack/sentinel-qa-reporter-<version>.tgz` for a repo on the same
machine.)

---

## 2. Wire it up

### Playwright

```ts
// playwright.config.ts
import { defineConfig } from "@playwright/test";
import { withSentinel } from "sentinel-qa-reporter/playwright/config";

export default defineConfig(
  withSentinel({
    // ...your existing config, unchanged...
  })
);
```

On a large existing config, wrap the finished object instead so you don't
re-indent the whole literal — it works the same either way:

```ts
const baseConfig = defineConfig({ /* ...your existing config, untouched... */ });

export default withSentinel(baseConfig);
```

That is the whole change. `withSentinel` is a **no-op unless `SENTINEL_URL`
is set**, so the line is safe to commit: a plain `npx playwright test` with no
Sentinel environment behaves exactly as before, and so does every pipeline
that has not opted in.

When it *is* enabled it does three things you would otherwise do by hand:

- appends the Sentinel reporter to your `reporter` array instead of replacing it
- adds `--remote-debugging-port` to `use.launchOptions.args` **and to every
  Chromium project's own `launchOptions.args`**
- offsets that port per worker, so parallel runs don't fight over one port

The middle one is the reason to use the helper. In Playwright a project-level
`use.launchOptions` **replaces** the config-level one rather than merging with
it, so in any repo whose projects set their own `launchOptions.args` — sandbox
flags, window size, `slowMo`, which is most real repos — a top-level CDP flag
never reaches the browser. Live view then silently never connects. WebKit and
Firefox projects are skipped automatically: they have no CDP endpoint, and
passing them a Chromium flag is a launch error rather than a no-op.

> **Don't use `--reporter=<name>` on the CLI.** It *replaces* the whole
> reporter array from the config, which silently disables Sentinel.

### Cypress

Two files, because Cypress splits into a Node half (can make HTTP calls) and a
browser half (knows about individual tests as they happen).

```ts
// cypress.config.ts
import { defineConfig } from "cypress";
import { registerSentinel } from "sentinel-qa-reporter/cypress";

export default defineConfig({
  e2e: {
    setupNodeEvents(on, config) {
      return registerSentinel(on, config);   // returning config is required
    },
  },
});
```

```ts
// cypress/support/e2e.ts
import { registerSentinelSupport } from "sentinel-qa-reporter/cypress/support";
registerSentinelSupport();
```

Also a no-op unless `SENTINEL_URL` is set — and the browser half stays
completely inert unless the Node half switched it on, so an unconfigured repo
never calls `cy.task` at all and reporting cannot fail a test.

Cypress gets everything except the live browser tiles: those come from Chrome
DevTools Protocol screenshot polling, which is Chromium/Playwright-specific.

---

## 3. Run it

```powershell
# PowerShell
$env:SENTINEL_URL = "https://sentinel.your-company.com"
$env:SENTINEL_API_KEY = "<from Connect a repo>"
npx playwright test          # or: npx cypress run
```

```bash
# bash
SENTINEL_URL=https://sentinel.your-company.com \
SENTINEL_API_KEY=<from Connect a repo> \
  npx playwright test
```

Locally the dashboard (`:3000`) and API (`:8000`) are two different origins,
so point `SENTINEL_URL` at the API and add the dashboard origin so the printed
watch link is clickable:

```bash
SENTINEL_URL=http://localhost:8000 \
SENTINEL_DASHBOARD_URL=http://localhost:3000 \
SENTINEL_API_KEY=<key> npx playwright test
```

Hosted behind one domain, `SENTINEL_URL` covers both.

### Set it once — then never touch it again

Typing two variables before every command is not a setup, it's a chore. Put
them somewhere permanent and every run from then on reports with no further
thought:

**Per machine (simplest).** One command, survives reboots and applies to every
terminal and every repo:

```powershell
setx SENTINEL_URL "https://sentinel.your-company.com"
setx SENTINEL_API_KEY "<from Connect a repo>"
```

```bash
# macOS/Linux - append to ~/.zshrc or ~/.bashrc
export SENTINEL_URL=https://sentinel.your-company.com
export SENTINEL_API_KEY=<from Connect a repo>
```

**Per repo.** If the repo already loads a `.env` file, put them there. Commit
`SENTINEL_URL` — it is not a secret, and committing it is what makes the whole
team's runs show up without anyone doing anything. Keep `SENTINEL_API_KEY` in
a git-ignored file.

**In CI.** Two repository variables (`SENTINEL_URL`, `SENTINEL_API_KEY`), set
once in the pipeline settings. Real environment variables always beat anything
a `.env` file loads, so CI overriding a committed default works exactly as
you'd expect.

There is no other maintenance. The config line stays as it is, package
upgrades are ordinary `npm update`, and the backend needs nothing. To turn
reporting **off** — for a repo, a machine, or a pipeline — unset
`SENTINEL_URL`. Nothing else changes.

### Worked example: `sfcc-qa-automation`

Already wired, as a reference for the next repo:

- `playwright.config.ts` — the config literal is unchanged; it is assigned to
  `baseConfig` and the file ends with
  `export default withSentinel(baseConfig, { environment: currentEnv, projectId: process.env.TARGET_APPLICATION })`.
  Wrapping the finished object instead of the literal keeps the diff to a few
  lines rather than re-indenting 160.
- It also loads `.env.local` (git-ignored, already the repo's secrets file)
  after `.env.<env>`, non-overriding — so `SENTINEL_API_KEY` lives in one file
  and a CI variable still wins.
- The old hand-written reporter block was removed. It pushed a package that
  was never in `devDependencies`, so it would have thrown the moment anyone
  set the variable it was gated on.

### In CI

Set the same two values as pipeline secrets. Branch, commit and a link back to
the build are detected automatically for GitHub Actions, GitLab CI, Jenkins,
Azure DevOps, Bitbucket Pipelines and CircleCI — the run page links straight
back to the build that produced it.

**Sharded suites** (`--shard=1/4`, or one job per browser) are several
processes reporting one logical run. Give them all the same `SENTINEL_RUN_KEY`
and they attach to a single run, with the test counts summed and the run only
closing when the last shard finishes:

```yaml
env:
  SENTINEL_RUN_KEY: ${{ github.run_id }}-${{ github.run_attempt }}
```

Without it you get one run per shard — which is still correct, just four rows
instead of one. It is opt-in deliberately: silently merging two unrelated jobs
that happen to share a build id would be a worse failure than not merging.

---

## 4. What you get

Open **`/runs/live`** before or during the run. Within a second or two a run
appears, named after the spec file(s), with pass/fail counts, elapsed time and
progress in the row — so you can leave the list open on a second screen and
answer "is anything red?" without opening anything.

Click through for:

- **Progress** — how many of the suite's tests are done, and the pass rate so far
- **Failures** — each failing test with its error message, at the top of the page
- **Test list** — flipping from running → passed/failed as results land
- **Live log** — console output and step timings, streaming
- **Live browser** — one tile per worker, ~1×/sec (Playwright + Chromium)
- **Attachments** — failure screenshots, video and traces, uploaded automatically

When the run ends the status flips in place, then it finalizes in the
background: live logs are discarded, artifacts move to permanent storage, and
the run joins normal history on **Dashboard** and **Build Trends**.

---

## 5. Settings reference

Everything is optional except the first two.

| Variable | Meaning |
|---|---|
| `SENTINEL_URL` | Sentinel API origin. Nothing reports without it. |
| `SENTINEL_API_KEY` | Ingest key from **Connect a repo**. |
| `SENTINEL_DASHBOARD_URL` | Only when the UI is on a different origin than the API. |
| `SENTINEL_ENV` | Free-text label, e.g. `dev` / `stage` / `prod`. |
| `SENTINEL_PROJECT` | Free-text label shown in the run list. |
| `SENTINEL_RUN_KEY` | Joins several processes into one run (see sharding, above). |
| `SENTINEL_LIVE_VIEW` | `on` / `off`. Defaults **on** locally, **off** in CI. |
| `SENTINEL_DEBUG` | `1` to log what the reporter is doing. |
| `NODE_EXTRA_CA_CERTS` | Node's own variable — point it at your CA bundle for an internally hosted install with a private certificate. |

Live view defaults off in CI on purpose: screenshots of the app under test are
the one thing this package sends that could carry customer data, and on CI
nobody is watching them live anyway.

Anything settable by environment is also settable as an option:
`withSentinel(config, { environment: "stage", liveView: false })`.

---

## 6. Hosting

Live execution needs nothing configured server-side. Two general settings
decide whether the dashboard can reach its own API at all:

- **`CORS_ALLOWED_ORIGINS`** must include the origin people load the dashboard
  from. Everything on the Live Runs page is a browser `fetch`, so a wrong value
  here shows up as a permanently empty page with CORS errors in the console.
- **`NEXT_PUBLIC_API_URL`** is baked into the frontend at **build** time. If
  you build the image yourself, pass the public API URL as a build arg;
  changing it afterwards as a runtime env var has no effect.

Optional:

- **`LIVE_INGEST_API_KEY`** — pin it explicitly if you run more than one
  backend replica, since otherwise each generates its own key into its own
  state directory. Pinning it in the environment also disables the **Rotate
  key** button, because rotating would write a file the next restart ignores.
- **`REDIS_URL`** — required for multiple replicas. The SSE bus and live-frame
  cache are in-process by default.
- **`LIVE_PACKAGE_DIR`** — where the served client tarball lives. The Docker
  images build it in and set this already; a source checkout serves nothing
  until you run `npm run pack:dist` in `packages/sentinel-qa-reporter/`.
- **`LIVE_RUN_STALE_TIMEOUT_SECONDS`** — how long a run may go silent before
  it is treated as abandoned and swept. Default 900 (15 min).

Reverse proxies need SSE to work: disable response buffering on `/live/*`
(`proxy_buffering off` in nginx — the backend already sends
`X-Accel-Buffering: no`) and allow long-lived connections, or the live page
will connect and then show nothing.

---

## 7. Other frameworks (WebdriverIO, pytest, anything)

Live execution is not tied to any framework — the two adapters are just the
first clients of a plain HTTP contract. Any runner that can make HTTP calls
can report, and `framework` is free text that shows up as-is in the UI.

Four calls, all authenticated with `x-api-key: <SENTINEL_API_KEY>`:

**1. Start** — `POST /live/runs`

```json
{
  "framework": "wdio",
  "name": "checkout.spec.ts",
  "total_tests": 12,
  "environment": "stage",
  "branch": "main",
  "ci_provider": "jenkins",
  "build_url": "https://ci.example.com/job/42",
  "external_id": "build-4711"
}
```

Returns `{"run_id": "run_..."}`. `total_tests` drives the progress bar;
`external_id` joins shards into one run (both optional).

**2. Stream events** — `POST /live/runs/{run_id}/events`, batched, up to 2000
events per request:

```json
{
  "events": [
    {"event_type": "test.started",  "ts": "2026-08-19T10:00:00Z",
     "test": {"id": "spec:1", "title": "adds item to cart", "status": "running"}},
    {"event_type": "test.finished", "ts": "2026-08-19T10:00:04Z",
     "test": {"id": "spec:1", "title": "adds item to cart", "status": "failed",
              "duration_ms": 4120, "error": "expected 1 item, got 0"}},
    {"event_type": "test.log", "ts": "2026-08-19T10:00:02Z",
     "test": {"id": "spec:1", "title": "adds item to cart"},
     "payload": {"level": "stdout", "message": "clicked #add-to-cart"}}
  ]
}
```

`status` is one of `running`, `passed`, `failed`, `skipped`, `retried`. Put a
failure message in `test.error` — it renders in the Failures panel.

**3. Attach a file** (optional) —
`POST /live/runs/{run_id}/attachments?test_id=...&kind=screenshot`,
`multipart/form-data` with a `file` field.

**4. Finish** — `PATCH /live/runs/{run_id}` with `{"status": "passed"}`,
`"failed"` or `"cancelled"`. This triggers finalization into permanent
history. For a sharded run, every participant PATCHes and the run closes when
the last one does.

A run that never gets its final `PATCH` (killed process, crashed agent, closed
laptop) is swept automatically rather than sitting in the list forever.

---

## Troubleshooting

The reporter names the cause on stdout rather than printing a status code —
check the test output first, the line starts with `[sentinel]`.

| Symptom | Cause | Fix |
|---|---|---|
| `could not reach <url>` | Wrong `SENTINEL_URL`, or backend down | It must be the API origin with no trailing path |
| `SENTINEL_API_KEY does not match` | Key mismatch | Re-copy from **Connect a repo** |
| `not a Sentinel API` (404) | URL points at the frontend, or at a path | Use the API origin |
| `did not respond in time` | Proxy or firewall between runner and backend | Check egress from the runner |
| TLS handshake failed | Private CA | Set `NODE_EXTRA_CA_CERTS` |
| No `[sentinel]` line at all | `SENTINEL_URL` unset, or `--reporter=` on the CLI replaced the config array | Set the env / drop the flag |
| Cypress: nothing per-test, run appears | Support file not importing `registerSentinelSupport()` | Add it to `cypress/support/e2e.ts` |
| Run appears, no live browser tile | Non-Chromium project, CI default, or a `--remote-debugging-port` the repo set itself | Expected for WebKit/Firefox and in CI; else set `SENTINEL_LIVE_VIEW=on` and check the console |
| Live page loads but stays empty | SSE buffered by a proxy, or CORS | See §6 |
| `dropping buffered log lines` | Backend was unreachable for a while | Test results are still kept; check the backend |
| Four runs instead of one from a sharded job | No `SENTINEL_RUN_KEY` | See §3 |
| No attachments after a passing run | `screenshot: only-on-failure` | Expected — only failures produce them |
