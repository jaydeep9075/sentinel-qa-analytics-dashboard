# Connecting a new automation repo

Two independent ways to get a test repo's results into TR-Insight. You can use
either, or both.

| | **Live** | **Ingest** |
|---|---|---|
| When | While the suite runs | After the suite finishes |
| You install | `sentinel-qa-reporter` in the test repo | nothing |
| You configure | 2 env vars + a reporter line | `state/config2.json` |
| Shows up at | `/runs/live` | `/dashboard`, `/build-trends` |
| Frameworks | Playwright, Cypress | Allure, CSV/XLSX/JSON/Parquet/…, SQL DB, HTTP API |

---

## A. Live — stream a run as it happens

Works with Playwright and Cypress. Nothing reports unless `SENTINEL_URL` is
set, so the config below is safe to commit.

### 1. Get the key

Dashboard → **Live Runs → Connect a repo**. Copy the install line and the
`SENTINEL_API_KEY` shown there. (Admins can also read or rotate it via
`GET /live/connection-info` and `POST /live/connection-info/rotate`.)

### 2. Install in the test repo

```bash
npm i -D sentinel-qa-reporter
# or, to match the host you're reporting to exactly:
npm i -D https://<your-host>/live/package/sentinel-qa-reporter-1.0.0.tgz
```

### 3. Wire the reporter

**Playwright** — wrap your existing config, change nothing else:

```ts
// playwright.config.ts
import { defineConfig } from "@playwright/test";
import { withSentinel } from "sentinel-qa-reporter/playwright/config";

export default defineConfig(withSentinel({
  /* your existing config, unchanged */
}));
```

**Cypress**:

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

### 4. Set the env vars and run

```bash
SENTINEL_URL=http://localhost:8000 \
SENTINEL_API_KEY=<from Connect a repo> \
SENTINEL_DASHBOARD_URL=http://localhost:3000 \
  npx playwright test
```

| Variable | Required | Meaning |
|---|---|---|
| `SENTINEL_URL` | yes | API origin. Unset = the reporter is a no-op. |
| `SENTINEL_API_KEY` | yes | Shared ingest key. Keep it in CI secrets, never in the repo. |
| `SENTINEL_DASHBOARD_URL` | no | Only when the UI is on a different origin than the API (local dev: `:3000` vs `:8000`). |
| `SENTINEL_ENV` / `SENTINEL_PROJECT` | no | Free-text labels in the run list. |
| `SENTINEL_RUN_KEY` | no | Joins shards into one run. Set it on `--shard=1/4` so 4 processes report 1 run. |
| `SENTINEL_LIVE_VIEW` | no | `on`/`off`. Defaults on locally, off in CI. |
| `SENTINEL_DEBUG` | no | `1` to log what the reporter is doing. |

In CI, set `SENTINEL_URL` as a plain variable and `SENTINEL_API_KEY` as a
masked secret.

Watch at `http://localhost:3000/runs/live`. When the run finishes it is
finalized into a permanent record automatically.

---

## B. Ingest — load results after the run

### 1. Produce results

Any of: an Allure results folder or zip, a CSV/XLSX/JSON/Parquet export, a
database the results already land in, or an HTTP endpoint that serves them.

### 2. Drop them in

Put the files in `ingest-source/` at the repo root. That folder is mounted
into the container at `/app/ingest-source`.

### 3. Edit `state/config2.json`

Seeded on first backend start. Copy the shape from
[`config2.json.example`](../config2.json.example). Paths are **container**
paths.

```jsonc
{
  "ingestion_name": "checkout-regression",   // becomes the build label
  "sources": [
    { "type": "allure", "path": "/app/ingest-source/allure-results.zip" }
  ],
  "output": { "base_path": "/app/data" }
}
```

`sources` is a list — add more than one entry to combine sources into a single
build.

| `type` | Required keys | Notes |
|---|---|---|
| `allure` | `path` | Folder or `.zip`; zips are auto-extracted |
| `file` | `path` | csv, tsv, xlsx, xls, json, jsonl, ndjson, parquet, xml, txt, log, pdf, png/jpg (OCR'd), yaml |
| `db` | `params.connection_string`, `params.tables` | Any SQLAlchemy URL. `params.connect_args` for SSL etc. |
| `api` | `params.url`, `params.headers` | HTTP/GraphQL returning JSON; paginated |

> `state/` is gitignored — real connection strings and tokens belong there,
> not in `config2.json.example`.

### 4. Run it

```bash
docker compose run --rm ingest       # Docker
docker-ingest.bat                    # Windows wrapper
cd universal_ingester && python ingester.py   # local
```

The new build appears at `GET /ingestions` immediately; a running backend
picks it up without a restart.

### Other ways in

| Method | Use it when |
|---|---|
| **Add Build** wizard in the dashboard | One-off, no shell access |
| `POST /ingest/upload` with `INGEST_API_KEYS` | CI pushes the artifact itself |
| `AUTO_INGEST_ENABLED=true` | A job keeps dropping files into `ingest-source/` |

For the CI push, set `INGEST_API_KEYS=ci-key:default` in `.env`, then:

```bash
curl -X POST http://localhost:8000/ingest/upload \
  -H "x-api-key: $SENTINEL_INGEST_KEY" \
  -F "file=@allure-results.zip"
```

---

## Adding a source type that doesn't exist yet

1. Add a connector in `universal_ingester/connectors/` subclassing
   `BaseConnector`; `fetch()` yields dicts with `name`, `type`, `data`,
   `metadata`.
2. Register it in the dispatch map in `universal_ingester/ingester.py`.
3. Expose it in `services/ingestion_service.py` so the **Add Build** wizard
   lists it.
4. Add a case to `tests/test_universal_pipeline.py`.
5. Document the `type` in `config2.json.example`.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| Live run never appears | `SENTINEL_URL` unset, or the key was rotated. Run with `SENTINEL_DEBUG=1`. |
| `401` from the reporter | Stale `SENTINEL_API_KEY` — re-copy from **Connect a repo**. |
| Sharded suite shows as N runs | Set `SENTINEL_RUN_KEY` to the same value in every shard. |
| Ingest finds no files | `path` must be the container path (`/app/ingest-source/...`), not a host path. |
| Ingest succeeds, 0 rows | Source matched no files. Check the Allure folder actually holds `*-result.json`. |
| Build missing from the dashboard | It landed in another workspace or is unassigned — Admin → Projects → build mapping. |
