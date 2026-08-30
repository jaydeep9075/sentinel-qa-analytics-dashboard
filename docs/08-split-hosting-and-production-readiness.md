# Split Hosting & Production Readiness

> **Status (2026-08-30): §1's two routes are removed, §2's `projects/`/`builds.json`
> leak is fixed, and §4's CI workflow now exists** (`.github/workflows/docker-publish.yml`).
> The `WEB_CONCURRENCY` caveat in §3 was already fixed in code (a process-wide
> `state._duck_query_lock`) when this doc was written — that bullet describes
> what raising it does and doesn't buy you, not an open bug. Remaining open
> items: picking and provisioning an actual backend host with a persistent
> volume, and the Redis/image-size/backup items in §3, which are inherent to
> this architecture rather than bugs to fix.

You're planning to host frontend and backend **separately** (e.g. frontend on
Vercel, backend on its own Docker host) instead of the single-host
`docker compose up` setup covered in [`05-docker.md`](05-docker.md) /
[`06-hosting-and-resources.md`](06-hosting-and-resources.md). This doc covers
what changes, what doesn't, why you're currently seeing data on a "fresh"
deploy, the real bottlenecks, and how to rebuild images going forward.

It assumes you've read `05-docker.md` and `06-hosting-and-resources.md` — this
doesn't repeat their env-var reference, storage layout, or resource tables.

## 1. Can frontend and backend actually be split?

**Auth: yes, cleanly.** The frontend stores the JWT in `localStorage` and
sends it as `Authorization: Bearer <token>` (`frontend/lib/api.ts`,
`liveRuns.ts`, `roleSuggestions.ts`) — there are no auth cookies and no
same-origin/`SameSite` assumption. A Vercel-hosted frontend calling a
backend on a different domain works as long as `CORS_ALLOWED_ORIGINS` on the
backend includes the Vercel origin and `NEXT_PUBLIC_API_URL` is built with
the backend's public URL.

**One real blocker: two Next.js route handlers touch the backend's
filesystem directly, not over HTTP.**

- `frontend/app/api/builds/route.ts` and `frontend/app/api/config2-path/route.ts`
  read/write `SENTINEL_DATA_DIR` and `SENTINEL_CONFIG2_PATH` straight off
  disk. In the current compose setup this works only because the `frontend`
  container also bind-mounts `DATA_DIR:ro` and `STATE_DIR` alongside the
  backend (see the `frontend.volumes` block in `docker-compose.yml`).
- Vercel functions have no shared filesystem with a backend running
  somewhere else — there is no volume to mount. Deployed as-is, these two
  routes will either 404/500 or silently show empty data on Vercel.
- **Fix before splitting hosts**: rewrite both routes to call the backend's
  HTTP API (`GET /ingestions`, `POST /ingest/config2` — check `services/main.py`
  for the exact paths) instead of reading `SENTINEL_DATA_DIR`/`config2.json`
  from disk. Once they're plain `fetch(NEXT_PUBLIC_API_URL + ...)` calls, the
  frontend has no filesystem dependency left and is a completely stateless,
  Vercel-friendly Next.js app.

Everything else under `frontend/` is a normal client-rendered app hitting the
backend over `fetch`/axios — no other split blockers found.

**Backend: needs a host with a persistent disk, not serverless.** There is no
Postgres/Mongo here — LanceDB, DuckDB, and the `users.db` SQLite file are all
plain files under `DATA_DIR`/`STATE_DIR` (see `06-hosting-and-resources.md`
§ Storage layout). That means:

- The backend needs a platform that gives you an attachable persistent
  volume — a VM (EC2/DigitalOcean/etc., the existing `terraform/` path),
  Fly.io with a volume, Railway/Render with a persistent disk add-on. A
  platform that only offers ephemeral/stateless containers (plain Cloud Run,
  plain Vercel/Netlify functions) will lose all ingested data and every
  account on the next redeploy.
- Whatever host you pick, `DATA_DIR` and `STATE_DIR` must map to that
  platform's persistent volume, exactly like the local bind mounts do today.

## 2. Why you see data locally but a fresh host should be empty

Two different mechanisms are at play — only one of them is actually a
problem:

**Local `data/` and `state/` — not a problem.** Both are gitignored
(`.gitignore` lines for `state/`, `data/`, `users.db`) and excluded from the
Docker build context (`.dockerignore`). They never leave your machine or your
image. A teammate cloning the repo or pulling the built image will not get
your local ingestions or your local `users.db` through either path.

**`projects/` — this is the actual leak.** `PROJECTS_ROOT` defaults to
`<repo>/projects` (`services/config.py`), and unlike `data/`/`state/` it is
**not** gitignored — it's tracked in git with real content:
`projects/FSA/context.md` + LanceDB embeddings, `projects/Lendingwise/context.md`,
`projects/clippd/context.md` + embeddings. `services/Dockerfile` then does
`COPY --chown=appuser:appuser projects ./projects`, so **every backend image
you build bakes these three real client projects in**, regardless of
environment. Anyone who pulls `jaydeepjoshi9403/sentinel-qa-backend` or
clones the repo gets them — this is the actual reason a "fresh" deploy isn't
actually empty.

To fix, pick one:

1. **Stop tracking real project content in git.** Keep `projects/` in the repo
   only as a placeholder (like `ingest-source/.gitkeep` already does), add the
   real subfolders to `.gitignore`, and remove the `COPY projects ./projects`
   line from `services/Dockerfile` — an admin adds project context after
   deploy through whatever UI/API writes into `PROJECTS_ROOT`.
2. **Bind-mount it like `DATA_DIR`/`STATE_DIR` instead of baking it in** —
   add a `PROJECTS_DIR` host-side variable to `docker-compose.yml`, drop the
   `COPY` from the Dockerfile, and mount an empty directory in production. A
   fresh deploy gets an empty `projects/`; your local dev machine keeps its
   own populated one via the bind mount.

Either way, this needs a decision on whether `FSA`/`Lendingwise`/`clippd`
context data is meant to be public (it's currently sitting in a public-looking
git history and Docker Hub image either way) — worth checking git history and
rotating/removing it if that data shouldn't have been committed at all.

**Auth is already handled correctly and needs no change**: `state/users.db`
is gitignored and not copied into the image; a fresh container has an empty
user table, and `_bootstrap_admin_if_empty()` in `services/auth.py` creates
exactly one admin account from `BOOTSTRAP_ADMIN_USERNAME`/`BOOTSTRAP_ADMIN_PASSWORD`
(or autogenerates + logs a password if you don't set one), forcing a password
change on first login. That's the "admin does setup" flow you want — it
already works, it just doesn't come across as working because `projects/`
currently overshadows it with real-looking data.

## 3. Bottlenecks worth knowing about before you scale this

- **`WEB_CONCURRENCY` defaults to 1 uvicorn worker — conservative, not
  required.** `services/state.py` used to hold the selected ingestion as
  mutable global state (contextvars fixed that), and DuckDB connections
  aren't safe for concurrent use from multiple threads. Rather than
  per-thread `cursor()`s (which can't see the pandas tables `data_loader`
  registers via `conn.register()` — verified against the pinned duckdb
  version), every query site takes `state._duck_query_lock`, a process-wide
  lock that serializes DuckDB execution. It's already safe to raise
  `WEB_CONCURRENCY` for more worker-level throughput (I/O and LLM-call
  waiting overlaps across workers); it just doesn't buy you *parallel*
  DuckDB queries within one process — those still run one at a time, which
  is fine at this app's traffic level.
- **CI/CD**: `.github/workflows/docker-publish.yml` now runs backend
  pytest + frontend lint on every push/PR, and on push to `main` (or a `v*`
  tag) builds and pushes both images tagged with the commit SHA and
  `latest`. Needs `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN` repo secrets and,
  before the published frontend image is production-useful, the
  `NEXT_PUBLIC_API_URL` repo variable set to your real backend URL (see the
  workflow file's trailing comment) — see §4.
- **No horizontal scaling story for live execution without Redis.** The
  live-run SSE bus (`services/live_exec/bus.py`) is in-process pub/sub;
  running more than one backend replica silently breaks live viewing for
  runs not on the replica a given browser is connected to, unless you enable
  the `multi-instance` profile and set `REDIS_URL`. Fine for one replica,
  a trap if you scale the backend out without reading this first.
- **Large backend image.** `torch` (CPU wheel) + a baked-in
  `sentence-transformers` model make the backend image multi-hundred-MB to
  low-GB even after the two-stage build's stripping. That's a reasonable
  trade for zero-network-dependency startup on a persistent VM; it's a worse
  fit for any platform that charges/cold-starts per container pull.
- **No managed database, so no managed backup/replication either.** Backup
  is "copy `DATA_DIR` and `STATE_DIR`" (rsync/tar), documented already in
  `06-hosting-and-resources.md`. That's fine for a single-VM deployment but
  means point-in-time recovery, replicas, and failover are all things you'd
  have to build yourself if you need them — there's no RDS/Atlas equivalent
  doing it for you.
- **The Terraform path is a single VM, no autoscaling/failover** — stated
  plainly in `06-hosting-and-resources.md` already; repeating here only so
  it's on your radar when you're deciding where the backend lives.

## 4. How images get rebuilt

**Now: `.github/workflows/docker-publish.yml`.** On every push/PR it runs
backend pytest and frontend lint. On push to `main` (or a `v*` tag), once
tests pass, it builds and pushes both images to Docker Hub tagged with the
commit SHA (`sha-<12 chars>`) **and** `latest` — the SHA tag is what gives
you a rollback path (`IMAGE_TAG=sha-abc123...` in `.env`) that a
floating-only `latest` never could.

Before this workflow can push anything, set in the GitHub repo (**Settings →
Secrets and variables → Actions**):

- Secrets: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` (a Docker Hub access
  token, not your account password)
- Variables: `IMAGE_NAMESPACE` (optional, defaults to `DOCKERHUB_USERNAME`),
  `NEXT_PUBLIC_API_URL` (your real backend URL — required before the
  *published* frontend image is anything but a `localhost:8000`-pointing
  placeholder, since Next.js inlines it at build time)

You can still do a manual build for local iteration —
`docker compose build [backend|frontend]` + `docker compose push` — the
workflow just means you no longer have to remember to.

## 5. Suggested split-hosting shape

```
Vercel (frontend, Next.js standalone)
  ├─ NEXT_PUBLIC_API_URL = https://api.yourdomain.com   (build-time env var)
  └─ no filesystem dependency — already true, §1's two routes are gone

Backend host with a persistent volume (Fly.io / Render / Railway / EC2 /
existing terraform/ path)
  ├─ /app/data   -> persistent volume  (DATA_DIR)
  ├─ /app/state  -> persistent volume  (STATE_DIR)
  ├─ /app/projects -> empty by default in prod (see §2)
  ├─ CORS_ALLOWED_ORIGINS includes the Vercel domain
  ├─ BOOTSTRAP_ADMIN_USERNAME/PASSWORD set (or left to auto-generate + log)
  └─ LLM provider/key set here or finished later in Admin → Settings
```

Resource sizing for the backend host doesn't change from what
`06-hosting-and-resources.md` already documents (3GB/2vCPU container limits,
`t3.large` as the tested VM baseline) — splitting hosting doesn't change what
the backend needs, it just moves where it runs.

## Action items, roughly in order

1. ~~Decide what to do with `projects/FSA`, `projects/Lendingwise`,
   `projects/clippd` (§2)~~ **Done.** Untracked from git (`git rm --cached`,
   kept on disk locally), `.gitignore`d, and no longer `COPY`'d into either
   Dockerfile — a fresh clone or pulled image now has an empty `projects/`.
   Still true: this data sat in git history (and, if ever pushed, in the
   public backend image) before today — rotate/scrub history separately if
   `FSA`/`Lendingwise`/`clippd` context was never meant to be public.
   `public/builds.json` (real client test names, same root cause) got the
   same treatment, plus its dead generator script was deleted outright.
2. ~~Rewrite `frontend/app/api/builds/route.ts` and
   `frontend/app/api/config2-path/route.ts`~~ **Done, differently.**
   `config2-path/route.ts` had no caller anywhere in the frontend — deleted,
   not rewritten. `api/builds/route.ts` was only used by
   `app/build-trends/page.tsx`, which now calls `listIngestions()` (the same
   `GET /ingestions` helper `lib/IngestionContext.tsx` already used) directly
   — no Next.js server route in between at all, consistent with how every
   other page already talks to the backend.
3. Pick a backend host with a persistent volume and wire `DATA_DIR`/`STATE_DIR`
   to it; set `CORS_ALLOWED_ORIGINS` and `NEXT_PUBLIC_API_URL` for the split
   domains. **Still open** — this is an infrastructure/provider decision, not
   a code change; see §5 for the shape.
4. ~~Add a CI workflow~~ **Done** — `.github/workflows/docker-publish.yml`
   (§4). Needs `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN` secrets and the
   `NEXT_PUBLIC_API_URL` variable set in the GitHub repo before it's
   production-useful.
5. Read §3 before enabling more than one backend replica — the
   `WEB_CONCURRENCY`/DuckDB-lock caveat was already fixed in code (§3 now
   reflects that); Redis-for-multi-replica-live-exec, image size, and
   backup/failover are architectural trade-offs to know about, not bugs
   waiting on a fix.
