# Sentinel QA Intelligence - AI-Powered Test Analytics Platform

## Overview

Sentinel QA Analytics Dashboard is an intelligent analytics platform designed for Quality Assurance teams to visualize, analyze, and derive insights from test data. It combines traditional analytics with AI-powered natural language processing.

### Key Capabilities

- Real-time KPI monitoring and test status visualization
- Historical trend analysis for quality improvements
- Module stability metrics
- Slow test detection for performance optimization
- AI-driven chart generation from plain English prompts
- Conversational analytics interface
- Flexible AI backend support (Google Gemini, Ollama, OpenAI)

### Architecture Components

- **Backend API Service** (Python/FastAPI): Data processing, analytics, AI interactions
- **Frontend Dashboard** (Next.js): Interactive visualizations and UI
- **Data Ingestion Layer**: Processes test data from various sources
- **AI Enhancement Module**: Natural language querying and chart generation

---

## Quick Setup

### Prerequisites

- Python 3.8+
- Node.js 16+

### Installation Commands

```bash
# Clone repository
git clone https://github.com/jaydeep9075/sentinel-qa-analytics-dashboard.git
cd sentinel-qa-analytics-dashboard

# Setup Python virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Mac/Linux

# Install Python dependencies
pip install fastapi uvicorn pydantic python-multipart pandas numpy duckdb lancedb pyarrow google-generativeai sentence-transformers requests openai anthropic plotly kaleido python-dotenv pymysql sqlalchemy typing-extensions python-jose

# Configure environment variables
# Add LLM_PROVIDER, LLM_API_KEY, LLM_MODEL to .env file

# Run data ingestion
cd universal_ingester
python ingester.py
cd ..

# Start backend server
python -m services.main

# In new terminal, setup frontend
cd frontend/qa-dashboard
npm install
npm run dev
```

### Access Points

- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **Frontend:** http://localhost:3000

---

## Environment Configuration (.env)

```env
LLM_PROVIDER=gemini
LLM_API_KEY=your_api_key_here
LLM_MODEL=models/gemini-2.5-flash
```

---

## Project Structure

```
sentinel-qa-analytics-dashboard/
├── services/           # Backend FastAPI service
│   ├── main.py        # API endpoints
│   ├── handlers.py    # Chat & chart logic
│   ├── llm_client.py  # LLM abstraction
│   ├── data_loader.py # Data access
│   ├── memory.py      # History persistence
│   └── config.py      # Configuration
├── frontend/          # Next.js dashboard
│   └── qa-dashboard/
├── universal_ingester/# Data ingestion
└── data/              # LanceDB storage
```

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI, Python |
| Frontend | Next.js, TypeScript, Tailwind CSS |
| Database | LanceDB, DuckDB |
| AI/LLM | Google Gemini, OpenAI, Anthropic, Ollama |
| Visualization | Plotly |
| Embeddings | Sentence Transformers |