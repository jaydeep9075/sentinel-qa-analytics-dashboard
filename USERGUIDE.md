# Sentinel QA Intelligence Dashboard — User Guide

## 1. Project Overview

**Sentinel QA Intelligence Dashboard** is an AI-powered test analytics platform for QA teams. It ingests test data (primarily from Allure reports), stores results in **LanceDB**, and provides:

- **Natural language querying** — Ask questions about test results in plain English (powered by RAG + SQL)
- **AI chart generation** — Auto-generate Plotly charts from plain English prompts
- **Build trend analysis** — Compare pass rates, durations, and regressions across multiple ingestion runs
- **Role-based AI personas** — Switch between CTO (executive) and QA Engineer (technical) perspectives
- **Project-specific context** — Load project documentation for contextual AI responses
- **Drag-and-drop chart gallery** — Organize and manage generated charts
- **Dark/light theme** — Toggle between themes

**Repository**: `https://github.com/jaydeep9075/sentinel-qa-analytics-dashboard.git`

---



## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (Next.js 16)                    │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐    │
│  │ Landing │ │  Login   │ │Dashboard │ │ Build Trends  │    │
│  │  Page   │ │  Page    │ │  Page    │ │    Page       │    │
│  └────┬────┘ └────┬─────┘ └────┬─────┘ └───────┬───────┘    │
│       └───────────┴────────────┴───────────────┘            │
│                        │ HTTP (port 3000)                   │
│                        ▼                                    │
│              ┌─────────────────┐                            │
│              │  lib/api.ts     │  ← Bearer JWT auth         │
│              └────────┬────────┘                            │
└───────────────────────┼─────────────────────────────────────┘
                        │ HTTP (port 8000)
                        ▼
┌────────────────────────────────────────────────────────────┐
│                  Backend (FastAPI / Python)                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │  auth.py │ │main.py   │ │handlers  │ │ data_loader   │  │
│  │ (JWT)    │ │(Routes)  │ │(Chat/    │ │ (DuckDB/      │  │
│  │          │ │          │ │ Charts)  │ │  LanceDB)     │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ llm_     │ │ memory   │ │ prompts  │ │ role_manager  │  │
│  │ client   │ │ (history) │ │ (765 ln) │ │ & project_mgr│  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
└───────────────────────┬────────────────────────────────────┘
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
    ┌──────────┐ ┌──────────┐ ┌──────────────┐
    │ LanceDB  │ │ DuckDB   │ │  LLM APIs    │
    │ (Vector  │ │ (SQL on  │ │ (Gemini,     │
    │  Store)  │ │ LanceDB) │ │  OpenAI, etc)│
    └──────────┘ └──────────┘ └──────────────┘
                        ▲
                        │
          ┌─────────────┘
          ▼
┌───────────────────────────────────────────────────────────┐
│               Universal Ingester (Python)                 │
│  ┌────────┐ ┌─────────┐ ┌────────┐ ┌──────────────┐       │
│  │ Allure │ │  Files  │ │   DB   │ │    APIs      │       │
│  │Connector│ │Connector│ │Connector│ │  Connector │       │
│  └────────┘ └─────────┘ └────────┘ └──────────────┘       │
└───────────────────────────────────────────────────────────┘
```

**Data flow**:

1. **Ingestion** — Allure results (or files, DB, APIs) are parsed by the ingester and stored as timestamped LanceDB tables under `data/ingestion_YYYYMMDD_HHMMSS/`
2. **Loading** — When a build is selected, `data_loader.py` loads LanceDB tables into DuckDB as in-memory tables
3. **Querying** — The LLM receives the DB schema + conversation history, decides an action (SQL query / Vector search / Direct answer), executes it, and returns a natural language response
4. **Charting** — A deterministic chart-type detector selects the visualization, generates Plotly JSON, and renders it via `react-plotly.js`

---



## 3. Tech Stack


| Component          | Technology                                         |
| ------------------ | -------------------------------------------------- |
| Backend framework  | FastAPI 0.115.6 (Python 3.10+)                     |
| ASGI server        | Uvicorn 0.34.0                                     |
| Auth               | JWT (python-jose), bcrypt                          |
| Frontend framework | Next.js 16.2.2, React 18.3.1                       |
| Frontend styling   | Tailwind CSS 4, Framer Motion 12                   |
| Vector database    | LanceDB 0.12.0                                     |
| SQL engine         | DuckDB 1.1.3 (in-memory, registers LanceDB tables) |
| AI / LLM providers | Google Gemini, OpenAI, Anthropic Claude, Ollama    |
| Embeddings         | Sentence Transformers (all-MiniLM-L6-v2)           |
| Charts             | Plotly 5.24.1, ApexCharts 3.45, Recharts 2.10      |
| Drag-and-drop      | @dnd-kit 6.3.1                                     |
| Data fetching      | SWR 2.4.1, Axios 1.13                              |
| Icons              | Lucide React 0.577                                 |


---



## 4. Prerequisites


| Requirement | Version | Check Command      |
| ----------- | ------- | ------------------ |
| Python      | 3.10+   | `python --version` |
| Node.js     | 18+     | `node --version`   |
| npm         | 9+      | `npm --version`    |
| Git         | any     | `git --version`    |


---



## 5. Step-by-Step Local Setup



### 5.1 Clone the Repository

```bash
git clone https://github.com/jaydeep9075/sentinel-qa-analytics-dashboard.git
cd sentinel-qa-analytics-dashboard
```



### 5.2 Python Virtual Environment

**Windows (PowerShell):**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**

```cmd
python -m venv venv
venv\Scripts\activate
```

**macOS / Linux:**

```bash
python3 -m venv venv
source venv/bin/activate
```

You should see `(venv)` in your terminal prompt.

### 5.3 Install Backend Dependencies

```bash
pip install -r requirements.txt
pip install python-jose[cryptography] bcrypt
```

> **Note**: `python-jose[cryptography]` and `bcrypt` are not in `requirements.txt` but are required for JWT auth. Install them separately as shown above.

> **Troubleshooting**: If you encounter issues with `torch` or `sentence-transformers`, use the version-independent command from requirements.txt:
>
> ```bash
> pip install fastapi uvicorn pydantic python-multipart pandas numpy duckdb lancedb pyarrow google-generativeai sentence-transformers requests openai anthropic plotly kaleido python-dotenv pymysql sqlalchemy typing-extensions python-jose[cryptography] bcrypt
> ```



### 5.4 Configure Environment Variables



#### Root `.env` (backend configuration)

Create or edit `.env` in the repository root:

```env
# LLM Configuration
LLM_PROVIDER=gemini

LLM_API_KEY=your-gemini-api-key-here
LLM_MODEL=models/gemini-2.5-flash

# Role-based AI context directories
PROJECTS_ROOT=./projects
ROLES_ROOT=./roles

# JWT Authentication (REQUIRED - change for production)
SECRET_KEY=generate-your-own-32-plus-char-random-secret
BCRYPT_ROUNDS=12
```


| Variable        | Required | Description                                                                        |
| --------------- | -------- | ---------------------------------------------------------------------------------- |
| `LLM_PROVIDER`  | Yes      | One of: `gemini`, `openai`, `anthropic`, `ollama`                                  |
| `LLM_API_KEY`   | Yes      | API key for the selected LLM provider                                              |
| `LLM_MODEL`     | Yes      | Model name (e.g. `models/gemini-2.5-flash`, `gpt-4`, `claude-3-5-sonnet-20241022`) |
| `PROJECTS_ROOT` | No       | Path to project context directory (default: `./projects`)                          |
| `ROLES_ROOT`    | No       | Path to role persona directory (default: `./roles`)                                |
| `SECRET_KEY`    | **Yes**  | JWT signing secret — generate a strong random string for production                |
| `BCRYPT_ROUNDS` | No       | Bcrypt hashing rounds (default: 12)                                                |
| `OLLAMA_URL`    | No       | Ollama endpoint URL if using Ollama (default: `http://localhost:11434`)            |


> **Important**: The SECRET_KEY in `.env` is shared for demo purposes. For any non-local deployment, generate a new secret:
>
> ```python
> import secrets
> secrets.token_hex(32)
> ```



#### Frontend `.env.local`

Create or edit `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```



### 5.5 Configure Allure Ingestion Source

Edit `config2.json` at the repository root to point to your Allure results directory:

```json
{
    "ingestion_name": "allure_demo",
    "sources": [
        {
            "type": "allure",
            "path": "C:/path/to/your/allure-results"
        }
    ],
    "output": {
        "base_path": "../data"
    }
}
```


| Field              | Description                                                            |
| ------------------ | ---------------------------------------------------------------------- |
| `ingestion_name`   | A label for this ingestion configuration                               |
| `sources[].type`   | Source type: `allure`, `file`, `db`, `api`                             |
| `sources[].path`   | Absolute path to Allure results directory (for `allure` type)          |
| `output.base_path` | Relative path for ingestion output (relative to `universal_ingester/`) |




### 5.6 Run the Ingester

```bash
cd universal_ingester
python ingester.py
cd ..
```

This will:

- Read the Allure results from the path in `config2.json`
- Parse test cases, suites, steps, parameters, and attachments
- Store everything in LanceDB tables under `data/ingestion_YYYYMMDD_HHMMSS/lancedb/`
- Generate a `summary.json` file with KPIs (pass rate, duration, counts)

**Expected output** (console):

```
Running ingestion: allure_demo
Processing source: C:/path/to/allure-results
Ingestion complete: ingestion_20260428_113234
Summary: 150 tests, 120 passed, 20 failed, 10 skipped
```

**Output structure** (`data/ingestion_YYYYMMDD_HHMMSS/`):

```
data/
└── ingestion_20260428_113234/
    ├── lancedb/                  # LanceDB tables
    │   ├── flattened_tests       # All test results flattened
    │   ├── module_metrics        # Per-module pass/fail stats
    │   ├── project_metrics       # Project-level summary
    │   ├── test_cases            # Individual test case details
    │   ├── documents             # Embeddings for vector search
    │   ├── chat_history          # Per-session chat history
    │   └── chart_history         # Generated chart records
    └── summary.json              # Build summary with KPIs
```



### 5.7 Start the Backend Server

```bash
python -m services.main
```

The backend will start on `http://0.0.0.0:8000`. You should see:

```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Verify the backend is running:**

```bash
curl http://localhost:8000/health
# Response: {"status":"ok","data_path":"...\\data"}
```



### 5.8 Install & Start the Frontend

Open **a new terminal** (keep the backend running):

```bash
cd frontend
npm install
npm run dev
```

The frontend will start on `http://localhost:3000`. The `predev` script automatically generates `public/builds.json` from the `data/` directory.

---



## 6. Access Points


| Page               | URL                                                                      | Description                              |
| ------------------ | ------------------------------------------------------------------------ | ---------------------------------------- |
| Landing page       | [http://localhost:3000](http://localhost:3000)                           | Animated landing with feature showcase   |
| Login              | [http://localhost:3000/login](http://localhost:3000/login)               | JWT authentication form                  |
| Dashboard          | [http://localhost:3000/dashboard](http://localhost:3000/dashboard)       | Main analytics dashboard (auth required) |
| Build Trends       | [http://localhost:3000/build-trends](http://localhost:3000/build-trends) | Multi-build comparison charts            |
| Backend API        | [http://localhost:8000](http://localhost:8000)                           | FastAPI backend                          |
| API Docs (Swagger) | [http://localhost:8000/docs](http://localhost:8000/docs)                 | Interactive OpenAPI documentation        |
| API Docs (ReDoc)   | [http://localhost:8000/redoc](http://localhost:8000/redoc)               | Alternative API documentation            |


---



## 7. Login Credentials

Three hardcoded users (defined in `services/auth.py`):


| Username  | Password   | Role          | Description                                              |
| --------- | ---------- | ------------- | -------------------------------------------------------- |
| `aditya`  | `Pass@123` | `qa-engineer` | Can chat & generate charts as QA Engineer                |
| `jaydeep` | `Pass@123` | `qa-engineer` | Same as above                                            |
| `ali`     | `Pass@123` | `cto`         | Can chat & generate charts as CTO; can also switch roles |


**Login API**:

```bash
curl -X POST "http://localhost:8000/auth/login?username=aditya&password=Pass@123"
```

**Response**:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "role": "qa-engineer"
}
```

Store the `access_token` — it must be sent as `Authorization: Bearer <token>` on all protected endpoints. The token expires after **24 hours**.

---



## 8. Complete API Reference



### 8.1 Public Endpoints (no token required)



#### `GET /health`

Check backend health.

**Response:**

```json
{
  "status": "ok",
  "data_path": "C:\\...\\sentinel-qa-analytics-dashboard\\data"
}
```



#### `POST /auth/login`

Authenticate and receive a JWT token.

**Parameters:** `username` (query), `password` (query)

```bash
curl -X POST "http://localhost:8000/auth/login?username=aditya&password=Pass@123"
```

**Response:**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "role": "qa-engineer"
}
```



#### `POST /ingest/config2`

Trigger an ingestion run. Updates `config2.json` with the provided `source_path`, then runs the ingester.

**Request body:**

```json
{
  "source_path": "C:/path/to/allure-results"
}
```

```bash
curl -X POST "http://localhost:8000/ingest/config2" \
  -H "Content-Type: application/json" \
  -d '{"source_path":"C:/path/to/allure-results"}'
```

**Response:**

```json
{
  "success": true,
  "build_id": "ingestion_20260428_113234",
  "source_path": "C:/path/to/allure-results"
}
```



### 8.2 Protected Endpoints (Bearer token required)

All protected endpoints require the header:

```
Authorization: Bearer <your_jwt_token>
```



#### `GET /ingestions`

List all available ingestion builds (reverse chronological order).

```bash
curl -X GET "http://localhost:8000/ingestions" \
  -H "Authorization: Bearer <token>"
```

**Response:**

```json
{
  "ingestions": [
    {
      "id": "ingestion_20260428_113234",
      "summary": "{...metrics JSON...}",
      "created": 1714329154.0,
      "build_label": "Build 1"
    }
  ]
}
```



#### `GET /data/status`

Get KPI summary for a specific ingestion. Requires `x-ingestion-id` header.

```bash
curl -X GET "http://localhost:8000/data/status" \
  -H "Authorization: Bearer <token>" \
  -H "x-ingestion-id: ingestion_20260428_113234"
```

**Response:**

```json
{
  "has_data": true,
  "total_rows": 150,
  "status_summary": {
    "passed": 120,
    "failed": 20
  }
}
```



#### `POST /chat`

Send a natural language message to the AI chatbot. Requires context headers.

```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -H "x-ingestion-id: ingestion_20260428_113234" \
  -H "x-role: qa-engineer" \
  -H "x-project: FSA" \
  -d '{"message": "How many tests failed in the mobile suite?"}'
```

**Response:**

```json
{
  "response": "In the mobile suite, 12 tests failed out of 45 total...",
  "session_id": "a1b2c3d4-..."
}
```


| Header           | Required | Description                                                        |
| ---------------- | -------- | ------------------------------------------------------------------ |
| `x-ingestion-id` | **Yes**  | The build/ingestion ID to query                                    |
| `x-role`         | No       | AI persona: `qa-engineer`, `cto`, or custom                        |
| `x-project`      | No       | Project context: `FSA`, `clippd`, or custom                        |
| `x-session-id`   | No       | Session ID for conversation continuity (auto-generated if omitted) |




#### `POST /chart`

Generate a Plotly chart from a natural language prompt.

```bash
curl -X POST "http://localhost:8000/chart" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -H "x-ingestion-id: ingestion_20260428_113234" \
  -H "x-role: qa-engineer" \
  -H "x-project: FSA" \
  -d '{"message": "Show pass/fail distribution as a pie chart"}'
```

**Response:**

```json
{
  "chart": {
    "data": [{"type": "pie", "labels": ["Passed", "Failed"], "values": [120, 20]}],
    "layout": {"title": "Test Results Distribution"}
  },
  "session_id": "a1b2c3d4-..."
}
```



#### `GET /chat/history/{session_id}`

Get chat history for a session.

```bash
curl -X GET "http://localhost:8000/chat/history/a1b2c3d4-..." \
  -H "Authorization: Bearer <token>" \
  -H "x-ingestion-id: ingestion_20260428_113234"
```



#### `GET /chart/history/{session_id}`

Get chart generation history for a session.

```bash
curl -X GET "http://localhost:8000/chart/history/a1b2c3d4-..." \
  -H "Authorization: Bearer <token>" \
  -H "x-ingestion-id: ingestion_20260428_113234"
```



#### `DELETE /chart/{chart_id}`

Delete a specific generated chart by ID.

```bash
curl -X DELETE "http://localhost:8000/chart/some-chart-uuid" \
  -H "Authorization: Bearer <token>" \
  -H "x-ingestion-id: ingestion_20260428_113234"
```



#### `GET /projects`

List available project contexts.

```bash
curl -X GET "http://localhost:8000/projects" \
  -H "Authorization: Bearer <token>"
```

**Response:**

```json
{
  "projects": ["FSA", "clippd"]
}
```



#### `GET /roles`

List available AI personas.

```bash
curl -X GET "http://localhost:8000/roles" \
  -H "Authorization: Bearer <token>"
```

**Response:**

```json
{
  "roles": ["cto", "qa-engineer"]
}
```



#### `GET /debug/data`

Debug endpoint showing DuckDB tables and sample data.

```bash
curl -X GET "http://localhost:8000/debug/data" \
  -H "Authorization: Bearer <token>" \
  -H "x-ingestion-id: ingestion_20260428_113234"
```



#### `GET /test/llm`

Test LLM connectivity (returns a one-word response from the configured provider).

```bash
curl -X GET "http://localhost:8000/test/llm" \
  -H "Authorization: Bearer <token>"
```



#### `GET /test/sql`

Test SQL query execution against DuckDB for a specific ingestion.

```bash
curl -X GET "http://localhost:8000/test/sql" \
  -H "Authorization: Bearer <token>" \
  -H "x-ingestion-id: ingestion_20260428_113234"
```



### 8.3 API Endpoints Summary


| Method   | Endpoint                      | Auth | Description         |
| -------- | ----------------------------- | ---- | ------------------- |
| `GET`    | `/health`                     | No   | Health check        |
| `POST`   | `/auth/login`                 | No   | Login (returns JWT) |
| `POST`   | `/ingest/config2`             | No   | Trigger ingestion   |
| `GET`    | `/ingestions`                 | Yes  | List builds         |
| `GET`    | `/data/status`                | Yes  | KPI summary         |
| `POST`   | `/chat`                       | Yes  | AI chat             |
| `POST`   | `/chart`                      | Yes  | Generate chart      |
| `GET`    | `/chat/history/{session_id}`  | Yes  | Chat history        |
| `GET`    | `/chart/history/{session_id}` | Yes  | Chart history       |
| `DELETE` | `/chart/{chart_id}`           | Yes  | Delete chart        |
| `GET`    | `/projects`                   | Yes  | List projects       |
| `GET`    | `/roles`                      | Yes  | List roles          |
| `GET`    | `/debug/data`                 | Yes  | Debug data          |
| `GET`    | `/test/llm`                   | Yes  | Test LLM            |
| `GET`    | `/test/sql`                   | Yes  | Test SQL            |


---



## 9. Data Ingestion Guide



### 9.1 Allure Ingestion (Primary Method)

Allure is the primary and most fully-featured ingestion source. It parses Allure JSON result files into structured LanceDB tables.

**Step 1**: Edit `config2.json` with the absolute path to your `allure-results` directory:

```json
{
    "ingestion_name": "allure_demo",
    "sources": [
        {
            "type": "allure",
            "path": "C:/absolute/path/to/allure-results"
        }
    ],
    "output": { "base_path": "../data" }
}
```

**Step 2**: Run the ingester:

```bash
cd universal_ingester
python ingester.py
cd ..
```

**Step 3**: Or use the dashboard API:

```bash
curl -X POST "http://localhost:8000/ingest/config2" \
  -H "Content-Type: application/json" \
  -d '{"source_path":"C:/absolute/path/to/allure-results"}'
```

**Step 4**: From the dashboard, use the "Add Build" button to set the Allure path (updates `config2.json` via `/api/config2-path`) and trigger ingestion.

### 9.2 File Ingestion (CSV, Excel, PDF, Images)

Configure a file source in an ingestion config JSON:

```json
{
    "ingestion_name": "file_import",
    "sources": [
        {
            "type": "file",
            "path": "C:/path/to/files",
            "format": "csv"
        }
    ],
    "output": { "base_path": "../data" }
}
```

Supported formats: `csv`, `xlsx`, `pdf`, `png`, `jpg`.

### 9.3 Database Ingestion (MySQL, PostgreSQL, etc.)

Configure a database source:

```json
{
    "ingestion_name": "db_import",
    "sources": [
        {
            "type": "db",
            "connection_string": "mysql+pymysql://user:pass@host:3306/database",
            "query": "SELECT * FROM test_results"
        }
    ],
    "output": { "base_path": "../data" }
}
```

Uses SQLAlchemy to connect to any supported database.

### 9.4 API Ingestion (REST APIs)

Configure an API source:

```json
{
    "ingestion_name": "api_import",
    "sources": [
        {
            "type": "api",
            "url": "https://api.example.com/test-results",
            "headers": { "Authorization": "Bearer token" }
        }
    ],
    "output": { "base_path": "../data" }
}
```



### 9.5 Ingestion Output

Each ingestion run creates a timestamped folder:

```
data/
└── ingestion_20260428_113234/
    ├── lancedb/
    │   ├── flattened_tests       # Flat table: all test cases with status, duration, suite
    │   ├── module_metrics        # Per-module aggregation: pass count, fail count, rate
    │   ├── project_metrics       # Project-level summary metrics
    │   ├── test_cases            # Detailed test case info (steps, parameters)
    │   ├── documents             # Text embeddings for RAG (vector search)
    │   └── chat_history          # Conversation history per session
    │   └── chart_history         # Generated chart records per session
    └── summary.json              # Build summary with KPIs
```

`summary.json` structure:

```json
{
  "build_id": "ingestion_20260428_113234",
  "metrics": {
    "total_tests": 150,
    "passed": 120,
    "failed": 20,
    "skipped": 10,
    "pass_rate": 80.0,
    "total_duration_ms": 450000,
    "avg_duration_ms": 3000
  },
  "modules": {
    "FSA": { "passed": 50, "failed": 5, "total": 55 },
    "HSA": { "passed": 40, "failed": 10, "total": 50 },
    "WDH": { "passed": 30, "failed": 5, "total": 45 }
  }
}
```

---



## 10. AI Features Guide



### 10.1 AI Chat Interface

The chat interface (`FloatingChat` component) allows you to ask questions about test data in natural language.

**How it works:**

1. Your message is sent with context headers (`x-ingestion-id`, `x-role`, `x-project`)
2. The backend loads the relevant LanceDB data into DuckDB
3. The LLM receives:
  - The DuckDB schema (table names, columns, types)
  - The selected role persona (from `roles/*.md`)
  - The selected project context (from `projects/*/context.md`)
  - Conversation history from the current session
4. The LLM decides one of three actions:
  - **SQL** — Generate and execute a SQL query against DuckDB, return results as text
  - **Vector** — Perform a vector similarity search against project embeddings
  - **Answer** — Generate a direct answer from context

**Example queries:**

- "How many tests passed vs failed?"
- "What's the pass rate for the FSA module?"
- "Show me the slowest 5 tests"
- "How does this build compare to the last one?"
- "What are the top failure reasons?"



### 10.2 AI Chart Generation

The chart interface (`FloatingChart` component) generates Plotly charts from plain English prompts.

**Supported chart types** (auto-detected from prompt):

- Bar charts (vertical/horizontal, grouped, stacked)
- Pie / donut charts
- Line charts (single, multi-series)
- Scatter plots
- Area charts
- Heatmaps
- Histograms
- Box plots
- Treemaps
- Sunburst charts
- Stacked bar charts
- Waterfall charts

**Example prompts:**

- "Show pass/fail distribution as a pie chart"
- "Bar chart of tests per module"
- "Line chart showing test duration trend"
- "Breakdown of mobile vs desktop test results"
- "Show passed vs failed by suite as a grouped bar chart"

**Chart history** is stored per session and displayed in a drag-and-drop gallery on the dashboard. You can reorder, view, or delete charts.

### 10.3 Role-Based Personas (x-role)

The AI adapts its responses based on the selected role. Roles are defined as Markdown files in `roles/`:


| Role          | File                   | Perspective                                                   |
| ------------- | ---------------------- | ------------------------------------------------------------- |
| `qa-engineer` | `roles/qa-engineer.md` | Technical: specific failures, root causes, regression details |
| `cto`         | `roles/cto.md`         | Executive: business risk, ROI, release readiness, trends      |


**Frontend behavior:**

- Users with `qa-engineer` role can only use the `qa-engineer` persona
- Users with `cto` role can toggle between all personas via a dropdown switch



### 10.4 Project Context (x-project)

Project-specific context files in `projects/` are loaded as embeddings for RAG:


| Project  | Path                         | Description                                        |
| -------- | ---------------------------- | -------------------------------------------------- |
| `FSA`    | `projects/FSA/context.md`    | FSA/HSA/WellDeserved Health platform documentation |
| `clippd` | `projects/clippd/context.md` | Golf analytics platform documentation              |


When a project is selected, the relevant context is embedded and used for vector similarity search alongside the SQL query results.

---



## 11. Build Trend Analysis

The **Build Trends** page (`/build-trends`) compares metrics across multiple ingestion runs.

**How it works:**

1. The frontend calls `GET /api/builds` (Next.js API route)
2. The route reads all `data/ingestion_*/summary.json` files
3. Builds are sorted chronologically and labeled "Build 1", "Build 2", etc.
4. Four ApexCharts are rendered:


| Chart                  | Type        | Description                                |
| ---------------------- | ----------- | ------------------------------------------ |
| Pass Rate Trend        | Line        | Pass rate percentage across builds         |
| Test Results Breakdown | Stacked Bar | Passed / Failed / Skipped counts per build |
| Total Duration         | Line        | Total execution time per build (ms)        |
| Average Test Duration  | Bar         | Average test duration per build (ms)       |


**Display range**: Choose between Last 5, 10, 20, or All builds.

---



## 12. Authentication & Authorization



### 12.1 JWT Authentication Flow

```
User → Login Form → POST /auth/login → Server validates credentials
  ↓
Server generates JWT (HS256, 24h expiry) with payload {sub: username, role: role}
  ↓
Frontend stores token in localStorage as "token"
  ↓
Every API call includes header: Authorization: Bearer <token>
  ↓
Server validates JWT on protected endpoints via Depends(get_current_user)
```



### 12.2 Frontend Auth Guard

The dashboard layout (`app/dashboard/layout.tsx`) checks for `token` in localStorage on every navigation to `/dashboard`. If missing, it redirects to `/login`.

### 12.3 Role-Based Permissions

- **qa-engineer**: Can query data and generate charts as QA Engineer only
- **cto**: Can query data, generate charts, and switch between all available roles

Enforced in `frontend/lib/RBContext.tsx` — `canSwitchRole` is `true` only for CTO users.

### 12.4 Generating New User Hashes

To add or update users, generate bcrypt hashes:

```python
import bcrypt
hash = bcrypt.hashpw(b"YourPassword", bcrypt.gensalt(rounds=12)).decode()
print(hash)
```

Then add to `USERS_HASHED` in `services/auth.py`:

```python
USERS_HASHED = {
    "newuser": {
        "username": "newuser",
        "password_hash": "$2b$12$...your_hash_here...",
        "role": "qa-engineer"
    },
    # ... existing users
}
```

---



## 13. Complete Project Structure

```
sentinel-qa-analytics-dashboard/
│
├── .env                         # Root environment variables (LLM keys, auth secret)
├── .gitignore                   # Git ignore rules
├── README.md                    # Quick-start documentation
├── USERGUIDE.md                 # This document
├── package.json                 # Root Node deps (shared chart libs)
├── requirements.txt             # Python backend dependencies
├── config.json                  # Legacy TiDB ingestion config
├── config2.json                 # Active Allure ingestion config (edit for your path)
├── chat_history.json            # Dumped chat history (runtime)
├── generated_charts.json        # Dumped chart cache (runtime)
│
├── services/                    # FastAPI backend
│   ├── __init__.py
│   ├── main.py                  # FastAPI app, all route definitions
│   ├── auth.py                  # JWT creation/validation, user store
│   ├── config.py                # Path resolution, env loading
│   ├── state.py                 # Global state (DB connections, managers)
│   ├── data_loader.py           # LanceDB → DuckDB data loading
│   ├── handlers.py              # Chat & chart business logic
│   ├── llm_client.py            # Multi-provider LLM abstraction
│   ├── memory.py                # Chat/chart history in LanceDB
│   ├── prompts.py               # All LLM prompts, chart templates (765 lines)
│   ├── role_manager.py          # Persona loading from roles/
│   └── project_manager.py       # Project context & embeddings
│
├── universal_ingester/          # Data ingestion pipeline
│   ├── ingester.py              # UniversalIngester orchestrator class
│   ├── utils.py                 # EmbeddingGenerator (sentence-transformers)
│   ├── test.py                  # Quick test script
│   ├── test_allure_ingestion.py # Allure-specific test
│   ├── test_tidb_ingestion.py   # TiDB-specific test
│   └── connectors/
│       ├── __init__.py
│       ├── base.py              # Abstract base connector
│       ├── allure_connector.py  # Allure JSON results parser
│       ├── file_connector.py    # CSV/Excel/PDF/images parser
│       ├── db_connector.py      # SQLAlchemy database connector
│       └── api_connector.py     # REST API connector
│
├── roles/                       # AI persona definitions
│   ├── cto.md                   # Executive/CTO persona
│   └── qa-engineer.md           # QA Engineer persona
│
├── projects/                    # Project-specific context
│   ├── FSA/
│   │   ├── context.md           # FSA/HSA/WellDeserved Health docs
│   │   └── embeddings.lance/    # Vector embeddings for RAG
│   └── clippd/
│       ├── context.md           # Golf analytics platform docs
│       └── embeddings.lance/    # Vector embeddings for RAG
│
├── data/                        # Ingestion output directories
│   └── ingestion_YYYYMMDD_HHMMSS/
│       ├── lancedb/             # LanceDB tables
│       └── summary.json         # Build KPIs
│
├── scripts/
│   └── generate-builds.js       # Legacy build summary generator
│
├── public/
│   └── builds.json              # Static build summaries (generated by predev script)
│
└── frontend/                    # Next.js 16 frontend
    ├── .env.local               # NEXT_PUBLIC_API_URL
    ├── .gitignore
    ├── package.json              # Frontend dependencies
    ├── next.config.ts            # Next.js config (allowedDevOrigins)
    ├── tsconfig.json             # TypeScript config
    ├── postcss.config.mjs        # PostCSS + Tailwind config
    ├── eslint.config.mjs         # ESLint config
    ├── next-env.d.ts             # Next.js type declarations
    ├── types/
    │   └── analytics.ts          # KPI, ModuleStats, Trend types
    ├── lib/
    │   ├── api.ts                # Backend API client with Bearer auth
    │   ├── IngestionContext.tsx   # Build/ingestion selection state
    │   ├── RBContext.tsx          # Role & Project selection state
    │   ├── session.ts            # Session ID management (UUID)
    │   ├── roleSuggestions.ts    # Role-specific chat/chart suggestions
    │   └── theme.ts              # Dark/light theme persistence
    ├── components/
    │   ├── AIChatbot.tsx         # Full chat interface
    │   ├── AIChatInput.tsx       # Chart prompt input
    │   ├── AIGeneratedChart.tsx  # Dynamic Plotly chart renderer
    │   ├── BrandLogo.tsx         # Logo component
    │   ├── BuildTrendCharts.tsx  # ApexCharts trend visualizations
    │   ├── ChartGallery.tsx      # Drag-and-drop chart gallery
    │   ├── FloatingChart.tsx     # Floating chart generator button
    │   ├── FloatingChat.tsx      # Floating chat modal
    │   ├── IngestionSelector.tsx # Build/ingestion dropdown
    │   ├── ProjectSelector.tsx   # Project dropdown
    │   ├── RoleSelector.tsx      # Role dropdown (CTO-only switch)
    │   ├── ThemeInitializer.tsx  # Theme on page load
    │   └── ThemeToggle.tsx       # Dark/light toggle button
    ├── app/
    │   ├── globals.css           # Global styles, CSS variables, animations
    │   ├── layout.tsx            # Root layout (fonts, theme provider)
    │   ├── page.tsx              # Landing page
    │   ├── login/
    │   │   └── page.tsx          # Login page
    │   ├── dashboard/
    │   │   ├── layout.tsx        # Auth guard + context providers
    │   │   └── page.tsx          # Main dashboard
    │   ├── build-trends/
    │   │   └── page.tsx          # Build trend analysis page
    │   └── api/
    │       ├── builds/
    │       │   └── route.ts      # GET /api/builds - reads data/summary.json
    │       └── config2-path/
    │           └── route.ts      # GET/PUT /api/config2-path
    ├── public/
    │   └── builds.json           # Static builds data (generated)
    └── scripts/
        └── generate-builds-json.js  # Prebuild/predev script
```

---



## 14. Configuration Reference



### 14.1 Environment Variables (`.env`)


| Variable        | Default                   | Description                                             |
| --------------- | ------------------------- | ------------------------------------------------------- |
| `LLM_PROVIDER`  | `gemini`                  | LLM provider: `gemini`, `openai`, `anthropic`, `ollama` |
| `LLM_API_KEY`   | (empty)                   | API key for the LLM provider                            |
| `LLM_MODEL`     | `models/gemini-2.5-flash` | Model name/ID                                           |
| `OLLAMA_URL`    | `http://localhost:11434`  | Ollama endpoint URL                                     |
| `PROJECTS_ROOT` | `./projects`              | Directory for project context files                     |
| `ROLES_ROOT`    | `./roles`                 | Directory for role persona files                        |
| `SECRET_KEY`    | (required)                | JWT signing secret                                      |
| `BCRYPT_ROUNDS` | `12`                      | Bcrypt hashing complexity                               |




### 14.2 Frontend Environment (`frontend/.env.local`)


| Variable              | Default                 | Description          |
| --------------------- | ----------------------- | -------------------- |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend API base URL |




### 14.3 Ingestion Config (`config2.json`)

```json
{
    "ingestion_name": "allure_demo",
    "sources": [
        {
            "type": "allure",
            "path": "C:/path/to/allure-results"
        }
    ],
    "output": {
        "base_path": "../data"
    }
}
```



### 14.4 Next.js Config (`frontend/next.config.ts`)

Used to allow remote dev server access:

```typescript
import type { NextConfig } from "next";
const nextConfig: NextConfig = {
  allowedDevOrigins: ['13.63.14.222'],  // Add remote IPs for network access
};
export default nextConfig;
```

---



## 15. Troubleshooting



### 15.1 Backend won't start

**Issue**: `ModuleNotFoundError: No module named 'jose'`
**Solution**: Install `python-jose[cryptography]`:

```bash
pip install python-jose[cryptography] bcrypt
```

**Issue**: `SECRET_KEY environment variable not set`
**Solution**: Ensure `.env` file exists in the repository root with a `SECRET_KEY` value.

**Issue**: Port 8000 already in use
**Solution**: Find and kill the process, or change the port in `services/main.py` line 310:

```bash
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```



### 15.2 Ingestion fails

**Issue**: `FileNotFoundError` for allure-results
**Solution**: Verify the path in `config2.json` is absolute and correct. Use forward slashes or escaped backslashes:

```json
"path": "C:/Users/Me/project/allure-results"
```

**Issue**: `MemoryError` during ingestion
**Solution**: Large Allure reports may require more memory. Close other applications or increase Python memory limit.

**Issue**: `torch` or `sentence-transformers` installation fails
**Solution**: Install without version pins:

```bash
pip install sentence-transformers
```



### 15.3 Frontend issues

**Issue**: Blank page or CORS errors in console
**Solution**: Ensure the backend is running on port 8000 and `NEXT_PUBLIC_API_URL` in `frontend/.env.local` is correct.

**Issue**: `401 Unauthorized` on dashboard
**Solution**: Log out and log back in. The JWT token expires after 24 hours.

**Issue**: `npm run dev` fails with build errors
**Solution**: Delete `node_modules` and reinstall:

```bash
cd frontend
rm -rf node_modules .next
npm install
npm run dev
```

**Issue**: Remote access to dev server
**Solution**: Add your IP to `frontend/next.config.ts`:

```typescript
allowedDevOrigins: ['your.ip.address'],
```



### 15.4 AI / LLM issues

**Issue**: `401` or authentication error from LLM provider
**Solution**: Verify `LLM_API_KEY` in `.env` is correct and has not expired. Test with:

```bash
curl -X GET "http://localhost:8000/test/llm" -H "Authorization: Bearer <token>"
```

**Issue**: LLM returns irrelevant or incorrect SQL
**Solution**: The `prompts.py` file (765 lines) contains all LLM prompts and SQL templates. You may need to adjust prompts for your specific schema or data patterns.

**Issue**: "Unknown chart type" error
**Solution**: The chart type detector in `prompts.py` (`detect_chart_type` function) recognizes specific keywords. Try rephrasing your prompt using supported chart type names (bar, pie, line, scatter, area, heatmap, histogram, box, treemap, sunburst, stacked bar, waterfall).

### 15.5 Data / Query issues

**Issue**: No data shown on dashboard
**Solution**: Verify an ingestion has been run and the `data/` directory contains a timestamped folder with a `lancedb/` subdirectory.

**Issue**: Build Trends page shows no builds
**Solution**: The page reads `data/*/summary.json` files. Ensure each ingestion folder has a valid `summary.json`.

### 15.6 Quick Diagnostic Commands

```bash
# Check backend health
curl http://localhost:8000/health

# List available ingestions
curl http://localhost:8000/ingestions -H "Authorization: Bearer <token>"

# Test LLM connectivity
curl http://localhost:8000/test/llm -H "Authorization: Bearer <token>"

# Check frontend API builds endpoint
curl http://localhost:3000/api/builds
```

---



## 16. Quick Setup Checklist

- [ ] Clone repository
- [ ] Create Python virtual environment (`python -m venv venv && venv\Scripts\activate`)
- [ ] Install backend deps (`pip install -r requirements.txt && pip install python-jose[cryptography] bcrypt`)
- [ ] Configure `.env` with LLM provider, API key, and SECRET_KEY
- [ ] Create `frontend/.env.local` with `NEXT_PUBLIC_API_URL=http://localhost:8000`
- [ ] Edit `config2.json` with your Allure results path
- [ ] Run ingester (`cd universal_ingester && python ingester.py && cd ..`)
- [ ] Start backend (`python -m services.main`)
- [ ] Install frontend deps & start (`cd frontend && npm install && npm run dev`)
- [ ] Open [http://localhost:3000](http://localhost:3000)
- [ ] Log in with `aditya` / `Pass@123`
- [ ] Select a build from the ingestion selector
- [ ] Start asking questions in the AI chat!

---

*Generated for Sentinel QA Intelligence Dashboard v0.1.0*