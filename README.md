# Sentinel QA Intelligence - AI-Powered Test Analytics Platform

## Overview

Sentinel QA Analytics Dashboard is an intelligent analytics platform for Quality Assurance teams to visualize, analyze, and derive insights from test data. It combines traditional analytics with AI-powered natural language processing, JWT-secured APIs, and Allure report ingestion.

### Key Capabilities

- **JWT Authentication**: Login-protected dashboard and API; role-aware sessions (CTO, QA Engineer)
- **Allure Ingestion**: Import `allure-results` directories via `config2.json`, CLI, or the dashboard “Add Build” flow
- **Build Trend Analysis**: Compare pass rates, durations, and regressions across builds at `/build-trends`
- **Persona-Driven AI Insights**: Context-aware natural language queries tailored by role (`roles/`) and project (`projects/`)
- **Resilient Analytics**: SQL validation, sanitization, and multi-table fallback mechanisms
- Real-time KPI monitoring and test status visualization
- Module stability metrics (FSA / HSA / WDH store grouping from Allure suites)
- Slow test detection and mobile vs desktop breakdowns
- AI-driven chart generation from plain English prompts
- Conversational analytics with session and chart history
- Flexible AI backend support (Google Gemini, Ollama, OpenAI, Anthropic)
- Dark / light theme toggle

### Architecture Components

- **Backend API Service** (Python/FastAPI): Auth, data processing, analytics, AI interactions
- **Frontend Dashboard** (Next.js 16): Landing page, login, dashboard, build trends
- **Universal Ingester**: Allure, file, database, and API connectors
- **AI Enhancement Module**: Natural language querying and chart generation with role/project context

---

## Quick Setup

### Prerequisites

- Python 3.10+
- Node.js 18+

### Installation

```bash
# Clone repository
git clone https://github.com/jaydeep9075/sentinel-qa-analytics-dashboard.git
cd sentinel-qa-analytics-dashboard

# Python virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

# Backend dependencies (includes auth packages)
pip install -r requirements.txt
pip install python-jose[cryptography] bcrypt

# Root .env — see Environment Configuration below
# Create frontend/.env.local with NEXT_PUBLIC_API_URL=http://localhost:8000

# Optional: configure Allure source path in config2.json, then ingest
cd universal_ingester
python ingester.py
cd ..

# Start backend (from repo root)
python -m services.main

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

### Access Points

| Service | URL |
|---------|-----|
| Landing page | http://localhost:3000 |
| Login | http://localhost:3000/login |
| Dashboard | http://localhost:3000/dashboard |
| Build trends | http://localhost:3000/build-trends |
| Backend API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

---

## Authentication

The API uses **Bearer JWT** tokens. After login, the frontend stores the token in `localStorage` and sends it on protected requests.

| Endpoint | Auth |
|----------|------|
| `GET /health` | Public |
| `POST /auth/login` | Public |
| `POST /ingest/config2` | Public |
| `/chat`, `/chart`, `/ingestions`, `/data/status`, etc. | **Bearer token required** |

Auth users are managed through the local DB-backed store (SQLite by default).

Initialize DB schema:

```bash
python -m services.admin_users init-db
```

Create/update a user:

```bash
python -m services.admin_users create-user --username admin --role cto
```

Reset password:

```bash
python -m services.admin_users reset-password --username admin
```

List users:

```bash
python -m services.admin_users list-users
```

Optional seed bootstrap:
- Copy `auth_seed_users.json.example` to `auth_seed_users.json`
- Set `AUTH_AUTO_SEED_USERS=true` in `.env`
- Set `AUTH_SEED_FILE=./auth_seed_users.json` (or your custom path)

Set a strong `SECRET_KEY` in `.env` before production use.

For complete user bootstrap, add-user, and validation commands, see:
- `USER_SEED_STEPS.md`

---

## Data Ingestion

### 1. Allure via `config2.json` (recommended)

Edit `config2.json` at the repo root:

```json
{
  "ingestion_name": "allure_demo",
  "sources": [
    {
      "type": "allure",
      "path": "/absolute/path/to/allure-results"
    }
  ],
  "output": {
    "base_path": "../data"
  }
}
```

Then run:

```bash
cd universal_ingester
python ingester.py
```

### 2. Dashboard / API ingestion

From the dashboard, use **Add Build** to set the Allure path (updates `config2.json` via `/api/config2-path`) and trigger ingestion through `POST /ingest/config2` with body `{ "source_path": "..." }`.

Each run creates a timestamped folder under `data/ingestion_YYYYMMDD_HHMMSS/` with LanceDB tables and a `summary.json`.

### 3. Other source types

The universal ingester also supports file, database, and API connectors—configure sources in your ingestion config as needed.

---

## Environment Configuration

### Root `.env`

```env
# LLM
LLM_PROVIDER=gemini
LLM_API_KEY=your_api_key_here
LLM_MODEL=models/gemini-2.5-flash

# Role-based AI context
PROJECTS_ROOT=./projects
ROLES_ROOT=./roles

# Auth (required)
SECRET_KEY=generate_a_long_random_secret_here
BCRYPT_ROUNDS=12
```

### `frontend/.env.local`

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

For remote development (e.g. accessing the dev server by IP), add allowed origins in `frontend/next.config.ts`:

```ts
allowedDevOrigins: ['your.server.ip'],
```

---

## Roles & Projects

- **`roles/`** — Markdown persona instructions (`cto.md`, `qa-engineer.md`) loaded by `RoleManager` and sent to the LLM via the `x-role` header.
- **`projects/`** — Per-project context (e.g. FSA, HSA, WDH) with optional embeddings; selected via `x-project` on chat/chart requests.

Use the dashboard **Role** and **Project** selectors to scope AI responses.

---

## Project Structure

```
sentinel-qa-analytics-dashboard/
├── services/                 # FastAPI backend
│   ├── main.py              # Routes (public + protected)
│   ├── auth.py              # JWT login & user store
│   ├── handlers.py          # Chat & chart logic
│   ├── llm_client.py        # LLM abstraction
│   ├── data_loader.py       # DuckDB / LanceDB access
│   ├── memory.py            # Chat & chart history
│   ├── role_manager.py      # Persona loading
│   ├── project_manager.py   # Project context
│   └── config.py            # Paths & LLM settings
├── frontend/                # Next.js app
│   ├── app/
│   │   ├── page.tsx         # Landing
│   │   ├── login/           # Auth UI
│   │   ├── dashboard/       # Main analytics UI
│   │   ├── build-trends/    # Multi-build charts
│   │   └── api/             # builds.json, config2-path
│   ├── components/          # Charts, chat, selectors
│   └── lib/api.ts           # Backend client + Bearer auth
├── universal_ingester/
│   ├── ingester.py
│   └── connectors/
│       ├── allure_connector.py
│       ├── file_connector.py
│       ├── db_connector.py
│       └── api_connector.py
├── config2.json             # Allure ingestion config
├── roles/                   # AI persona definitions
├── projects/                # Project-specific context
├── data/                    # Ingestion outputs (LanceDB)
└── requirements.txt
```

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI, Python, Uvicorn |
| Auth | JWT (python-jose), bcrypt |
| Frontend | Next.js 16, React 18, TypeScript, Tailwind CSS 4 |
| Database | LanceDB, DuckDB |
| AI / LLM | Google Gemini, OpenAI, Anthropic, Ollama |
| Visualization | Plotly, Recharts, ApexCharts |
| Embeddings | Sentence Transformers |
| Ingestion | Allure JSON, files, MySQL, APIs |

---

## API Quick Reference

**Login**

```http
POST /auth/login?username=aditya&password=Pass@123
```

**Chat** (requires `Authorization: Bearer <token>`)

```http
POST /chat
x-ingestion-id: ingestion_20260506_110116
x-role: qa-engineer
x-project: FSA
Content-Type: application/json

{ "message": "How many tests failed?" }
```

**List ingestions**

```http
GET /ingestions
Authorization: Bearer <token>
```

See interactive docs at http://localhost:8000/docs after starting the backend.
