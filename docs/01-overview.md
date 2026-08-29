# TR-Insight — Overview

## What it is

TR-Insight is an AI-powered test analytics dashboard: point it at the test results your team already produces — Allure reports, spreadsheets, an existing database, or a live Playwright/Cypress run — and it turns them into answers you can ask for in plain English, plus the chart and the release call to go with them.

It is the test-reporting member of **TR-TestIntelligence**, Testrig Technologies' suite of AI-driven QA frameworks:

| Framework | Purpose |
|---|---|
| **TR-Forge** | Test case generation |
| **TR-Automate** | Playwright automation with AI |
| **TR-Insight** | Test reporting and analytics dashboard (this project) |

Tagline: **"AI QE that knows your results."**

## What it does

- **JWT-authenticated dashboard and API**, with role-aware sessions (`admin`, `cto`, `qa-manager`, `sdet`) and per-team **workspaces** that scope who sees which builds.
- **Allure ingestion** via a drop-box watcher, an HTTP upload endpoint, the dashboard's "Add Build" flow, or a one-shot CLI/container run — plus file (CSV/Excel/JSON/…), database and generic API connectors through the universal ingester.
- **Build trend analysis** — pass rate, duration and regressions compared across builds at `/build-trends`.
- **Conversational AI analytics** — ask a question in plain English and get a SQL-backed answer, with session and chat history.
- **AI-driven chart generation** — 17 chart forms (bar, line, pie, heatmap, funnel, radar, and more), built deterministically from the parsed intent, not free-form LLM code.
- **Persona-driven responses** — the same data answers differently depending on who's asking, via role personas (`roles/*.md`) and per-project context (`projects/*/`).
- **Live test-run visibility** — a Playwright or Cypress repo can stream a run to `/runs/live` while it's still executing, with live logs, a live browser tile per worker, and failure detail, before it folds into normal build history.
- **Flexible LLM backend** — Google Gemini, OpenAI, Anthropic, Groq, Ollama, or any other provider [litellm](https://github.com/BerriAI/litellm) supports, switchable from `.env` or live from the admin console.
- Dark/light theme, module stability metrics, slow-test detection, mobile vs. desktop breakdowns.

## Architecture at a glance

```
   your browser
        |
        v
  frontend  :3000   Next.js 16 dashboard (landing, login, dashboard, build-trends, live runs)
        |
        v
  backend   :8000   FastAPI + LanceDB (vectors/history) + DuckDB (SQL analytics) + LLM client
        |
        v
  ./data/           every ingestion, on disk — not inside a container
```

- **Backend** (`services/`, Python/FastAPI) — auth, ingestion orchestration, the chat and chart pipelines, live-run streaming, the admin API.
- **Frontend** (`frontend/`, Next.js 16 + React 18 + TypeScript + Tailwind) — the dashboard itself, plus two server-side route handlers that read `data/` and `config2.json` directly.
- **Universal Ingester** (`universal_ingester/`) — Allure, file, database and API connectors that normalize any source into the same LanceDB/DuckDB tables.
- **AI layer** — role/project-aware prompt construction, a deterministic chart-intent parser, and an LLM that only ever writes SQL or plain-English answers, never chart code.

For the full technical breakdown — module-by-module, the request pipelines, the live-execution design — see [`03-architecture-guide.md`](03-architecture-guide.md). To get it running, see [`02-getting-started.md`](02-getting-started.md).
