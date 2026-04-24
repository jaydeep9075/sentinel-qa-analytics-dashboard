# Sentinel QA Intelligence Platform

An AI-powered test analytics platform that ingests test data from multiple sources (TiDB, Allure, files), stores it in a unified file‑based vector database (LanceDB), and provides a chat interface (RAG) and dynamic chart generation via natural language.

---

## 📖 Table of Contents
- [Overview](#overview)
- [Architecture](#architecture)
- [Folder Structure](#folder-structure)
- [Setup & Installation](#setup--installation)
- [Components](#components)
  - [Universal Ingester](#universal-ingester)
  - [Unified Service (Backend)](#unified-service-backend)
  - [Frontend Dashboard](#frontend-dashboard)
- [How It Works](#how-it-works)
  - [RAG (Retrieval-Augmented Generation)](#rag)
  - [Memory & History](#memory--history)
  - [Self‑Learning Potential](#self‑learning-potential)
- [Usage](#usage)
  - [Ingesting Data](#ingesting-data)
  - [Running the Backend](#running-the-backend)
  - [Running the Frontend](#running-the-frontend)
  - [API Endpoints](#api-endpoints)
- [Deployment](#deployment)
- [Future Enhancements](#future-enhancements)
- [Troubleshooting](#troubleshooting)

---

## Overview

The **Sentinel QA Intelligence Platform** is a modular, scalable solution for:
- **Ingesting** test data from various sources (databases, files, Allure reports) into a unified, versioned storage (LanceDB).
- **Providing an AI assistant** that can answer questions about test results using RAG (Retrieval-Augmented Generation) and SQL.
- **Generating charts** from natural language requests (Plotly).
- **Maintaining conversation memory** per session, stored in LanceDB.
- **Extensible** to other LLMs (Gemini, OpenAI, Anthropic, Ollama).

The system is designed for token efficiency and can scale from a local POC to production serving billions of vectors.

---

## Architecture
┌─────────────────────────────────────────────────────────────────┐
│ Data Sources │
│ TiDB │ Allure │ CSV/Excel │ PDF │ Images │ APIs │
└─────────────────────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────┐
│ Universal Ingester (Python) │
│ - Detects source type, reads data, extracts structure │
│ - Stores structured tables + documents with embeddings │
└─────────────────────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────┐
│ LanceDB (File‑based) │
│ - structured_test_cases │
│ - structured_test_results (flattened) │
│ - documents (chunks + embeddings) │
│ - chat_history, chart_history │
└─────────────────────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────┐
│ Unified Service (FastAPI) │
│ - SQL via DuckDB │
│ - Vector search (embedding similarity) │
│ - LLM decision (sql/vector/answer) │
│ - Memory storage │
│ - Chart generation (Plotly code execution) │
└─────────────────────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────┐
│ Frontend (Next.js + Tailwind) │
│ - Chat interface (session‑based) │
│ - Chart gallery (drag‑and‑drop, delete) │
│ - Data summary cards │
└─────────────────────────────────────────────────────────────────┘

text

---

## Folder Structure
sentinel-qa-analytics-dashboard/
├── universal_ingester/ # Data ingestion pipeline
│ ├── connectors/ # Source connectors
│ │ ├── base.py # Abstract base class
│ │ ├── db_connector.py # SQLAlchemy databases (TiDB, etc.)
│ │ ├── file_connector.py # CSV, Excel, PDF, images
│ │ ├── api_connector.py # REST APIs
│ │ └── allure_connector.py # Allure JSON results
│ ├── ingester.py # UniversalIngester class
│ ├── utils.py # EmbeddingGenerator (sentence‑transformers)
│ └── lancedb_tidb_test/ # Default data directory (created by ingester)
├── services/ # Modular backend (FastAPI)
│ ├── init.py
│ ├── config.py # Environment variables, paths
│ ├── state.py # Global database connections
│ ├── llm_client.py # Pluggable LLM client
│ ├── data_loader.py # Data loading & SQL/vector helpers
│ ├── memory.py # Chat/chart history storage
│ ├── handlers.py # Business logic for /chat and /chart
│ └── main.py # FastAPI app, endpoints
├── frontend/qa-dashboard/ # Next.js frontend
│ ├── app/ # App router pages
│ ├── components/ # React components
│ │ ├── AIChatbot.tsx
│ │ ├── AIChatInput.tsx
│ │ ├── AIGeneratedChart.tsx # Plotly wrapper
│ │ └── ChartGallery.tsx # Gallery with drag‑and‑drop
│ ├── lib/ # API client functions
│ │ └── api.ts
│ └── package.json
├── .env # LLM API keys, provider, model
├── config.json # Ingestion source configurations
└── README.md

text

---

## Setup & Installation

### Prerequisites
- Python 3.10+
- Node.js 18+ (for frontend)
- (Optional) Docker if running LanceDB in container, but we use embedded.

### Backend Setup
1. Clone the repository and navigate to the project root.
2. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Linux/Mac
   .venv\Scripts\activate      # Windows
Install Python dependencies:

bash
pip install -r requirements.txt
(If requirements.txt is missing, install manually: lancedb duckdb pandas numpy sentence-transformers fastapi uvicorn python-dotenv google-generativeai plotly)

Create .env file in the root with your LLM credentials:

env
LLM_PROVIDER=gemini
LLM_API_KEY=your_gemini_api_key
LLM_MODEL=models/gemini-2.5-flash
(Other supported providers: openai, anthropic, ollama)

Frontend Setup
Navigate to the frontend directory:

bash
cd frontend/qa-dashboard
Install Node dependencies:

bash
npm install
Ensure the API endpoint in lib/api.ts points to your backend (default: http://localhost:8000).

Components
Universal Ingester
Purpose: Convert any data source into LanceDB tables with versioning (build_id).

Key features:

Plug‑in connectors for DBs, files, APIs, Allure.

Automatically infers schema and splits unstructured text.

Generates embeddings (using sentence-transformers) for each row/chunk.

Stores structured tables (structured_*) and a unified documents table for vector search.

Maintains sources table for provenance.

Usage: Run with a configuration file:

bash
python universal_ingester/ingester.py --config config.json
(Modify ingester.py to accept command‑line arguments if not already implemented.)

Unified Service (Backend)
Purpose: Provide chat and chart APIs using the ingested data.

Key features:

SQL execution via DuckDB on registered tables.

Vector search on documents table.

LLM‑driven decision (choose SQL, vector, or direct answer).

Session‑based memory (chat and chart history stored in LanceDB).

Chart generation by executing Plotly code from LLM.

Run:

bash
python -m services.main
(Ensure you are in the project root.)

Frontend Dashboard
Purpose: User interface for querying and visualising.

Key features:

Chat interface with persistent sessions (session ID stored in localStorage).

Gallery of generated charts with drag‑and‑drop reordering and delete.

Data summary cards (total tests, passed/failed, pass rate).

Run:

bash
cd frontend/qa-dashboard
npm run dev
Access at http://localhost:3000.

How It Works
RAG (Retrieval-Augmented Generation)
User sends a chat message.

The service retrieves conversation history and current data schema.

LLM decides the best action: SQL, vector search, or direct answer.

SQL: A DuckDB query is generated, executed, and the results are passed back to the LLM for a natural language answer.

Vector: The query is embedded and used to find similar document chunks in the documents table. Those chunks serve as context for the final answer.

Answer: The LLM directly returns a response (e.g., “I don't have enough information”).

The answer is stored in chat_history (LanceDB) for that session.

Memory & History
Chat: Each message (user and assistant) is stored in chat_history with a session_id. The last MAX_HISTORY_TURNS (default 10) are included in the prompt.

Chart: Each generated chart is stored in chart_history with its Plotly JSON config, allowing users to revisit or delete them.

Both tables reside in LanceDB, enabling simple backups and scaling.

Self‑Learning Potential
While the current version does not automatically retrain models, the stored histories can be used for:

Fine‑tuning the LLM on successful interactions.

Improving prompts by analysing which questions led to good SQL generation.

Building a feedback loop (e.g., thumbs up/down) to reinforce correct answers.

Creating a custom knowledge base from frequently asked questions.

Usage
Ingesting Data
Prepare a config.json (see example below) listing your sources.

Run:

bash
python universal_ingester/ingester.py
(You may need to modify ingester.py to read from config.json if not already.)

Example config.json for TiDB and Allure:

json
{
  "sources": [
    {
      "type": "db",
      "params": {
        "connection_string": "mysql+pymysql://user:pass@host/db",
        "tables": ["test_cases", "test_results"],
        "connect_args": {"ssl": {"verify_cert": false}}
      }
    },
    {
      "type": "allure",
      "params": {
        "directory": "./allure-results"
      }
    }
  ]
}
Running the Backend
bash
python -m services.main
You should see logs indicating data loading and the server starting on http://0.0.0.0:8000.

Running the Frontend
bash
cd frontend/qa-dashboard
npm run dev
Visit http://localhost:3000.

API Endpoints
Method	Endpoint	Description
POST	/chat	Send a message, receive answer.
POST	/chart	Generate a chart from a natural language prompt.
GET	/chat/history/{session_id}	Retrieve chat history for a session.
GET	/chart/history/{session_id}	Retrieve chart history for a session.
DELETE	/chart/{chart_id}	Delete a specific chart.
GET	/health	Health check.
GET	/data/status	Summary statistics (total rows, passed/failed).
GET	/debug/data	Detailed debug info (for development).
Deployment
Backend (FastAPI)
Recommended: Use a cloud platform like Render, Railway, or a VM.

Set environment variables (LLM_PROVIDER, LLM_API_KEY, etc.) in the hosting environment.

The data directory (universal_ingester/lancedb_tidb_test) must be persistent (e.g., mounted volume or cloud storage). For a POC, you can use the same VM.

Frontend (Next.js)
Deploy to Vercel for free.

Update API_BASE in frontend/qa-dashboard/lib/api.ts to point to your deployed backend URL.

Build with npm run build and deploy.

Triggering Ingestion via CI/CD
Expose an /ingest endpoint in the backend that calls the ingester (or use a separate script).

In your CI pipeline (e.g., GitHub Actions), after tests run, invoke that endpoint with curl -X POST https://your-backend.com/ingest.

Future Enhancements
Incremental Updates – Instead of full re‑ingestion, detect changed rows using timestamps or primary keys.

Summarised Conversation Memory – Use a secondary LLM call to compress older conversation turns, reducing token usage.

Chart Improvement – Return the chart as an image in addition to JSON for compatibility.

Feedback System – Add upvote/downvote buttons to improve answer quality.

Multi‑tenant Support – Isolate data by project/organisation using build_id filters.

Advanced Vector Index – Tune HNSW parameters for faster search at scale.

Data Lineage – Track which build generated which test results, and allow comparing builds.

Export – Provide PDF/PNG exports of charts and chat transcripts.

Troubleshooting
“No module named 'sentence_transformers'”
Ensure you installed the package: pip install sentence-transformers.

“ValueError: Table 'chat_history' already exists”
The table creation code already handles this; if you see this, it's likely a race condition. The latest code checks for existence and uses if table_name not in tables.

Chart generation fails with “Object of type Timestamp is not JSON serializable”
We fixed this in handlers.py by converting timestamps to ISO strings before serializing to JSON.

LLM returns markdown-wrapped JSON
The service strips ```json ... ``` fences before parsing.

Frontend cannot connect to backend
Check that the backend is running and the API_BASE in api.ts is correct.

Ensure CORS is enabled (already in main.py with allow_origins=["*"]).

Memory usage
For large datasets, adjust MAX_HISTORY_TURNS in config.py to a smaller number to limit prompt size.

