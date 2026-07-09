# Change Implementation Log

Purpose:
- Track every requested code/process change.
- Record exactly what changed and why.
- Keep an auditable trail for enterprise governance.

How to use this file:
- Add one entry per requested change set.
- Keep entries short and factual.
- Include impacted files and rationale.

Entry template:

## YYYY-MM-DD HH:MM UTC - Short title
Requested by:
- User request summary

Changes made:
- File: path/to/file
  - What changed
- File: path/to/another
  - What changed

Reason:
- Why this implementation was chosen
- Tradeoffs/limitations

Validation:
- Checks run
- Result

---

## 2026-07-09 00:00 UTC - LLM dependency sync and config generalization
Requested by:
- Make the framework enterprise-ready and reduce hardcoding.
- Add litellm dependency to tracked dependencies.
- Check and improve whether arbitrary model APIs can be configured via env.
- Create framework knowledge and change-rationale documentation.

Changes made:
- File: requirements.txt
  - Added litellm dependency so the code import in services/llm_client.py is explicitly version-tracked.
- File: services/config.py
  - Generalized LLM env handling:
    - Added fallback chain for API key: LLM_API_KEY -> OPENAI_API_KEY -> GEMINI_API_KEY -> ANTHROPIC_API_KEY.
    - Added provider-agnostic API base key: LLM_API_BASE with fallback to OPENAI_API_BASE.
- File: services/llm_client.py
  - Added model name resolution logic to avoid forced provider prefixing when model is already fully qualified.
  - Added explicit passing of api_key and api_base to LiteLLM from config.
- File: KNOWLEDGE_FRAMEWORK_MAP.md
  - Added full framework map: file responsibilities, runtime/data flow, enterprise gaps, and enhancement roadmap.
- File: CHANGE_IMPLEMENTATION_LOG.md
  - Created this changelog file and initialized process/template.

Reason:
- Dependency lock prevents runtime drift and hidden imports.
- Provider/model/api-base decoupling enables easier migration across model vendors and OpenAI-compatible gateways.
- Documentation establishes a maintainable architecture baseline and traceable change governance.

Validation:
- Static validation by code inspection of import/dependency consistency and env usage flow.
- Functional runtime tests not executed in this pass.

---

## 2026-07-09 00:20 UTC - Phase 1 hardening (free-first)
Requested by:
- Proceed with Phase 1.
- Keep setup free and avoid lock-in/hardcoding.

Changes made:
- File: services/config.py
  - Added runtime config validation with fail-fast checks for key security/runtime fields.
  - Added configurable CORS allowlist parsing via CORS_ALLOWED_ORIGINS.
  - Added auth backend settings for DB-backed users (AUTH_BACKEND, AUTH_USER_STORE_URL).
  - Added FREE-friendly guard: API key is optional when LLM_PROVIDER=ollama.
- File: services/user_store.py
  - Added SQLAlchemy-backed user store module (SQLite by default) with seed-on-empty behavior.
  - Added user model and lookup API used by auth flow.
- File: services/auth.py
  - Added startup initializer for auth backend.
  - Switched authenticate_user to use DB-backed user lookup when AUTH_BACKEND=db.
  - Kept optional fallback to legacy in-code users for safe migration.
- File: services/main.py
  - Added startup calls for config validation and auth store initialization.
  - Replaced wildcard CORS with env-driven allowlist.
- File: services/llm_client.py
  - Added automatic OLLAMA_URL wiring when provider is ollama and no explicit api base is set.
- File: .env.free.example
  - Added free local environment template for Ollama + SQLite auth backend.

Reason:
- Introduces enterprise baseline controls without paid infrastructure.
- Uses fully free local auth storage (SQLite) and supports free local models via Ollama.
- Reduces runtime surprises by validating configuration at startup.

Validation:
- IDE error scan run for all modified backend files.
- Result: no errors found.

---

## 2026-07-09 00:45 UTC - Phase 1.1 auth decoupling and admin CLI
Requested by:
- Create Phase 1.1 continuation.
- Remove runtime dependency on hardcoded users and provide manageable user operations.

Changes made:
- File: services/config.py
  - Replaced legacy fallback toggle with seed bootstrap settings:
    - AUTH_AUTO_SEED_USERS
    - AUTH_SEED_FILE
- File: services/auth.py
  - Removed runtime hardcoded user map usage.
  - Added seed-file loader (`password_hash` or plain `password`) for bootstrap.
  - Added DB/memory backend initialization using external seed data only.
- File: services/user_store.py
  - Added user management operations (upsert, set role, reset password hash, set active, list users).
- File: services/admin_users.py
  - Added admin CLI for user lifecycle management:
    - init-db
    - create-user
    - set-role
    - reset-password
    - set-active
    - list-users
- File: auth_seed_users.json.example
  - Added seed file example for optional bootstrap.
- File: .env.free.example
  - Updated auth settings for seed-file bootstrap model.
- File: README.md
  - Updated authentication documentation and admin CLI commands.
- File: KNOWLEDGE_FRAMEWORK_MAP.md
  - Updated hardcoding status after Phase 1.1.

Reason:
- Removes runtime coupling to embedded credential maps.
- Enables repeatable user onboarding without code edits.
- Keeps stack free-first via SQLite and local tooling.

Validation:
- IDE error scan run for modified service files.
- Result: no errors found.
