# Sentinel QA Analytics Dashboard - Simple Architecture Report

## What This System Does

Sentinel QA Analytics Dashboard is a web application that helps QA teams analyze test results. Users can ask questions about test data in plain English, and the system uses AI to generate answers and charts. It ingests test data from multiple sources (like Allure test reports), stores it in databases, and provides a web interface for exploration.

---

## System Overview

The system has three main parts:

1. **Frontend** - A Next.js web app that runs in the browser
2. **Backend** - A Python FastAPI service that processes requests
3. **Data Pipeline** - An ingestion system that imports test data from various sources

Users log in, select test data, ask questions, and get AI-powered insights.

---

## How Data Flows Through the System

### Step 1: Data Ingestion (Getting test data in)

- User uploads Allure test results (JSON files) or connects to a database
- The "Universal Ingester" reads this data
- Data is processed, cleaned, and stored in two places:
  - **LanceDB** - A vector database that stores documents and embeddings
  - **DuckDB** - An in-memory query engine that stores tables for fast SQL queries
- The ingested data is saved to disk under `data/ingestion_TIMESTAMP/`

### Step 2: User Login (Authentication)

- User enters username and password on the login page
- Backend validates the password using bcrypt hashing
- If valid, backend creates a JWT token (a signed piece of text that acts like a temporary credential)
- Frontend stores this token in browser storage
- All future requests include this token to prove the user is logged in

### Step 3: User Asks a Question (Chat Flow)

- User types a question like "How many tests failed?"
- Frontend sends the message to the backend `/chat` endpoint with the token
- Backend receives the request and:
  1. Loads the ingested test data into memory (if not already loaded)
  2. Looks up previous conversation history
  3. Extracts keywords from the question
  4. Sends the question to the LLM (AI model like Gemini or Claude)
  5. LLM decides: should I run SQL? Search documents? Or answer directly?
  6. Backend executes that action
  7. LLM generates a human-readable response
  8. Response is saved to chat history
  9. Response is sent back to frontend and displayed to user

### Step 4: User Asks for a Chart (Chart Generation Flow)

- User types "Show me pass rate by module"
- Frontend sends to `/chart` endpoint
- Backend:
  1. Determines chart type based on keywords (bar, line, pie, etc.) - NOT from AI (prevents errors)
  2. Asks LLM to generate SQL query to get the data
  3. Runs the SQL query against DuckDB
  4. Gets back a table of numbers
  5. Asks LLM to fill in a pre-made Plotly chart template
  6. Sends the chart back to frontend
  7. Frontend displays the interactive chart

---

## Technology Stack

**Frontend (User Interface)**
- Next.js (React framework)
- TypeScript (typed JavaScript)
- Tailwind CSS (styling)
- Recharts and ApexCharts (for charts)

**Backend (Processing & Logic)**
- FastAPI (Python web framework)
- SQLAlchemy (database ORM)
- Python (programming language)

**Databases**
- SQLite - stores user login info
- LanceDB - stores vectors and chat history
- DuckDB - fast query engine for test data

**AI/LLM**
- LiteLLM (abstraction layer)
- Google Gemini (default AI model)
- Also supports: OpenAI, Anthropic Claude, Ollama

**Data Processing**
- Pandas (data manipulation)
- NumPy (numerical computing)
- sentence-transformers (creates embeddings)
- Plotly (interactive charts)

---

## File Structure Explained

```
sentinel-qa-analytics-dashboard/
├── services/                    # Backend code
│   ├── main.py                 # API endpoints and routing
│   ├── handlers.py             # Logic for chat and charts
│   ├── auth.py                 # Login and JWT tokens
│   ├── data_loader.py          # Loads data into DuckDB
│   ├── llm_client.py           # Talks to AI models
│   ├── memory.py               # Saves chat history
│   └── ... other backend files
│
├── frontend/                   # User interface code
│   ├── app/
│   │   ├── page.tsx            # Landing page
│   │   ├── login/page.tsx      # Login page
│   │   ├── dashboard/page.tsx  # Main dashboard
│   │   └── build-trends/page.tsx # Build comparison page
│   └── components/             # React UI components
│       ├── AIChatbot.tsx       # Chat interface
│       ├── ChartGallery.tsx    # Chart display
│       └── ... other components
│
├── universal_ingester/         # Data import system
│   ├── ingester.py            # Main ingestion logic
│   └── connectors/            # Data source handlers
│       ├── allure_connector.py # Allure test results
│       ├── file_connector.py   # CSV, JSON files
│       ├── db_connector.py     # MySQL, databases
│       └── api_connector.py    # REST APIs
│
├── data/                       # Generated data storage
│   └── ingestion_TIMESTAMP/   # One folder per ingestion
│       ├── lancedb/           # Vector database
│       ├── summary.json       # Metadata
│       └── summary.md         # Human-readable summary
│
├── roles/                      # AI personality templates
│   ├── cto.md                 # Executive view
│   └── qa-engineer.md         # QA team view
│
└── config.json                # Data source configuration
```

---

## How Authentication Works

1. User enters username and password
2. Backend looks up the user in SQLite database
3. Password is checked using bcrypt (one-way hashing)
4. If correct, JWT token is created with:
   - Username
   - Role (cto or qa-engineer)
   - Workspace ID
   - Expiration time (24 hours)
5. Token is signed with a secret key so it can't be forged
6. Token is sent to frontend and stored in browser
7. For future requests, token is included in headers
8. Backend verifies token is valid and not expired
9. Request proceeds if everything checks out

### Roles

- **CTO** - Admin access, can see all users' data
- **QA Engineer** - Standard access, can only see their own data

---

## Database Details

### SQLite (User Authentication)
- Simple file-based database (`users.db`)
- Stores: username, password hash, role
- Used only for login verification
- No test data stored here

### LanceDB (Vector Storage)
- Stores embeddings (numeric representations of text)
- Stores documents and text
- Stores chat history (questions and answers)
- Stores knowledge graph (related concepts)
- One database per ingestion in `data/ingestion_TIMESTAMP/lancedb/`

### DuckDB (Query Engine)
- Runs in memory during a session
- Stores test execution tables:
  - `flattened_tests` - one row per test result
  - `module_metrics` - aggregates by module
  - `project_metrics` - aggregates by project
- Fast SQL queries (no disk I/O during query)
- Pre-computed aggregate tables for quick analysis

---

## Data Model for Test Results

When Allure results are ingested, they are normalized into a standard format:

**Main Table: flattened_tests**
- test_name - the test identifier
- status - passed, failed, skipped, etc.
- duration - how long it took (in seconds)
- error - error message if failed
- project_name - FSA, HSA, WDH, etc.
- module_name - which feature area
- platform_type - desktop or mobile
- browser - Chrome, Safari, iPhone, etc.

**Aggregate Tables:**
- module_metrics - pass rate by module
- project_metrics - pass rate by project
- test_cases - metadata about each test

---

## API Endpoints (What the Backend Provides)

**Public (No Login Required)**
- GET /health - Check if backend is running
- POST /auth/login - Login with username/password

**Protected (Login Required)**

Chat:
- POST /chat - Send a question, get AI response
- GET /chat/history/{id} - Get past conversations

Charts:
- POST /chart - Generate a chart from description
- GET /chart/history/{id} - Get past charts
- DELETE /chart/{id} - Delete a chart

Data:
- GET /ingestions - List all imported datasets
- GET /data/status - How much data is loaded
- GET /data/quality - Data quality metrics
- GET /dashboard/overview - Summary for dashboard

Admin:
- GET /usage/tokens - Track AI token spending

---

## Key Features

**Multi-Source Data Ingestion**
- Allure test results (JSON)
- CSV, JSON, Excel files
- MySQL, TiDB databases
- REST APIs

**Natural Language Analytics**
- Ask questions in English: "How many tests are failing?"
- AI understands the question
- AI generates SQL to fetch the data
- Returns answer in plain English

**AI-Generated Charts**
- Describe what you want: "Bar chart of pass rate by module"
- System generates interactive charts
- Saves charts for later reference

**Conversation Memory**
- System remembers previous questions
- Learns from repeated patterns
- Suggests follow-up questions based on keywords

**Role-Based Views**
- CTO sees executive summary
- QA Engineer sees technical details
- Different AI personas for different roles

**Dark/Light Mode**
- Automatic based on OS preference
- Manual toggle available

---

## Security Overview

**What's Implemented:**
- JWT tokens for authentication
- Bcrypt password hashing
- SQL injection prevention (checks for dangerous keywords)
- CORS protection (controls which websites can connect)
- Role-based access control (CTOs vs QA Engineers)

**Important Issues to Know About:**

1. **Credentials in Code** - Database passwords are in config.json file. Should be in environment variables only, not in code.

2. **API Keys Exposed** - AI API keys are in .env file that was committed to git. Should be kept secret in production.

3. **No Rate Limiting** - Anyone can spam the API. Should add limits to prevent abuse.

4. **SQL Validation Incomplete** - Uses pattern matching instead of proper SQL parser. Could be bypassed.

5. **Tokens in Browser** - JWT stored in localStorage. Vulnerable to cross-site scripting (XSS). Should use secure cookies instead.

6. **No HTTPS** - Development mode uses HTTP. Production must use HTTPS.

---

## Performance Characteristics

**Typical Response Times:**
- First question after loading data: 5-10 seconds
- Subsequent questions: 3-5 seconds
- Chart generation: 3-8 seconds
- Dashboard load: 2-4 seconds

**Why Some Things Are Slow:**
- First request loads data into memory (one-time, then cached)
- LLM API calls are slow (1-10 seconds per call)
- Large test datasets take time to process (100K+ tests = several minutes to ingest)

**Optimizations in Place:**
- Frontend caches data in memory and session storage
- DuckDB runs in memory (no disk I/O during queries)
- LanceDB stores vectors for fast semantic search
- Only necessary data is computed on demand

---

## Common Workflows

### Workflow 1: Analyze Test Results

1. User logs in
2. User uploads Allure results folder
3. System ingests and processes the data (1-5 minutes)
4. User goes to dashboard
5. User asks "What's the pass rate?"
6. System returns answer with stats
7. User asks "Show me failures by module"
8. System generates bar chart
9. User reviews chart and patterns

### Workflow 2: Compare Builds Over Time

1. User uploads multiple test runs over time
2. Goes to "Build Trends" page
3. System shows trends: pass rate over time, slowest tests, etc.
4. User can spot regressions (tests that broke)
5. User asks AI: "Why did pass rate drop?"
6. AI analyzes and suggests root causes

### Workflow 3: Team Collaboration

1. QA Engineer runs tests, uploads results
2. CTO logs in and views summary
3. CTO asks AI for executive summary
4. System generates report: pass rate, risk areas, recommendations
5. CTO shares charts with team
6. Team discusses and plans fixes

---

## How AI (LLM) Is Used

The system uses an AI model (Gemini, Claude, or ChatGPT) for:

1. **Understanding Questions** - Converts "How many tests failed?" to structured query
2. **Generating SQL** - Creates database queries from natural language
3. **Interpreting Results** - Turns data into human-readable insights
4. **Generating Suggestions** - Recommends questions to ask
5. **Creating Responses** - Writes explanations for the user

The AI does NOT:
- Decide what chart type to use (that's determined by keywords in the description)
- Modify data (all operations are read-only)
- Authenticate users (that's JWT)
- Store credentials (API keys are separate)

---

## Deployment and Running

**Development:**
```bash
# Backend
python -m services.main        # Runs on http://localhost:8000

# Frontend (new terminal)
cd frontend
npm run dev                    # Runs on http://localhost:3000

# Ingestion (to load data)
cd universal_ingester
python ingester.py
```

**Production Considerations:**
- Use HTTPS (not HTTP)
- Store secrets in secure vault (not .env files)
- Run behind reverse proxy (nginx, etc.)
- Use PostgreSQL instead of SQLite for scaling
- Set up monitoring and logging
- Add rate limiting and authentication API keys
- Regular backups of LanceDB and user database

---

## What Needs Improvement

**Immediate Fixes Needed:**
1. Remove hardcoded credentials from config files
2. Add rate limiting to prevent abuse
3. Use HTTPS for all communication
4. Improve SQL validation

**Should Do Soon:**
1. Better error handling and logging
2. Comprehensive testing suite
3. TypeScript strict mode in frontend
4. Performance optimization for large datasets

**Future Enhancements:**
1. Better failure analysis (root cause detection)
2. Predictive test prioritization (which tests to run first)
3. Graph database for failure relationships
4. Kubernetes deployment support
5. Fine-tuned AI model for QA-specific tasks

---

## Summary

Sentinel QA Analytics Dashboard is a modern, AI-powered tool that makes test data analysis easy. Users upload test results, ask questions, and get instant insights without writing SQL. The architecture is clean (separate frontend, backend, database layers), secure (JWT auth, SQL injection prevention), and extensible (multiple LLM providers, multiple data sources).

The system is production-ready for small to medium teams but needs security hardening and performance optimization for enterprise scale.

**Key Takeaway:** This is a smart tool that bridges the gap between raw test data and actionable insights for QA teams.
