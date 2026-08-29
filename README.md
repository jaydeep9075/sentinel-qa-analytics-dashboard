# TR-Insight — AI-Powered Test Analytics Dashboard

**AI QE that knows your results.**

TR-Insight is the test-reporting member of Testrig Technologies' **TR-TestIntelligence** suite. Point it at the test results your team already produces — Allure reports, spreadsheets, an existing database, or a live Playwright/Cypress run — and ask questions about them in plain English, with AI-generated charts and a defensible release call.

## Quick start

```bash
git clone https://github.com/jaydeep9075/sentinel-qa-analytics-dashboard.git
cd sentinel-qa-analytics-dashboard
cp .env.example .env
docker compose up --build -d
```

Dashboard: http://localhost:3000 · Backend API docs: http://localhost:8000/docs

Full walkthrough (Docker and local-dev paths, first login, first ingestion): [`docs/02-getting-started.md`](docs/02-getting-started.md).

## Documentation

| Doc | What's in it |
|---|---|
| [`docs/01-overview.md`](docs/01-overview.md) | What TR-Insight is, what it does, architecture at a glance |
| [`docs/02-getting-started.md`](docs/02-getting-started.md) | Install and first run — Docker or local dev |
| [`docs/03-architecture-guide.md`](docs/03-architecture-guide.md) | The technical deep-dive: modules, data flow, chart/chat pipelines, live execution |
| [`docs/04-marketing.md`](docs/04-marketing.md) | The one-pager — pitch, personas, differentiators |
| [`docs/05-docker.md`](docs/05-docker.md) | Images, compose files, build/run, env vars for Docker |
| [`docs/06-hosting-and-resources.md`](docs/06-hosting-and-resources.md) | Sizing, storage layout, full env-var reference, scaling, hosting options |
| [`docs/07-user-guide.md`](docs/07-user-guide.md) | Using the dashboard: accounts, ingestion, chat, charts, live runs, admin console |

## Tech stack

| Component | Technology |
|---|---|
| Backend | FastAPI, Python, Uvicorn |
| Auth | JWT (python-jose), bcrypt |
| Frontend | Next.js 16, React 18, TypeScript, Tailwind CSS 4 |
| Database | LanceDB, DuckDB |
| AI / LLM | Google Gemini, OpenAI, Anthropic, Ollama, or any litellm-supported provider |
| Visualization | Plotly, Recharts, ApexCharts |
| Embeddings | Sentence Transformers |
| Ingestion | Allure JSON, files, MySQL/Postgres, APIs |

See interactive API docs at http://localhost:8000/docs after starting the backend.
