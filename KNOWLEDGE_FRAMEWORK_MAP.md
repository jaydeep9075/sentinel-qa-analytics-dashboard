# Sentinel QA Analytics Dashboard - Framework Knowledge Map

## 1) What this repository is
This is an AI-assisted QA analytics platform with:
- A FastAPI backend for auth, chat, chart generation, ingestion APIs, and data access.
- A Next.js frontend for dashboard UX, role/project scoping, chart gallery, and ingestion triggers.
- A universal ingestion engine that converts external sources (mainly Allure) into LanceDB + DuckDB queryable structures.

The architecture is split for clear boundaries:
- Ingestion and data shaping
- Runtime query/analytics service
- UI and user workflows

## 2) Top-level folders and purpose

### services/
Core backend service (FastAPI).
- main.py: API routes, auth guard integration, ingestion trigger endpoint, and runtime orchestration.
- auth.py: JWT auth, token creation/validation, demo user store.
- handlers.py: Main chat/chart business logic, SQL generation decisions, fallback handling.
- llm_client.py: LLM adapter (LiteLLM) used by chat/chart logic.
- data_loader.py: Loads LanceDB ingestion into DuckDB tables and enforces safe SQL execution.
- memory.py: Chat and chart persistence in LanceDB tables.
- config.py: Environment-driven runtime config (paths, LLM config, limits).
- state.py: In-memory active ingestion state and lazy manager instances.
- prompts.py: Prompt templates and deterministic chart-type logic.
- role_manager.py: Loads role prompt files from roles/.
- project_manager.py: Loads project docs/context and optional semantic retrieval.

### frontend/
Next.js app for login, dashboard, and build trends.
- app/layout.tsx: Root app shell and theme wiring.
- app/login/page.tsx: Login UI and backend auth integration.
- app/dashboard/layout.tsx: Auth gate and context providers.
- app/dashboard/page.tsx: Main dashboard UI, ingestion controls, chart/chat launchers.
- app/build-trends/*: Multi-build trend visualization pages.
- app/api/config2-path/route.ts: Local API route to read/write root config2.json source path.
- app/api/builds/route.ts: Local API route to aggregate build summaries from data/.
- lib/api.ts: Frontend client for backend API calls.
- lib/IngestionContext.tsx: Ingestion selection state.
- lib/RBContext.tsx: Role/project state and permissions.
- components/: UI modules (selectors, chart/gallery, chat controls, branding, etc.).

### universal_ingester/
Source ingestion pipeline.
- ingester.py: Connectors, ingestion orchestration, writing LanceDB tables, summary generation.
- connectors/: Source adapters (allure, file, db, api).
- utils.py: Shared ingestion helpers such as embeddings.

### data/
Generated ingestion outputs.
- ingestion_YYYYMMDD_HHMMSS/
  - lancedb/: vector/structured store for runtime.
  - summary.json, summary.md: build-level summaries.

### roles/
Role prompt files (for example cto, qa-engineer).

### projects/
Project-specific context packages and optional embeddings.

### config2.json
Source-path driven ingestion config used by API/UI ingestion flow.

### requirements.txt
Python dependencies for backend + ingester.

### package.json
Root JS dependencies (lightweight currently).

## 3) Runtime flow (end-to-end)

### A) Login and auth flow
1. Frontend login page calls POST /auth/login.
2. Backend validates bcrypt hash and returns JWT.
3. Frontend stores token in localStorage.
4. Protected backend routes require Bearer token via get_current_user.

### B) Ingestion flow
1. User enters allure-results path from dashboard Add Build.
2. Frontend writes path through frontend API route -> config2.json.
3. Frontend calls backend POST /ingest/config2 with source_path.
4. Backend updates config2.json source and runs UniversalIngester.
5. UniversalIngester creates a new ingestion folder under data/ with lancedb + summaries.

### C) Chat analytics flow
1. Frontend sends /chat with headers x-ingestion-id, x-role, x-project, x-session-id.
2. handlers.handle_chat initializes ingestion into DuckDB if needed.
3. LLM decision prompt chooses action (sql/answer/vector).
4. SQL is sanitized + validated + executed in DuckDB.
5. Response generated and stored in LanceDB chat_history.

### D) Chart generation flow
1. Frontend sends /chart with same runtime headers.
2. Chart type is deterministic (not LLM-decided).
3. LLM proposes SQL -> SQL executes against DuckDB.
4. LLM returns Plotly code within strict template boundaries.
5. Backend executes code, applies visual layout, stores result in chart_history.

## 4) Data contracts and key tables
Primary runtime table: flattened_tests
Typical fields:
- test_name, status, duration, error
- project_name, module_name
- platform_type, browser

Derived aggregates:
- module_metrics
- project_metrics
- test_cases (compatibility table)

## 5) Configuration model
Environment controls backend behavior through services/config.py.
Current important keys:
- LLM_PROVIDER
- LLM_MODEL
- LLM_API_KEY (or provider-specific fallback)
- LLM_API_BASE (or OPENAI_API_BASE fallback)
- PROJECTS_ROOT
- ROLES_ROOT
- SECRET_KEY
- BCRYPT_ROUNDS

## 6) What is already generalized vs still hardcoded

### Already generalized
- Ingestion ID driven runtime context (multi-build support).
- Role/project headers propagate from UI to backend.
- LiteLLM-based LLM client now supports generic API base + key + model naming.
- CORS allowlist is now env-driven (no wildcard by default).
- Runtime env validation is now enforced at backend startup.
- Auth backend supports DB storage (SQLite default) for free local deployment.
- Runtime auth no longer depends on hardcoded users; user lifecycle can be handled via admin CLI.

### Still hardcoded / should be improved
- Seed credentials can still be file-based unless moved to secret manager/bootstrap service.
- Some prompt logic and fallback SQL maps are static and embedded.
- Frontend assumes localStorage token strategy without refresh-token lifecycle.
- Session/chat memory retention policy is fixed and not centrally configurable.

## 7) Enterprise-grade enhancement roadmap

### Platform architecture
- Add clear service boundaries: auth, analytics, ingestion, and AI gateway as separable modules.
- Introduce contract-first schemas for all API payloads with versioning.
- Add tenant and workspace isolation if multiple teams use the same deployment.

### Security
- Move user identity to persistent DB + RBAC policy engine.
- Replace demo user map with user management and password rotation policy.
- Add secrets manager integration, key rotation, and strict env validation at startup.
- Lock CORS to trusted origins only.

### Reliability and operations
- Add background job queue for ingestion and heavy chart generation.
- Add observability stack: structured logs, metrics, distributed tracing.
- Add health tiers: liveness, readiness, dependency checks.
- Add retry/circuit breaker policy for model providers.

### Data and governance
- Add ingestion schema registry and source quality checks.
- Add data retention windows and PII redaction layer.
- Introduce lineage metadata from source record to dashboard metric.

### AI orchestration
- Add provider routing policy (latency/cost/fallback/quality).
- Add response caching and semantic cache for repeated asks.
- Add safety filters, prompt injection checks, and output validators.
- Track model metrics per request: latency, token use, failure class.

## 8) Self-learning and graph-based learning recommendations

### Self-learning
Use a retrieval-first feedback loop rather than self-modifying prompts in production:
- Capture user feedback on answers/charts.
- Store feedback as supervised examples.
- Train/evaluate offline and promote only validated prompt/model configs.
- Add automated regression tests for known analytics questions.

### Graph-based learning
Recommended stack:
- Graph store: Neo4j (best for enterprise graph traversal + ecosystem).
- Alternative OSS: Memgraph or ArangoDB.
- Model layer: graph embeddings (Node2Vec/GraphSAGE) + retrieval fusion with vector search.

Practical graph entities:
- TestCase, Module, Project, Build, FailureSignature, Requirement, Owner.

Graph edges:
- FAILED_IN, DEPENDS_ON, AFFECTS, REGRESSED_IN, OWNED_BY.

Use cases:
- Root-cause neighborhoods for repeated failures.
- Impact analysis before release.
- Learning failure propagation patterns across modules and builds.

## 9) Recommended next implementation sequence
1. Add env validation and config schema (pydantic settings) with startup fail-fast checks.
2. Replace hardcoded users with persistent auth store and role policies.
3. Introduce async job queue for ingestion/chart workloads.
4. Add provider router abstraction for multi-model failover and cost guardrails.
5. Add graph DB integration for failure dependency analysis.
6. Add automated evaluation suite for chat/chart quality before every release.
