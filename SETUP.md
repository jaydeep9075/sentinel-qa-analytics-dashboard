# Setup Guide — Sentinel QA Analytics Dashboard

Start here if you've just cloned this repo. It takes you from nothing to a
running dashboard, then covers day-to-day use: restarting, rebuilding after a
code change, getting data in, and moving storage somewhere else.

For deeper reference topics (scaling workers, Redis, the full env-var table)
see [DOCKER.md](DOCKER.md).

---

## 1. What you're running

Two containers, started and stopped together by one command:

```
  your browser
       |
       v
  frontend  :3000   Next.js dashboard
       |
       v
  backend   :8000   FastAPI + LanceDB/DuckDB + LLM
       |
       v
  ./data/          every ingestion, on your disk (not inside the container)
```

Both are defined in `docker-compose.yml`. You never start them separately and
you don't need two terminals.

**Nothing important lives inside a container.** `data/` (builds) and `state/`
(accounts) are bind-mounted from the host, so `docker compose down`, rebuilds,
and image deletion never destroy them. Backup = copy `data/` and `state/`.

The three things you'll want to understand beyond "it runs":

| | Where |
|---|---|
| Which LLM it calls, and with whose key | §3 step 1 — all from `.env`, any provider |
| Who can log in and what they can see | §3a — accounts, approval, workspaces |
| How test results get in | §5 — drop-box, HTTP upload, or the dashboard |

---

## 2. Prerequisites

Install **Docker Desktop** and make sure it's running (whale icon in the tray).
That's the only requirement — Python, Node, and every dependency live inside
the images.

Verify:

```bash
docker --version
docker compose version
```

---

## 3. First-time setup

Two steps: fill in `.env`, then start. Nothing to create by hand. If you'd
rather not use a terminal, `docker-start.bat` does both and prompts you
through the `.env` edit.

> **Upgrading an install that predates the `state/` directory?** Move the two
> files into it once — `mkdir state && mv users.db config2.json state/` — with
> the stack stopped. Your accounts and builds are otherwise untouched.

### Step 1 — Create your `.env`

There is **one** `.env`, at the repo root, and it configures both services.

```bash
cp .env.example .env
```

You can genuinely leave `.env` empty and run `docker compose up -d` — a fresh
container has no required values any more. Fill these in when you have them
handy; skip them for a first look and finish later from the admin console.

**`SECRET_KEY`** — signs login tokens. If unset, the backend generates one on
first start and writes it to `state/secret_key`. That file is what keeps
everyone's login working across restarts, so back it up along with `state/`;
losing it just signs everyone out (a new one is generated), it doesn't lock
you out permanently. Set it explicitly yourself if you'd rather manage it as a
secret than a file — must be 32+ characters:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**`LLM_API_KEY`** — your LLM credential. See the provider table below. If you
skip it, the backend still starts (chat/chart just answer with a clear "not
configured yet" instead of failing to boot) — finish it later as an admin, in
**Admin → Settings**, with a **Test connection** button. A key set here in
`.env` always takes precedence over one saved in Settings.

**`BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD`** — the first admin
account, created **only** when the user database is empty (so it can't be used
to override or reset an existing account). Leave `BOOTSTRAP_ADMIN_USERNAME`
unset and it defaults to `admin`; leave `BOOTSTRAP_ADMIN_PASSWORD` unset and
the backend generates one for you into `state/bootstrap_admin_password`,
printed once in the startup logs — there is no fixed `admin`/`admin` pair
anymore, since a well-known password on anything reachable before you've
logged in is a race, not a safeguard. That account is created with a forced
password change either way: the very first login can do nothing except set a
real username and password. Set these instead if you'd rather choose the
first admin's username/password yourself; you'll still get a forced change
unless you also set `BOOTSTRAP_ADMIN_FORCE_PASSWORD_CHANGE=false`.

#### Choosing an LLM provider

Provider, model and key all come from `.env`. Switching vendors is an edit to
these lines plus a restart — no rebuild, no code change.

| Provider | `LLM_PROVIDER` | Key variable | `LLM_MODEL` |
|---|---|---|---|
| Google Gemini (default) | `gemini` | `GEMINI_API_KEY` | `gemini/gemini-2.5-flash` |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` | `anthropic/claude-opus-5` |
| OpenAI | `openai` | `OPENAI_API_KEY` | `openai/gpt-4o-mini` |
| Groq | `groq` | `GROQ_API_KEY` | `groq/llama-3.3-70b-versatile` |
| Ollama (local, no key) | `ollama` | — | `ollama/llama3` |

**Any other provider litellm supports also works.** Its key is read from
`<PROVIDER>_API_KEY`, falling back to `LLM_API_KEY`. For a provider not in the
table you must set `LLM_MODEL` explicitly, since there's no built-in default to
fall back on.

Two things worth knowing:

- **The active provider's own key wins**, and `LLM_API_KEY` is only the
  fallback. So you can keep every vendor's key in `.env` at once and switch by
  changing `LLM_PROVIDER` alone. Previously a stale `LLM_API_KEY` would be sent
  to whichever provider you switched to, producing a 401 with nothing in the
  config looking wrong.
- **A provider/model mismatch is refused at startup.** If you switch
  `LLM_PROVIDER` to `anthropic` but leave `LLM_MODEL=gemini/...`, the backend
  says so by name instead of failing later against the wrong vendor's API.

Using a gateway (LiteLLM proxy, vLLM, an enterprise egress proxy)? Set
`LLM_API_BASE` — that also satisfies the key requirement, since gateways
normally hold the real credential themselves.

> **`frontend/.env.local` is not part of the Docker setup.** It exists only for
> running `npm run dev` directly on your machine. Editing it has no effect on
> the containers — see §8 for why.

### Step 2 — Start it

```bash
docker compose up --build -d
```

That's the whole setup. There is no "create these files first" step:
`data/`, `state/` and `ingest-source/` are **directory** mounts, so Docker
creates them if they're missing, and the backend seeds `state/config2.json`
and `state/users.db` inside on first start.

> **Why that's worth a note:** Docker passes a *single file* through a bind
> mount only if the file already exists on the host — otherwise it silently
> creates a **directory** with that name and the app fails in a way that looks
> like an application bug. `users.db` and `config2.json` used to be mounted
> that way, which is why setup previously needed `touch users.db` and a batch
> script to do it for you. Mounting the directory that *contains* them removes
> the failure mode entirely.

First run builds both images and takes several minutes (the backend installs
torch and bakes in an embedding model). Later runs reuse the cache and start in
seconds.

Log in with the `BOOTSTRAP_ADMIN_*` credentials from step 1 — or, if you left
them unset, with **`admin` / `admin`**. Either way you land straight on
**Account settings** and can't go anywhere else until you set a real password
(and, optionally, a real username) — that's `must_change_password`, not a bug.
Once that's done, use the **Admin** link in the dashboard header (or go
straight to `/admin`) to finish LLM setup, approve other users, set token
limits and review the audit log. Everyone else gets an account through §3a
below.

### Open it

| | |
|---|---|
| **Dashboard** | http://localhost:3000 |
| Request an account | http://localhost:3000/register |
| Your own account (password/username) | http://localhost:3000/account |
| Admin console (admins) | http://localhost:3000/admin |
| Backend API docs | http://localhost:8000/docs |
| Backend health | http://localhost:8000/health |

---

## 3a. Users, roles and who can see what

### How accounts are created

Three routes, in the order you'll actually use them:

1. **The first admin** — `BOOTSTRAP_ADMIN_*` in `.env`, applied only to an
   empty user database.
2. **Self-service** — someone visits `/register` and fills in username, email,
   password and the team they think they're on. This creates a **pending**
   account: the row exists and the password is stored, but **it cannot log in
   and has no workspace** until an admin approves it. That's what makes leaving
   registration open safe — signing up gets you into a queue, not into the data.
3. **Admin-created** — an admin adds the account directly on
   **Users → New user**, already active.

An admin approves a request on the same page: pick the workspace and role, hit
Approve. The requested team is shown as a hint, not a grant — the admin decides
which workspace the person actually joins.

Turn signup off entirely with `AUTH_ALLOW_SELF_REGISTRATION=false` (the login
page then stops offering the link). On a trusted internal network you can skip
the queue with `AUTH_AUTO_APPROVE_REGISTRATION=true` — but understand what that
means: anyone who can reach the login page can read the default workspace's
builds.

Everything on the Users page also works from a terminal, which is what you want
when you're locked out:

```bash
docker compose exec backend python -m services.admin_users list-users
docker compose exec backend python -m services.admin_users approve \
    --username jane --workspace platform --role sdet
docker compose exec backend python -m services.admin_users create-user \
    --username bob --role sdet --workspace platform --password '...'
docker compose exec backend python -m services.admin_users set-workspace \
    --username bob --workspace mobile
docker compose exec backend python -m services.admin_users delete-user --username bob
```

Valid roles: `admin`, `cto`, `qa-manager`, `sdet` — the account-permission roles in `services/permissions.py`, not to
be confused with the LLM chat personas in `roles/*.md` (selected per-chat via
the role picker, unrelated to who's allowed to do what). `admin` and `cto` are
equivalent administrator roles; the rest are increasingly read-only — see the
permission matrix in `permissions.py` for exactly what each can do
(`data.view`/`data.ingest`/`data.delete`/`usage.view_own`, admin roles get
everything). An admin-created or -reset account can also be given a **token
limit** (lifetime LLM tokens, 0 = unlimited) and a **force password change on
next login** flag, both from the same Users page.

### The admin console — `/admin`

Five tabs, all admin-only (role `admin` or `cto`), all backed by real
endpoints rather than static pages:

| Tab | What it's for |
|---|---|
| **Overview** | Population by status, workspace count, build count, lifetime token spend, and whether the LLM is actually configured — one screen for "is this deployment healthy". |
| **Users** | Everything in "How accounts are created" above, plus per-account token limits and the force-password-change flag. |
| **Usage** | Every account's lifetime token spend against its limit, with a per-account reset (clears recorded spend, not the limit itself). |
| **Settings** | Provider/model/API key/base URL for the LLM, editable at runtime with **Test connection**. Fields pinned in `.env` show a "locked by env" badge and can't be overridden here — see §7B. |
| **Audit** | Append-only trail of logins, registrations, user edits, password/username changes, LLM settings edits and build deletions — who did what, when, filterable by action. |

### Workspaces — the visibility boundary

A **workspace** is a team. Every build belongs to exactly one, and:

- A normal user sees **only their own workspace's** builds.
- An **admin** (`admin` or `cto`) sees every workspace, labelled by workspace.

There's no workspaces table — a workspace is just the label shared by a set of
users and a set of builds, so creating one means assigning it to somebody. The
Users page autocompletes from workspaces already in use.

This is enforced on the server, in three places, because filtering the build
*list* alone would be cosmetic:

| Where | What it stops |
|---|---|
| `GET /ingestions` | Other teams' builds appearing in the dropdown |
| Every endpoint taking `x-ingestion-id` | Reading another team's build by typing its id |
| `DELETE /ingestions/{id}` | Destroying a build you can't see |

Deletion is narrower than viewing, because it's irreversible:

| Build | Who can delete it |
|---|---|
| Ingested by a person | That person, or an admin |
| From CI / the drop-box (no human creator) | Anyone in its workspace, or an admin |
| Predates ownership tracking (`source: legacy`) | Admins only |

Builds created before this feature existed have no ownership record. Rather
than hiding your history or exposing it to everyone, they're attributed to
`LEGACY_BUILDS_WORKSPACE` (the default workspace). Set that to an unused label
like `archive` to make them admin-only instead.

> **Upgrading an existing install?** The `users` table is migrated in place on
> startup — existing accounts stay active, and land in the default workspace
> until you assign them. Nothing to run by hand.

---

## 4. Everyday use

Everything below runs from the repo root.

| I want to… | Command |
|---|---|
| **Start both services** | `docker compose up -d` |
| **Stop both** | `docker compose down` |
| Watch logs (both) | `docker compose logs -f` |
| Watch one service | `docker compose logs -f backend` |
| See what's running | `docker compose ps` |
| Restart just the backend | `docker compose restart backend` |
| Open a shell in a container | `docker compose exec backend sh` |
| List accounts | `docker compose exec backend python -m services.admin_users list-users` |
| Approve a signup | `docker compose exec backend python -m services.admin_users approve --username <n> --workspace <ws> --role sdet` |
| Switch LLM provider | edit `LLM_PROVIDER`/`LLM_MODEL`/key in `.env`, then `docker compose up -d` |

**Next time you want to run this**, that's just:

```bash
docker compose up -d
```

No `--build`, no setup steps — your `.env`, `state/`, and `data/` are all
still there. Double-clicking `docker-start.bat` does the same thing.

`docker compose down` stops and removes the containers. Your data is untouched.

---

## 5. Getting data in

Four ways in, one thing out: a new `data/ingestion_<timestamp>/` folder that
appears in the dashboard immediately — no restart needed. They share the same
ingester, so a build is indistinguishable whichever route produced it.

| Route | Use it when |
|---|---|
| **5a** Drop-box watcher | Your CI or a cloud bucket can write to the data volume |
| **5b** `POST /ingest/upload` | It can't — a hosted runner, a Lambda, another network |
| **5c** Dashboard "Add Build" | A person is importing something by hand |
| **5d** One-shot container | Bulk/offline import; backend needn't be running |

Every build records **which workspace it belongs to** and who created it, which
is what §3a's visibility rules act on. Each route decides the workspace
differently: 5a from the directory, 5b from the API key, 5c/5d from the caller.

Whichever you use, **paths you type are container paths**. The backend sees
`/app/ingest-source`, not `C:\Users\...`. It has no access to the rest of your
drive.

### 5a. Auto-ingest (drop a file, walk away)

Enabled by `AUTO_INGEST_ENABLED=true` in `.env`. The backend polls
`ingest-source/` and ingests anything new by itself.

```bash
cp my-results.zip ingest-source/
```

That's it. Within ~30 seconds the build appears in the dashboard.

How it decides what to do:

| What you drop | Treated as |
|---|---|
| A folder | `allure` |
| A `.zip` | `allure` (auto-extracted) |
| Anything else | `file` — dispatched by extension: `.csv .tsv .xlsx .xls .json .jsonl .ndjson .parquet .xml .txt .log .pdf .png .jpg .yaml` |

Behaviour worth knowing:

- **Partial uploads are safe.** A file must keep the same size for
  `AUTO_INGEST_STABLE_SECONDS` (default 20s) before it's touched, so a
  half-copied 500MB zip is never handed to the ingester mid-write.
- **Restarts don't re-import.** Processed files are remembered in
  `data/auto_ingest_state.json`, keyed by name + size + mtime. Files can stay
  in the drop-box indefinitely.
- **Replacing a file re-imports it.** New size/mtime means new work, and you
  get a second build rather than an overwrite.
- **Failures aren't retried in a loop.** A failed source is recorded and
  skipped; check `GET /ingest/status/{build_id}`. Re-drop the file to retry.
- **Only one watcher runs.** A lock file elects a single watcher even with
  multiple workers or replicas sharing the volume, so you never get duplicate
  builds.

Tuning knobs: `AUTO_INGEST_INTERVAL_SECONDS` (how often to scan),
`AUTO_INGEST_STABLE_SECONDS` (how long a file must sit still).

Set `AUTO_INGEST_ENABLED=false` if people also use that folder as scratch
space — anything landing there gets ingested with no confirmation.

#### Routing a drop to a workspace

The drop-box is a filesystem, so there's no caller to authenticate — **the path
is the routing**:

```
ingest-source/report.zip             → AUTO_INGEST_DEFAULT_WORKSPACE
ingest-source/platform/report.zip    → workspace "platform"
ingest-source/mobile/report.zip      → workspace "mobile"
```

Point each team's CI at its own prefix and a shared mount serves everybody with
no per-team configuration.

A subdirectory only routes if **a workspace of that name already exists** —
create the team first (assign a user to it). Otherwise it's treated as an
Allure results directory, which is also a legitimate source, and there's no way
to tell the two apart from the name alone. Only one level deep, for the same
reason.

> Anyone who can write to the mount can write to any prefix. That's the right
> model for a volume your own infrastructure controls; if the producer isn't
> that trusted, use §5b instead, where the key fixes the workspace.

### 5b. Push over HTTP — `POST /ingest/upload`

For CI that **can't mount the data volume**: a GitHub Actions runner, a Lambda,
a build agent in another network. Mounting the analytics volume into every CI
environment is exactly the coupling you don't want.

```bash
curl -X POST http://your-host:8000/ingest/upload \
     -H "x-api-key: ci-abc123" \
     -F "file=@allure-results.zip"
```

Issue keys in `.env` as `key:workspace` pairs:

```
INGEST_API_KEYS=ci-abc123:platform,ci-def456:mobile
```

**The key determines the workspace**, so a leaked pipeline token can only write
into the team it was issued for. A logged-in user's bearer token works too, and
uploads into their own workspace.

The file lands in that workspace's drop-box and the watcher picks it up — so
uploads, mounted buckets and manual copies all converge on one code path rather
than three that drift apart. The response tells you if `AUTO_INGEST_ENABLED` is
off rather than leaving you waiting for an ingestion that will never start.

Uploads are written under a `.part` suffix and renamed on completion, so a slow
upload can't be ingested half-written. Cap the size with
`INGEST_UPLOAD_MAX_BYTES` (default 500MB).

### 5c. From the dashboard ("Add Build")

1. Drop your file into `ingest-source/`.
2. In the dashboard, open **Add Build** and type the **container** path:
   `/app/ingest-source/my-results.zip`.
3. Hit ingest. It runs in the background inside the running backend.

The build is created in *your* workspace and recorded as created by you.

### 5d. One-shot container (CI, large imports)

Doesn't need the backend or frontend running at all.

1. Drop your data into `ingest-source/`.
2. Point `config2.json`'s `sources[0].path` at it, using the container path:
   ```json
   {
     "ingestion_name": "my_build",
     "sources": [
       { "type": "allure", "path": "/app/ingest-source/my-results.zip" }
     ],
     "output": { "base_path": "/app/data" }
   }
   ```
3. Run it:
   ```bash
   docker compose run --rm ingest
   ```

`type` is one of `allure`, `file`, or `db` (a live MySQL/TiDB connection —
see `config.json.example` for the connection shape).

### 5e. Deleting a build

Deleting a build from the dashboard's build dropdown removes **everything that
build produced**, not just its test rows:

| Removed | Where it lived |
|---|---|
| Test results, metrics, schema profile | `data/<build>/duckdb` + `lancedb` |
| Saved charts and chat history | `data/<build>/lancedb` |
| Feedback (thumbs up/down, notes) | `data/<build>/lancedb` |
| Summary, job status, ownership record | `data/<build>/*.json` |
| Cached dashboard panels (server + browser) | in-memory / sessionStorage |

That's a property of the layout, not a cleanup routine: everything a build
produces is written *inside that build's own folder*, so removing the folder
removes all of it. What the code has to do on top is close the open
DuckDB/LanceDB handles first — otherwise the file locks make the delete fail
partway on Windows and leave a half-removed build still showing in the list —
and clear the caches on both sides, or the UI keeps rendering a build that no
longer exists.

Two things deliberately *survive* a delete:

- **Token usage accounting**, which is per user and workspace, not per build.
- **The drop-box record.** The file that produced the build stays marked as
  processed in `data/auto_ingest_state.json`. Clearing it while the source
  file is still sitting in the drop-box would have the watcher immediately
  re-ingest what you just deleted. Re-drop the file to import it again.

Who's allowed to delete what is in §3a.

---

## 6. Moving where data lives (cloud or another disk)

The rule: **paths inside the containers are fixed; the host side of every
mount is a variable.** The app always sees `/app/data`. To store that
somewhere else you change one line in `.env` — no rebuild, no code change.

| `.env` variable | Default | Mounted at | Holds |
|---|---|---|---|
| `DATA_DIR` | `./data` | `/app/data` | All ingestions, live runs, LanceDB/DuckDB |
| `STATE_DIR` | `./state` | `/app/state` | `users.db` (accounts) + `config2.json` |
| `INGEST_SOURCE_DIR` | `./ingest-source` | `/app/ingest-source` | Drop-box (watched by auto-ingest) |

All three are **directories**, and Docker creates them at the new location if
they don't exist — there's nothing to prepare before you move.

Examples:

```bash
# Windows — forward slashes, absolute path
DATA_DIR=D:/qa-storage/data
STATE_DIR=D:/qa-storage/state
INGEST_SOURCE_DIR=D:/qa-storage/drop

# Linux / cloud VM — an attached volume or network share
DATA_DIR=/mnt/qa-storage/data
STATE_DIR=/mnt/qa-storage/state
INGEST_SOURCE_DIR=/mnt/qa-storage/drop
```

Then `docker compose up -d`. Point `INGEST_SOURCE_DIR` at a share your CI
writes to, turn on auto-ingest, and builds appear with nothing else wired up.

Two things to get right when you relocate:

- **Move the contents, don't just repoint.** Pointing `STATE_DIR` at an empty
  directory gives you an empty user database and a fresh bootstrap admin —
  your existing accounts are still in the old one, not lost, but not in use.
- **Leave `AUTH_USER_STORE_URL` unset.** Compose points it at
  `/app/state/users.db`, inside the mount. Setting it to a relative path in
  `.env` would put the database inside the container's own filesystem, where
  it disappears on the next `docker compose down`.

Running the image outside compose (Kubernetes, ECS, a plain `docker run`)?
Set `SENTINEL_DATA_DIR` to wherever you mounted storage and the backend will
use it; compose sets this to `/app/data` for you.

---

## 7. After you change code

Only changed layers rebuild. The slow Python dependency layers (torch,
sentence-transformers) stay cached unless `requirements.txt` itself changed,
so a code-only backend rebuild takes seconds.

| You changed | Run |
|---|---|
| Python (`services/`, `universal_ingester/`) | `docker compose up -d --build backend` |
| Frontend (`frontend/`) | `docker compose up -d --build frontend` |
| Both, or you're unsure | `docker compose up -d --build` |
| `requirements.txt` | `docker compose up -d --build backend` (slow — deps reinstall) |
| **Only `.env`** | `docker compose up -d` — **no rebuild**, values are read at container start |
| `NEXT_PUBLIC_API_URL` | Rebuild required — see §8 |

Force a completely clean rebuild if something seems stuck:

```bash
docker compose build --no-cache backend
docker compose up -d
```

---

## 8. Configuration: what's fixed, what you supply

Three different mechanisms, which is the part that trips people up.

### A. Fixed — baked into the image or pinned in compose. Don't touch.

| Setting | Value | Where |
|---|---|---|
| `HF_HOME`, `HF_HUB_OFFLINE` | `/opt/hf-cache`, `1` | `services/Dockerfile` — the embedding model is baked in, so nothing downloads at runtime |
| `PYTHONPATH`, `HOME`, `PATH` | — | `services/Dockerfile` |
| `SENTINEL_DATA_DIR` | `/app/data` | `docker-compose.yml` (both services) |
| `SENTINEL_STATE_DIR` | `/app/state` | `docker-compose.yml` (backend) |
| `SENTINEL_CONFIG2_PATH` | `/app/state/config2.json` | `docker-compose.yml` (frontend + ingest) |
| `AUTH_USER_STORE_URL` | `sqlite:////app/state/users.db` | `docker-compose.yml` (backend) |
| `AUTO_INGEST_DIR` | `/app/ingest-source` | `docker-compose.yml` |
| Container ports | `8000`, `3000` | Dockerfiles — remap the *host* side with `BACKEND_PORT`/`FRONTEND_PORT` |

Everything above ships **inside the image**. A person setting this up never
edits any of it.

### B. You must supply these — `.env`, read at container start

**Nothing is actually required any more.** `SECRET_KEY` self-generates into
`state/secret_key`, the first admin defaults to `admin`/`admin` with a forced
password change, and the LLM provider/model/key can be finished later from
**Admin → Settings**. Everything below is worth setting deliberately for a
real deployment, but an empty `.env` boots a usable install.

| Variable | Required | Default |
|---|---|---|
| `SECRET_KEY` | No | auto-generated into `state/secret_key` on first start |
| `LLM_API_KEY` | No (unless ollama/gateway) | none — set in `.env` or **Admin → Settings** |
| `BOOTSTRAP_ADMIN_USERNAME` / `_PASSWORD` | No | `admin` / `admin`, forced password change on first login |
| `BOOTSTRAP_ADMIN_FORCE_PASSWORD_CHANGE` | No | `true` |
| `MIN_PASSWORD_LENGTH` | No | `8` |
| `LLM_PROVIDER` / `LLM_MODEL` | No | `gemini` / `gemini/gemini-2.5-flash` |
| `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, … | No | per-provider key; wins over `LLM_API_KEY` |
| `LLM_API_BASE` | No | empty — set for a proxy/gateway |
| `CORS_ALLOWED_ORIGINS` | No | `http://localhost:3000` — must contain the frontend's origin |
| `BACKEND_PORT` / `FRONTEND_PORT` | No | `8000` / `3000` |
| `DATA_DIR`, `STATE_DIR`, `INGEST_SOURCE_DIR` | No | see §6 |
| `AUTO_INGEST_*` | No | see §5a |
| `INGEST_API_KEYS` | No | empty — CI upload keys, see §5b |
| `AUTH_ALLOW_SELF_REGISTRATION` | No | `true` — new accounts land pending |
| `AUTH_AUTO_APPROVE_REGISTRATION` | No | `false` |
| `AUTH_DEFAULT_ROLE` / `AUTH_DEFAULT_WORKSPACE` | No | `sdet` / `default` |
| `LEGACY_BUILDS_WORKSPACE` | No | `default` — see §3a |
| `LIVE_INGEST_API_KEY` | No | auto-generated into `state/live_ingest_api_key`, logged once at startup |
| `WEB_CONCURRENCY` | No | `1` — read DOCKER.md §5 before raising |

Change any of these and run `docker compose up -d`. No rebuild. Any value set
here always wins over the same setting made from the admin **Settings** tab —
the UI shows a "locked by env" badge on a field `.env` has pinned.

**Not in `.env` at all** — users, roles, workspaces, token limits, and (unless
pinned above) the LLM provider/model/key. Those are *data*, not configuration:
users live in `users.db` and are managed from the **Admin console**
(`/admin/users`, `/admin/settings`) or via `services.admin_users` (§3a). The
only account that comes from the environment is the first admin, and only
when the database is empty.

### C. Build-time only — needs a rebuild

**`NEXT_PUBLIC_API_URL`** (default `http://localhost:8000`).

Next.js inlines every `NEXT_PUBLIC_*` variable into the client JS bundle when
the image is built. Changing it in `.env` and restarting does nothing:

```bash
NEXT_PUBLIC_API_URL=https://qa-api.example.com docker compose build frontend
docker compose up -d frontend
```

This is the URL your **browser** calls, so it must be reachable from your
machine. `http://backend:8000` will **not** work — that name only resolves
inside the Docker network.

If you change it, update `CORS_ALLOWED_ORIGINS` to match the frontend's origin
or every browser call fails CORS.

---

## 9. Troubleshooting

**Backend won't start, complains about `SECRET_KEY`** — only happens if you
set it yourself and it's under 32 characters; delete the line to let it
auto-generate, or fix the value (§3 step 1).

**Can't log in / "Invalid credentials"** — try `admin` / `admin` first (the
built-in default, unless you set `BOOTSTRAP_ADMIN_*`). Otherwise list existing
accounts: `docker compose exec backend python -m services.admin_users
list-users`. If the table is empty, restart the backend — the bootstrap admin
is created on any startup where the user table is empty, not only the first.

**Signed in but every page 403s / redirects to `/account`** — this is
`must_change_password`, not a bug. It's set on the built-in `admin`/`admin`
account (and on anyone an admin resets a password for with "force change"
left on) specifically so a default or admin-issued password is never a
standing credential. Set a new password on the Account page and every other
route unlocks immediately.

**"Your account is awaiting administrator approval"** — the account registered
but hasn't been approved. An admin approves it on **Users**, or:
`docker compose exec backend python -m services.admin_users approve --username <name> --workspace <ws> --role sdet`.

**A user sees no builds** — they're in a workspace that has none. Check with
`list-users`, then either move them (`set-workspace`) or ingest into their
workspace (§5a). Admins see everything, which is a quick way to confirm the
builds exist at all.

**Builds vanished after upgrading** — check `LEGACY_BUILDS_WORKSPACE` (§3a).
Builds with no ownership record are attributed to that workspace; if it's set
to something nobody belongs to, only admins will see them.

**Chat/chart say the LLM isn't configured** — check **Admin → Settings**: it
shows the effective provider/model/key and which fields `.env` has locked, and
has a **Test connection** button that makes one real call so you find out
immediately, not on the next chat attempt. A field pinned in `.env` always
wins over whatever is saved there — that's the "locked by env" badge.

**LLM calls fail after switching provider** — saving a provider/model
combination that doesn't make sense (e.g. an Anthropic model name under
provider `gemini`) is rejected immediately, in the Settings tab, rather than
saved and discovered later. If a save succeeded but calls 401, the key being
used is the active provider's own variable, falling back to `LLM_API_KEY` —
check you filled in the right one (§3 step 1), or that the key saved in
Settings is actually valid for that provider (**Test connection** confirms
either way).

**`users.db` bind-mount error on first run** — this can no longer happen:
`users.db` and `config2.json` live inside the `state/` **directory** mount and
are created for you. If you're upgrading from the older layout and still have
a stray `users.db` *directory* at the repo root, delete it —
`rm -rf users.db config2.json && docker compose up -d` — and let `state/` take
over. (Move a real `users.db` *file* into `state/` first; it holds your
accounts.)

**Frontend loads but every API call fails** — check `NEXT_PUBLIC_API_URL` was
right at *build* time (§8C) and that `CORS_ALLOWED_ORIGINS` includes the
frontend's origin.

**Build Trends page shows no builds** — confirm the mount is live:
`docker compose exec frontend ls /app/data` should list your `ingestion_*`
folders.

**"Add Build" fails with a path error** — you typed a Windows path. Use
`/app/ingest-source/<file>` and confirm it's really there:
`docker compose exec backend ls /app/ingest-source`.

**Auto-ingest isn't picking up a file** — check in order:

```bash
docker compose logs backend | grep -i auto-ingest
```

- No "watching" line at all → `AUTO_INGEST_ENABLED` isn't `true`.
- "another instance holds the watcher lock" → normal with `WEB_CONCURRENCY>1`
  or multiple replicas; one instance is watching. If nothing is watching, a
  previous container died hard — the lock is taken over automatically once the
  holder is confirmed gone.
- Dotfiles, empty files, and in-flight suffixes (`.part`, `.crdownload`,
  `.tmp`) are skipped by design.
- Already ingested once? Its key is in `data/auto_ingest_state.json`. Touch or
  re-copy the file to re-trigger.

**Backend takes 30–45s on its first request** — that's LanceDB/DuckDB opening
the selected ingestion, not a model download. The healthcheck's `start_period`
already allows for it.

**Using Ollama on the host** — `localhost` inside a container means the
container. Use `OLLAMA_URL=http://host.docker.internal:11434`.

**Port already in use** — set `BACKEND_PORT` / `FRONTEND_PORT` in `.env`. If
you change the frontend port, also update `CORS_ALLOWED_ORIGINS` and rebuild
the frontend with a matching `NEXT_PUBLIC_API_URL`.

**Start completely fresh** (destroys containers, keeps your data):

```bash
docker compose down
docker compose up -d --build
```
