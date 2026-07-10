# Sentinel QA Intelligence Platform - Framework Documentation

## 1. Purpose
Sentinel QA Intelligence Platform is a full-stack AI analytics framework that ingests heterogeneous data sources, normalizes them into queryable structures, enables natural-language analytics, generates charts, and persists user/workspace learning context for faster future retrieval.

## 2. High-Level Architecture
- Frontend: Next.js app (dashboard, login, trends, chat, charts).
- Backend: FastAPI service (auth, ingestion orchestration, chat/chart handlers, history APIs).
- Storage:
  - LanceDB for structured tables, vectors, chat/chart history, learning signals, graph edges.
  - DuckDB for low-latency SQL over loaded ingestion tables.
- AI layer:
  - LLM decision/action generation (SQL/vector/direct answer).
  - AI-assisted fallback parser for difficult unstructured ingestion input.
- Connectors: Allure, file, DB, API via universal ingester.

Diagram:
- See [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md)

## 3. Repository Structure
- services/: backend service modules.
- universal_ingester/: ingestion engine and connectors.
- frontend/: Next.js UI.
- data/: per-ingestion persisted outputs.
- roles/: persona prompts.
- projects/: project-specific context.
- scripts/: helper scripts.

## 4. Core Backend Modules
- services/main.py:
  - API entrypoint.
  - Auth/login, ingestion trigger, chat/chart endpoints, history endpoints.
  - Admin cross-user history support via target_user.
- services/auth.py:
  - JWT authentication.
  - User identity now includes workspace_id.
- services/handlers.py:
  - Chat flow and chart generation flow.
  - Uses learning context + related graph concepts to enrich prompts.
- services/memory.py:
  - Chat/chart persistence.
  - Self-learning signals table.
  - Knowledge graph edge table.
  - Workspace-aware filtering and schema migration helpers.
- services/data_loader.py:
  - Loads ingestion into DuckDB.
  - Builds flattened_tests + metrics tables.
  - Generic fallback mapping for non-test schemas.
- services/llm_client.py:
  - Provider abstraction (Gemini/OpenAI/Anthropic/Ollama).

## 5. Ingestion Framework
### 5.1 Universal Ingester
- universal_ingester/ingester.py:
  - Accepts source config.
  - Fetches datasets through source connector.
  - Stores structured/unstructured outputs in LanceDB.
  - Generates embeddings for documents.
  - Produces ingestion summary files.

### 5.2 Connectors
- allure_connector.py: parses Allure result JSON recursively and computes test-level normalized records and metrics.
- file_connector.py: generalized support for csv/tsv/xlsx/xls/json/jsonl/ndjson/parquet/xml/text-like files + fallback.
- db_connector.py: SQLAlchemy table ingestion.
- api_connector.py: REST ingestion into structured DataFrame.

### 5.3 Generalization and AI Parsing
- Structured data normalization now flattens JSON-like columns where possible.
- For unstructured payloads:
  - Heuristic key-value extraction first.
  - AI structured parsing fallback next (if LLM configured).
  - AI parsed rows stored in structured_<dataset>_ai_parsed.

## 6. Data Model and Context Persistence
### 6.1 History Tables
- chat_history and chart_history now include:
  - workspace_id
  - user_id
  - ingestion_id
  - session_id

### 6.2 Learning Tables
- learning_signals:
  - stores prompt/response patterns, keywords, frequency, timestamps.
- knowledge_graph_edges:
  - stores keyword co-occurrence graph with edge weights.

### 6.3 Retrieval Strategy
- For incoming query:
  - pull top learning_signals by overlap/frequency/recency scoring.
  - pull related concepts from knowledge graph.
  - augment model context for better continuity and faster grounding.

## 7. Auth, Roles, and Access Control
- JWT carries sub (username), role, workspace_id.
- Protected endpoints require bearer token.
- Admin/cto can fetch another user history with target_user query parameter.
- Non-admin users are restricted to their own history.

## 8. Frontend Framework
- frontend/app:
  - /login, /dashboard, /build-trends, root landing.
- frontend/components:
  - AIChatbot, AIChatInput, ChartGallery, AIGeneratedChart, selectors, floating helpers.
- frontend/lib/api.ts:
  - API client with auth headers + workspace header propagation.
- frontend/lib/session.ts:
  - stable per-user session id management.

## 9. Request Flows
### 9.1 Chat Flow
1. Frontend sends chat request with ingestion + auth + workspace headers.
2. Backend loads ingestion context if needed.
3. Handler retrieves history + learning signals + graph concepts.
4. LLM decides SQL/vector/answer path.
5. Backend returns response and persists interaction.

### 9.2 Chart Flow
1. Frontend sends chart prompt.
2. Backend determines chart type deterministically.
3. SQL generated/executed and chart code produced.
4. Plotly JSON returned and persisted in chart history + learning signals.

### 9.3 Ingestion Flow
1. Frontend/API submits source path (and optional source type).
2. Backend creates dynamic ingestion config.
3. Universal ingester fetches + normalizes data.
4. LanceDB tables and summary artifacts are written under data/ingestion_<timestamp>/.

## 10. Current Local Validation Status (2026-07-10)
### Passed
- Backend startup from venv: success.
- Health endpoint: 200.
- Login endpoint: 200.
- Protected /ingestions endpoint with bearer token: 200.
- Frontend production build: success.

### Observed Issues
- Frontend lint currently reports multiple pre-existing issues (any typing, React purity/setState-in-effect warnings/errors) in several files.
- These lint issues do not block production build in current setup, but should be cleaned for code quality.

## 11. Operational Commands
### Backend
- Activate configured Python venv and run:
  - d:/Ai-testrig/.venv/Scripts/python.exe -m services.main

### Frontend
- From frontend/:
  - npm install
  - npm run dev
  - npm run build
  - npm run lint

### API Smoke Test Example
- Login:
  - POST /auth/login?username=admin&password=Admin@123
- Health:
  - GET /health
- Protected test:
  - GET /ingestions with Authorization: Bearer <token>

## 12. Configuration Notes
- Required env:
  - SECRET_KEY
  - LLM_PROVIDER
  - LLM_MODEL
  - LLM_API_KEY (or provider equivalent unless local ollama mode)
- Optional env:
  - DEFAULT_WORKSPACE_ID
  - AUTH_BACKEND, AUTH_USER_STORE_URL
  - CORS_ALLOWED_ORIGINS

## 13. Scalability and Improvement Insights
- Short-term:
  - Clean frontend lint errors.
  - Add ingestion parser confidence score to summary artifacts.
- Mid-term:
  - Add explicit tenant/workspace management UI.
  - Add feedback loop from chat/chart usefulness signals.
- Long-term:
  - Hybrid retrieval: graph + vector + SQL plan memory.
  - Streaming/async ingestion for very large datasets.

## 14. Security Notes
- Keep SECRET_KEY strong and private.
- Do not commit API secrets in repo.
- Restrict admin cross-user access to trusted roles only.
- Prefer HTTPS and secure cookie/token handling for production.

## 15. Summary
The framework is now a generalized AI analytics platform with:
- multi-source ingestion,
- workspace/user-aware memory,
- self-learning retrieval,
- graph-assisted context expansion,
- role/project-aware AI interactions,
- and production-capable frontend/backend runtime flow.
