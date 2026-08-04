# Sentinel QA Analytics — Docker Images

Two images, one stack: a FastAPI backend and a Next.js frontend for AI-powered
test analytics (Allure/CSV/DB ingestion, chat-driven charts, live Playwright
run streaming).

```
jaydeepjoshi9403/sentinel-qa-backend
jaydeepjoshi9403/sentinel-qa-frontend
```

This file is written to double as the Docker Hub "Overview" page for both
repos — paste it into **hub.docker.com → repo → Edit → Description** if it
isn't already synced. Full source, issues, and the deeper reference docs
(`DOCKER.md`, `SETUP.md`) live at
[github.com/jaydeep9075/sentinel-qa-analytics-dashboard](https://github.com/jaydeep9075/sentinel-qa-analytics-dashboard).

**No data or secrets are baked into either image.** `.env`, `data/`,
`state/` (accounts + config), and `ingest-source/` are all bind-mounted from
*your* machine at run time — pulling the image gets you the application,
never the maintainer's builds, accounts, or API keys. See "Where your data
lives" in `DOCKER.md` if you want to verify that yourself from the
Dockerfiles.

---

## 1. Quick start

Two files, no `git clone`:

```bash
curl -O https://raw.githubusercontent.com/jaydeep9075/sentinel-qa-analytics-dashboard/main/docker-compose.pull.yml
curl -O https://raw.githubusercontent.com/jaydeep9075/sentinel-qa-analytics-dashboard/main/.env.example
cp .env.example .env
```

Open `.env` and set (everything else has a working default — see §3):

- `SECRET_KEY` — 32+ random characters, or leave blank and one self-generates
  into `state/secret_key` on first start.
- `LLM_PROVIDER` / `LLM_API_KEY` / `LLM_MODEL` — or skip and configure later
  from **Admin → Settings** in the running app.
- `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD` — your first login.
  Username defaults to `admin`; leave the password blank and one is
  generated for you — check `docker compose -f docker-compose.pull.yml logs
  backend` right after first start (or read `state/bootstrap_admin_password`
  directly). Forced password change on first login either way.

Then:

```bash
docker compose -f docker-compose.pull.yml pull
docker compose -f docker-compose.pull.yml up -d
```

- Frontend → http://localhost:3000
- Backend → http://localhost:8000 (`/docs` for Swagger, `/health` for a ping)

Prefer a plain `docker run` over compose? See §6.

---

## 2. Public vs. private — pulling under both

**If the repos are public** (the default — nothing to do): the steps above
work with no `docker login` at all. Anonymous pulls are allowed, subject to
[Docker Hub's anonymous pull rate limit](https://docs.docker.com/docker-hub/download-rate-limit/)
(higher once you `docker login` with any free account, even one unrelated to
this image).

**If the repos are private:** the image name doesn't change, but every pull
needs an authenticated session from an account with access:

```bash
docker login -u <your-dockerhub-username>
docker compose -f docker-compose.pull.yml pull
```

Without an account added as a **Collaborator** (or a member of an
**Organization Team** with Read access) on both
`jaydeepjoshi9403/sentinel-qa-backend` and `-frontend`, this fails with
`denied: requested access to the resource is denied` — that error means
"not authorized," not "image doesn't exist," so don't debug it as a typo in
the image name.

**Granting access (maintainer side, Docker Hub UI):**
1. hub.docker.com → repo → **Settings → Collaborators** → add their Docker
   Hub username (per-repo, do it for both `-backend` and `-frontend`), **or**
2. Move both repos under a Docker Hub **Organization**, create a **Team**,
   grant the team Read (or Read & Write) on the repos, and add teammates to
   the team — the better option once more than 2-3 people need access, since
   team membership is managed in one place instead of per-repo.

CI/CD pulling a private image (no interactive login) authenticates the same
way, non-interactively:

```bash
echo "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_USER" --password-stdin
```
Use a [Docker Hub access token](https://docs.docker.com/security/for-developers/access-tokens/)
scoped to Read-only, not your account password.

---

## 3. `.env` reference — the condensed version

Full reference with every variable, default, and rationale is in
`.env.example` (fetched above) and `DOCKER.md`. This is the subset that
actually changes behavior day-to-day.

| Variable | Why you'd touch it |
|---|---|
| `SECRET_KEY` | JWT signing. Blank = auto-generated and persisted to `state/secret_key`. Losing that file signs everyone out (nothing else breaks). |
| `LLM_PROVIDER` / `LLM_API_KEY` / `LLM_MODEL` | Any [litellm](https://docs.litellm.ai/docs/providers)-supported provider — `gemini`/`openai`/`anthropic`/`ollama` have built-in default models. Leave blank to configure later from the running app's Admin → Settings (env, if set, always wins over the UI value). |
| `BOOTSTRAP_ADMIN_USERNAME` / `_PASSWORD` | First admin account. Only takes effect while the user table is empty — can't clobber an existing account. Password auto-generates and logs once if left unset — no fixed `admin`/`admin` default. |
| `DATA_DIR` / `STATE_DIR` / `INGEST_SOURCE_DIR` | **This is the "bring your own storage" knob.** Point these at any folder, second disk, or cloud-mounted volume on *your* machine — absolute paths are fine, Windows uses forward slashes (`C:/qa-storage/data`). The container always sees the same fixed internal paths; only the host side changes, no rebuild needed either way. |
| `BACKEND_PORT` / `FRONTEND_PORT` | Change if 8000/3000 are already taken on your machine. |
| `NEXT_PUBLIC_API_URL` | **Build-time only** — see §4, this is the one gotcha that isn't a restart-and-go .env change. |
| `CORS_ALLOWED_ORIGINS` | Must contain the frontend's actual origin or every browser request fails CORS. Comma-separated for more than one. |
| `LIVE_INGEST_API_KEY` | Locks down the Playwright live-run endpoint — see §5. Auto-generates and logs once if unset; the endpoint is authenticated by default, not open. |
| `IMAGE_NAMESPACE` / `IMAGE_TAG` | Which published image to pull — only relevant to `docker-compose.pull.yml`, ignored by anything that builds from source. |

Everything not listed here (auth backend choice, bcrypt cost, ingestion
size/row/timeout caps, auto-ingest drop-box tuning, Redis for multi-replica,
`WEB_CONCURRENCY`, …) has a working default. Uncomment in `.env` only when
you actually want to change it.

---

## 4. Features / things that trip people up

- **`data/`, `state/`, `ingest-source/` are directory mounts, on purpose.**
  Docker only bind-mounts a *file* if it already exists on the host;
  otherwise it silently creates a *directory* there and the app fails in a
  way that looks like an app bug. Mounting the containing directory instead
  means a fresh setup needs nothing pre-created — the backend seeds
  `state/users.db` and `state/config2.json` itself on first start.
- **`NEXT_PUBLIC_API_URL` is baked into the frontend image at build time**,
  not read at container start (Next.js inlines every `NEXT_PUBLIC_*` var
  into the client JS bundle). The published frontend image bakes in
  `http://localhost:8000` — exactly right if you run the stack locally with
  default ports, since it's *your browser* calling *your* `localhost:8000`,
  not the image publisher's. If you need a different backend URL baked in,
  you must rebuild the frontend from source with that build arg — editing
  `.env` and restarting the pulled image does nothing here.
- **First login is a one-time door, not a standing credential.** The
  bootstrap admin account forces a password change before any other route
  works (`/auth/me` and the password/username-change endpoints are the only
  things that respond until you change it) — and unlike many "appliance"
  defaults, its password isn't even a fixed guessable string to begin with;
  see the `.env` table above.
- **LLM config resolves per-field: env > database > built-in default.** A
  value pinned in `.env` locks that field — an admin can't override it from
  the UI. Leave a field out of `.env` and it becomes live-editable from
  **Admin → Settings**, including a one-click "Test connection" check, no
  restart required.
- **No outbound network needed for embeddings.** The `all-MiniLM-L6-v2`
  sentence-transformers model is baked into the backend image at build time
  (`HF_HUB_OFFLINE=1`), so semantic search/RAG works even on a fully
  air-gapped host.
- **`WEB_CONCURRENCY` > 1 is safe; concurrent requests against *different*
  ingestions on the *same* worker are not.** `services/state.py` holds the
  selected ingestion as mutable global state swapped per request — safe
  across separate worker *processes*, not safe for two simultaneous
  requests against different ingestions landing on one worker's event loop.
  Only raise this if your usage pattern doesn't do that (or after fixing it
  to be request-scoped).
- **Two people running the pulled image independently get two completely
  separate systems** — different accounts, different data — unless they
  deliberately point `DATA_DIR`/`STATE_DIR` at the same shared storage (a
  network share, a shared cloud volume). Nothing is shared by default, and
  nothing should be assumed shared.

---

## 5. Connecting a Playwright project (live test run streaming)

Sentinel ships its own Playwright reporter, `@sentinel/playwright`, that
streams a run live to the dashboard (`/runs/live`) as it executes — pass/fail
per test, console logs, and an optional live browser screenshot feed — then
folds it into normal build history when the run finishes. This section is
the **Docker-specific** part; the full walkthrough (installing the reporter,
`playwright.config.ts` wiring, troubleshooting table) is
`LIVE_EXECUTION_SETUP_GUIDE.md` in the source repo.

**The moving parts and where they run, when the stack is in Docker:**

| Piece | Runs where | Talks to |
|---|---|---|
| Your Playwright test process | Your host (npx playwright test) — **not** inside a container | Launches a local Chromium |
| `@sentinel/playwright` reporter | Same Node process as the test | HTTP → Sentinel backend; CDP → the local Chromium it just launched |
| Sentinel backend | Docker container | Receives the reporter's HTTP calls, published on `${BACKEND_PORT}` |

Because the reporter runs on your host, not inside Docker, the live browser
screenshot feed (Chrome DevTools Protocol) never crosses into the container —
it only needs `--remote-debugging-port` on the Chromium the test itself
launched. Docker only matters for the one thing the reporter calls over
HTTP: `baseUrl`.

**Setup, once the backend is up (`docker compose -f docker-compose.pull.yml up -d`):**

1. **Get the live-ingest key.** The backend generates one on first start if
   `LIVE_INGEST_API_KEY` isn't set in `.env` — the endpoint is authenticated
   by default, not open. Read it from the startup logs or the state file:
   ```bash
   docker compose -f docker-compose.pull.yml logs backend | grep LIVE_INGEST_API_KEY
   # or, any time:
   docker compose -f docker-compose.pull.yml exec backend cat /app/state/live_ingest_api_key
   ```
   (Pin your own instead by setting `LIVE_INGEST_API_KEY` in `.env` before
   first start — do this if you want one fixed value to hand out instead of
   reading a generated one back out of the container.)
2. In the target Playwright repo, point the reporter at the **published**
   backend port — not the in-container one, and not `http://backend:8000`
   (that hostname only resolves inside the Docker network) — using the key
   from step 1:
   ```bash
   export SENTINEL_BASE_URL=http://localhost:8000   # or your host's real address, if the test runs elsewhere
   export SENTINEL_API_KEY=<the key from step 1>
   ```
   Every Playwright repo that reports to this backend needs this same value.
3. Make sure `CORS_ALLOWED_ORIGINS` in `.env` includes wherever you'll load
   the dashboard from in a browser (default already covers
   `http://localhost:3000`) — the reporter's server-to-server calls aren't
   affected by CORS, but the live-runs *page itself*, loaded in your
   browser, is.
4. Run the test with those two env vars set in the same shell, open
   `http://localhost:3000/runs/live` before or during the run, and watch it
   stream in.

If the test process runs on a **different machine** than the Docker host
(e.g. CI runners hitting a shared Sentinel deployment), `SENTINEL_BASE_URL`
must be that host's real reachable address (and port). The endpoint is
already authenticated by default (step 1) — just make sure the CI
credential store holds the real generated/pinned key, not a placeholder.

---

## 6. Plain `docker run`, no compose

For anyone who wants full manual control instead of `docker-compose.pull.yml`:

```bash
docker network create sentinel-qa

docker run -d --name sentinel-backend \
  --network sentinel-qa \
  -p 8000:8000 \
  -e SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  -e CORS_ALLOWED_ORIGINS=http://localhost:3000 \
  -e SENTINEL_DATA_DIR=/app/data \
  -e SENTINEL_STATE_DIR=/app/state \
  -e BOOTSTRAP_ADMIN_USERNAME=admin \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/state:/app/state" \
  -v "$(pwd)/ingest-source:/app/ingest-source" \
  jaydeepjoshi9403/sentinel-qa-backend:latest

# BOOTSTRAP_ADMIN_PASSWORD deliberately left unset above - it self-generates
# into state/bootstrap_admin_password on first start. Grab it with:
docker logs sentinel-backend 2>&1 | grep -A1 "AUTO-GENERATED password"

docker run -d --name sentinel-frontend \
  --network sentinel-qa \
  -p 3000:3000 \
  -e SENTINEL_DATA_DIR=/app/data \
  -e SENTINEL_CONFIG2_PATH=/app/state/config2.json \
  -v "$(pwd)/data:/app/data:ro" \
  -v "$(pwd)/state:/app/state" \
  jaydeepjoshi9403/sentinel-qa-frontend:latest
```

The frontend image already has `NEXT_PUBLIC_API_URL=http://localhost:8000`
baked in (§4) — this only works as-is if the backend is reachable at that
exact address from your browser. Compose is the maintained, tested path;
this is here for people who need it, not the recommended default.

---

## 7. Getting help / reporting issues

Source, issue tracker, and the deeper docs (env var rationale, scaling,
Redis, ingestion connectors, auth/roles model) all live in the GitHub repo
linked at the top. This Docker Hub page intentionally stays focused on
"pull it and run it" — everything else is one click away.
