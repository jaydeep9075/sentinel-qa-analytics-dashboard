# Work Log — Docker, Auth & Multi-User Hardening

Handover note. What was changed, what was verified, and what's still open.
Setup instructions live in [SETUP.md](SETUP.md); reference detail in
[DOCKER.md](DOCKER.md). This file is only the "where we got to".

**Status:** all five items below are done, live and verified.

---

## 1. LLM — provider, model and key all come from outside

Switching vendors is a `.env` edit plus a restart. No rebuild, no code change.

- The key resolves **per provider**: the active provider's own variable
  (`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `<PROVIDER>_API_KEY`) wins, and
  `LLM_API_KEY` is the fallback. Every vendor's key can sit in `.env` at once.
- **Any** litellm provider works — no whitelist. Ones without a built-in
  default model must set `LLM_MODEL` explicitly.
- A provider/model mismatch (`LLM_PROVIDER=anthropic` + `LLM_MODEL=gemini/...`)
  is refused at startup by name.

*Bug fixed:* key resolution was provider-blind — it checked `LLM_API_KEY`
first, so switching to Claude would have sent the **Gemini key to Anthropic**
and failed as a 401 with nothing in the config looking wrong.

**Verified:** 10/10 cases (gemini, anthropic-with-own-key, generic fallback,
mismatch, missing key, unknown provider, gateway, ollama, bare model name).

To switch to Claude: put the key in `ANTHROPIC_API_KEY`, set
`LLM_PROVIDER=anthropic` and `LLM_MODEL=anthropic/claude-opus-5`, restart.

---

## 2. Users — registration with admin approval

Chosen model: **self-service signup + admin approval**.

- `/register` creates a **pending** account — password stored, but it cannot
  log in and has no workspace until an admin approves it. Signing up gets you
  into a queue, not into the data.
- `/admin/users` — approve, set role/workspace, disable, delete, reset
  password. Full CLI parity via `python -m services.admin_users`.
- First admin comes from `BOOTSTRAP_ADMIN_*`, applied only when the user table
  is empty (can't override an existing account).
- `AUTH_ALLOW_SELF_REGISTRATION=false` turns signup off;
  `AUTH_AUTO_APPROVE_REGISTRATION=true` skips the queue (trusted networks).

The `users` table gained `workspace_id`, `email`, `status`,
`requested_workspace`, migrated **in place on startup**.

---

## 3. Visibility — workspace is the boundary

A build belongs to one workspace. Normal users see only theirs; admins see all.
Enforced in three places, because filtering the list alone would be cosmetic:

| Where | Stops |
|---|---|
| `GET /ingestions` | Other teams' builds in the dropdown |
| Middleware on `x-ingestion-id` | Reading a build by typing its id (~14 routes) |
| `DELETE /ingestions/{id}` | Destroying a build you can't see |

**Three real holes found and fixed** (all proven live before the fix):

1. **Login accepted a client-chosen workspace** — `?workspace_id=acme` minted a
   token for a workspace that existed nowhere. Now server-side only.
2. **`x-workspace-id` outranked the token** — an unauthenticated tenant switch.
   Now admin-only.
3. **`DELETE /ingestions/{id}` had no authorization** and concatenated the id
   straight into a path before `shutil.rmtree`. Now role-checked and
   traversal-guarded.

Also fixed: a blanket `except Exception` on that endpoint would have swallowed
the new 403 into a `200 {"error": ...}`.

Ownership is recorded as `owner.json` inside each build folder, so it travels
with the directory. Pre-existing builds have none and are attributed to
`LEGACY_BUILDS_WORKSPACE` (default: `default`) — set it to `archive` to make
them admin-only.

**Delete rules:** hand-ingested → creator or admin. CI/drop-box (no human
creator) → anyone in its workspace. Legacy → admins only.

**Verified:** 26/27 checks. The one failure was the test's own bad assumption
(it expected demoting `zz-admin` to be blocked, but `admin` is role `cto`,
which also counts as admin — so allowing it was correct). The last-admin guard
was verified separately on a scratch DB.

---

## 4. Ingestion triggers + delete cascade + generalised Docker

**Four ways in**, one ingester. Each decides the workspace differently:

| Route | Workspace from |
|---|---|
| Drop-box watcher | The path — `ingest-source/platform/x.zip` → `platform` |
| `POST /ingest/upload` | The API key (`INGEST_API_KEYS=key:workspace`) |
| Dashboard "Add Build" | The caller |
| `docker compose run --rm ingest` | config2.json |

A drop-box subdirectory only routes if a workspace of that name exists —
otherwise it stays an Allure results directory, which is also a valid source.

**Delete now removes everything the build produced** — charts, chat, feedback,
metrics, summary, caches. That's mostly a property of the layout (it all lives
in the build's own folder); what the code adds is closing the DuckDB/LanceDB
handles *first* (file locks otherwise make `rmtree` fail partway on Windows and
leave a half-removed build still listed) and clearing caches on both server and
browser. A deleted build now 404s instead of serving an empty dashboard.

Deliberately survives a delete: token usage (per user, not per build) and the
drop-box processed-record (clearing it would have the watcher instantly
re-ingest what you just deleted).

**First run needs nothing but `.env`.** `users.db` and `config2.json` moved
into a `state/` **directory** mount. Docker only passes a *single file* through
a bind mount if it already exists — otherwise it creates a directory with that
name and the app fails in a way that looks like an application bug. That's why
setup used to need `touch users.db`. Mounting the containing directory removes
the failure mode; the backend seeds the files inside on startup.

**Verified on a genuinely clean deployment** (fresh ports, paths that did not
exist, nothing pre-created): directories self-created, config seeded, bootstrap
admin created, CSV dropped → auto-ingested → deleted. **15/15 passed.**

> **Upgrade note for other checkouts:** with the stack stopped,
> `mkdir state && mv users.db config2.json state/`. Already done here.

---

## 5. First-run zero-config bootstrap + full admin console

Landed. Deviated from the plan on one point (see below), but resolves the
same problem: `docker compose up -d` on a completely empty `.env` now
produces a deployment you can sign into, configure, and administer end to
end from the browser.

### Decision that changed from the plan: appliance pattern, not a `/setup` wizard

The plan called for a dedicated `/setup` screen reachable only while zero
users exist. Built instead: the bootstrap admin now defaults to `admin`/`admin`
(previously `BOOTSTRAP_ADMIN_*` were required), created with
`must_change_password=true`. A new backend gate —
`credential_change_middleware` in `main.py` — refuses **every** route except
`/auth/me`, `/auth/permissions` and the two account-settings endpoints until
that flag is cleared, so the well-known default password is a one-time door,
not a standing credential. This is the router/Grafana/Jenkins pattern rather
than a bespoke wizard, and it does the same job with far less surface area:
no separate screen, no "is setup already done" state machine, no route that
only exists for the first five minutes of a deployment's life. LLM setup
still happens after login, in **Admin → Settings**, exactly as planned.

`SECRET_KEY` auto-generation landed as planned: unset in `.env`, it's
generated into `state/secret_key` on first start and reused after that (env
still wins when set). Combined with the bootstrap default, required `.env`
values are now genuinely **zero**.

### What shipped

1. **Zero-config bootstrap** — `config.py` (`BOOTSTRAP_ADMIN_*` defaults,
   `SECRET_KEY` auto-gen, `MIN_PASSWORD_LENGTH`), `user_store.py`
   (`must_change_password`, `token_limit`, `full_name`, `last_login_at`
   columns, additive migration), `auth.py` (`_bootstrap_admin_if_empty` forces
   the change flag whenever the password in use is the literal default).
2. **Forced credential change** — `main.py`'s `credential_change_middleware`
   plus two new endpoints, `POST /auth/account/password` and
   `POST /auth/account/username` (`auth.change_own_password` /
   `change_own_username`). A username change re-keys the row (`rename_user`)
   *and* everything that referenced the old username by value —
   `token_usage_store.rename_user()` and `build_owner.rename_creator()` — so a
   rename doesn't orphan someone's usage history or their delete rights on
   builds they created.
3. **Role permission matrix** — new `services/permissions.py`. Six roles
   (`admin`/`cto` wildcard-everything, `qa-manager`/`qa-engineer`
   view+ingest+delete, `developer`/`viewer` view-only), a `require_permission()`
   FastAPI dependency, `GET /auth/permissions` for the frontend to gate on
   instead of hardcoding role-name checks. Wired into ingest (`POST
   /ingest/config2`, `POST /ingest/upload`) and delete (`DELETE
   /ingestions/{id}`) ahead of the existing ownership checks in
   `build_owner.py`, which are unchanged and still apply on top.
4. **Token quotas** — `token_limit` per account (0 = unlimited), enforced in
   `main._enforce_token_quota()` at the top of `/chat` and `/chart` — checked
   *before* any LLM call, not inside `llm_client`, so a request that's going
   to be refused doesn't burn tokens getting there. `token_usage_store.py`
   gained `get_lifetime_total()` (what the quota check compares against —
   account-wide, not per-workspace), `list_usage_by_user()`, `reset_usage()`,
   `rename_user()`.
5. **Runtime LLM settings** — new `services/app_settings.py`: a small
   `app_settings` table in the same SQLite database, resolution order **env >
   database > default** decided *per field* (provider/model/key/base can each
   independently be env-locked or admin-editable). `llm_client.py` now reads
   this on every call instead of the module-level `config.LLM_*` constants, so
   a change in the Settings tab takes effect for the next request with no
   restart. `GET/PUT /admin/settings/llm` plus `POST
   /admin/settings/llm/test`, which fires one real minimal completion against
   a candidate config without saving it — resolves the plan's open question
   ("should the API key be editable from the UI") as **yes**, masked in every
   response (`app_settings.mask_api_key`), admin-only.
6. **Audit log** — new `services/audit_log.py`, an append-only table
   (self-pruning past 20k rows) recording logins (success/failed/blocked),
   registrations, user create/update/approve/delete, password
   resets/changes, username changes, LLM settings edits, usage resets and
   build deletions. `GET /admin/audit`, filterable by action/actor.
7. **Admin console** — `frontend/app/admin/layout.tsx` (auth-gated shell,
   five tabs) plus `page.tsx` under `admin/{,users,usage,settings,audit}`.
   `admin/users/page.tsx` folded into the shared layout and extended with
   token-limit and force-password-change controls. New
   `frontend/lib/usePermissions.ts` hook backs both the admin nav and two
   hide-only UI gates elsewhere (`IngestionSelector`'s delete button,
   dashboard's "Add New Build") — hiding only, since every one of those
   actions is independently enforced server-side regardless of what the
   client shows.
8. **Account page** — `frontend/app/account/page.tsx`, self-service
   username/password change, with a `?forced=1` mode the login page and
   dashboard both redirect into when `must_change_password` is set.

**Verified live** against a scratch `state/` directory (fresh SQLite, no
pre-existing users): bootstrap produced `admin`/`admin` with the change flag
set; every route 403'd until the password was changed; role-based 403s
confirmed for a `viewer` account attempting ingest and admin routes; a
username rename correctly re-issued a token, invalidated the old username
for login, and preserved usage history under the new one; a token quota of 1
correctly returned 429 from `/chat` *before* any LLM call once simulated
usage exceeded it, and correctly cleared after an admin reset; the full audit
trail was reviewed end to end. Frontend: `tsc --noEmit` clean, `npm run build`
succeeds, all six new routes present in the route table.

---

## Files

**New (this round):** `services/permissions.py`, `services/app_settings.py`,
`services/audit_log.py`, `frontend/app/account/page.tsx`,
`frontend/app/admin/layout.tsx`, `frontend/app/admin/page.tsx`,
`frontend/app/admin/{usage,settings,audit}/page.tsx`,
`frontend/lib/usePermissions.ts`

**New (earlier rounds):** `services/auto_ingest.py`, `services/build_owner.py`,
`frontend/app/register/page.tsx`, `frontend/app/admin/users/page.tsx`,
`SETUP.md`, `DOCKER.md`, `docker-*.bat`, `config2.docker.json.example`

**Changed (this round):**
`services/{config,auth,user_store,main,llm_client,token_usage_store,build_owner}.py`,
`frontend/{app/login,app/dashboard,app/admin/users}/page.tsx`,
`frontend/components/IngestionSelector.tsx`, `SETUP.md`

**Changed (earlier rounds):** `services/{ingestion_jobs,admin_users}.py`,
`services/Dockerfile`, `universal_ingester/ingester.py`, `docker-compose.yml`,
`.env.example`, `.gitignore`, `.dockerignore`, `frontend/lib/api.ts`

**Also fixed along the way:** `services/Dockerfile` `CMD` lacked `exec`, so
`sh` stayed PID 1 and never forwarded SIGTERM — uvicorn was SIGKILLed 10s after
every `docker stop`, FastAPI's shutdown hooks never ran, and DuckDB connections
never closed cleanly. Pre-existing; found because the auto-ingest lock wasn't
being released on restart.

---

## Current state

Stack up and healthy. **11 builds and both accounts (`admin` cto, `qa1`
qa-engineer, both workspace `default`) intact. Zero errors in the backend log.**
All test users, files and temporary keys cleaned up. Item 5's verification ran
against an isolated scratch `state/` directory, not this one — the real
`state/users.db` above was never touched by this round's testing.

```bash
docker compose up -d          # start
docker compose logs -f        # watch
docker compose ps             # status
```

Dashboard http://localhost:3000 · API docs http://localhost:8000/docs
