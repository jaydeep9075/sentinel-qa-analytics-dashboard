# sentinel-qa-reporter

Stream a **Playwright** or **Cypress** run to a [TR-Insight](../../README.md)
dashboard while it is still running — live test results, logs, failures,
screenshots, and (Playwright + Chromium) a ~1fps view of the browser.

One package, both frameworks, two environment variables. (The package name
and the `SENTINEL_*` env vars below are this reporter's stable identifiers —
unchanged by the TR-Insight rebrand.)

```bash
npm i -D sentinel-qa-reporter
```

If your team hosts TR-Insight itself, install the copy that host was built with
instead — same command, no registry needed:

```bash
npm i -D https://sentinel.your-company.com/live/package/sentinel-qa-reporter-1.0.0.tgz
```

The exact line, with your host and version filled in, is on the dashboard
under **Live Runs → Connect a repo**.

## Playwright

```ts
// playwright.config.ts
import { defineConfig } from "@playwright/test";
import { withSentinel } from "sentinel-qa-reporter/playwright/config";

export default defineConfig(
  withSentinel({
    /* your existing config, unchanged */
  })
);
```

## Cypress

```ts
// cypress.config.ts
import { defineConfig } from "cypress";
import { registerSentinel } from "sentinel-qa-reporter/cypress";

export default defineConfig({
  e2e: {
    setupNodeEvents(on, config) {
      return registerSentinel(on, config);
    },
  },
});
```

```ts
// cypress/support/e2e.ts
import { registerSentinelSupport } from "sentinel-qa-reporter/cypress/support";
registerSentinelSupport();
```

## Run

```bash
SENTINEL_URL=https://sentinel.your-company.com \
SENTINEL_API_KEY=<from Connect a repo> \
  npx playwright test        # or: npx cypress run
```

## Environment

| Variable | Required | Meaning |
|---|---|---|
| `SENTINEL_URL` | yes | TR-Insight API origin. **Nothing reports without it** — which is what makes the config safe to commit. |
| `SENTINEL_API_KEY` | yes | Shared ingest key, from **Live Runs → Connect a repo**. |
| `SENTINEL_DASHBOARD_URL` | no | Only when the UI is on a different origin than the API (local dev: `:3000` vs `:8000`). |
| `SENTINEL_ENV` / `SENTINEL_PROJECT` | no | Free-text labels shown in the run list. |
| `SENTINEL_RUN_KEY` | no | Joins several processes into one run — set it on a sharded suite (`--shard=1/4`) so four processes report one run instead of four. |
| `SENTINEL_LIVE_VIEW` | no | `on`/`off`. Defaults **on** locally, **off** in CI. |
| `SENTINEL_DEBUG` | no | `1` to log what the reporter is doing. |

Behind a private CA, point `NODE_EXTRA_CA_CERTS` at your bundle.

## Guarantees

Reporting never fails a test run. Every request has a deadline, every queue
has a ceiling, the backend going away mid-run costs log lines and never test
results, and the worst outcome available to this package is one `[sentinel]`
warning followed by silence.

## Licence

MIT
