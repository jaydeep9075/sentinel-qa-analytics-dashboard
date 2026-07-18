# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Commonly Used Commands
**Development & Testing:**
- `python -m services.main`: Start the backend API service
- `npm run dev`: Build and run the frontend dashboard (Next.js 16)
- `cd universal_ingester && python ingester.py`: Ingest Allure test results
- `python -m pip install -r requirements.txt`: Install Python dependencies
- `cd frontend && npm install`: Install frontend dependencies
- `python -m pytest tests/`: Run unit/integration tests (supports CLI flags)
- `python -m services.admin_users list-users`: Manage auth users
- `python -m services.admin_users init-db`: Initialize SQLite database

**Configuration:**
- Edit `config2.json` to define Allure ingestion paths
- Update `frontend/.env.local` with `NEXT_PUBLIC_API_URL` pointing to backend
- Set `SECRET_KEY` in `.env` for JWT security

---

## High-Level Architecture
1. **Authentication Layer**  
   - JWT-based authentication via FastAPI backend
   - User management through SQLite database
   - Role-based access control (CTO, QA Engineer roles)

2. **Data Pipeline**  
   - **Ingestion**: Allure test results → `config2.json` → Universal Ingester → LanceDB/DuckDB
   - **Storage**: Test metadata, clinical project data (FSA/HSA/WDH), artificial embeddings
   - **Analytics Engine**: FastAPI handles processing requests with AI-enhanced insights

3. **AI/ML Layer**  
   - LLM-powered NLQ for QA queries with role/project context
   - AI-generated test visualization (AllieCharts, Plotly)
   - Context-aware test analysis via embeddings.lance database

4. **Frontend Interface**  
   - Next.js dashboard with build trend visualizations
   - Role/project selectors for AI query scoping
   - Interactive chat interface with session history

---

## Critical Files for Claude to Navigate
1. `config2.json` - Allure ingestion configuration
2. `roles/` directory - Persona definitions for AI context
3. `projects/` directory - Project-specific context files
4. `test/` directory - Test suites and edge case scenarios
5. `universal_ingester/` - Core data ingestion module

---

## Key Implementation Patterns
- JWT token expiration handled by ArrowDateTime library
- Role/project context propagation via HTTP headers
- Allure result processing with LanceDB integration
- Fallback mechanisms for missing data paths
- Elliptic curve signature generation in auth module

---

This structure emphasizes the critical metadata for Claude to efficiently navigate the codebase. For first-time usage, prioritize understanding the `config2.json` ingestion flow and role/project context handling.