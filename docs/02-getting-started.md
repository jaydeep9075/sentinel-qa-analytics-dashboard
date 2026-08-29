# Getting Started

Two ways to run TR-Insight: **Docker** (recommended — one command, nothing to install but Docker itself) or **local dev** (Python + Node directly on your machine, for anyone actively changing the code). Both end up at the same dashboard.

## Option A — Docker (recommended)

### Prerequisites

Just **Docker Desktop**, installed and running. Python, Node and every dependency live inside the images.

```bash
docker --version
docker compose version
```

### 1. Create your `.env`

There is one `.env`, at the repo root, and it configures both services.

```bash
cp .env.example .env
```

You can genuinely leave it empty and start the stack — every value has a working default. Two worth setting before a real (non-throwaway) run:

- **`SECRET_KEY`** — signs login tokens. Left unset, one is generated into `state/secret_key` on first start; losing that file just signs everyone out (a new key is generated), it doesn't lock you out. Set your own (32+ chars) if you'd rather manage it as a secret:
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(48))"
  ```
- **`LLM_PROVIDER` / `LLM_MODEL` / `LLM_API_KEY`** (or the provider-specific key, e.g. `GEMINI_API_KEY`) — pick a vendor from the table below. Skipping this is fine too: the backend still starts, and an admin can finish LLM setup later from **Admin → Settings**, which has a live "Test connection" check.

| Provider | `LLM_PROVIDER` | Key variable | `LLM_MODEL` |
|---|---|---|---|
| Google Gemini (default) | `gemini` | `GEMINI_API_KEY` | `gemini/gemini-2.5-flash` |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` | `anthropic/claude-opus-5` |
| OpenAI | `openai` | `OPENAI_API_KEY` | `openai/gpt-4o-mini` |
| Groq | `groq` | `GROQ_API_KEY` | `groq/llama-3.3-70b-versatile` |
| Ollama (local, no key) | `ollama` | — | `ollama/llama3` |

Any other provider [litellm](https://github.com/BerriAI/litellm) supports also works — set `LLM_MODEL` explicitly since there's no built-in default for it. The full variable reference lives in [`06-hosting-and-resources.md`](06-hosting-and-resources.md).

### 2. Start it

```bash
docker compose up --build -d
```

That's the whole setup — `data/`, `state/` and `ingest-source/` are directory mounts, so Docker creates them and the backend seeds `state/config2.json` and `state/users.db` inside on first start. First run takes a few minutes (the backend installs `torch` and bakes in an embedding model); later runs reuse the build cache and start in seconds.

On Windows, double-clicking `docker-start.bat` does the same thing and walks you through the `.env` edit interactively.

### 3. Log in

The very first login is the bootstrap admin account:

- If you set `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD` in `.env`, use those.
- If you left them unset, the backend generates a password and prints it once in the startup logs:
  ```bash
  docker compose logs backend
  ```
  (the username defaults to `admin`).

Either way, the first login lands you straight on **Account settings** and won't let you go anywhere else until you set a real username/password — that's a forced password change, not a bug. From there, use the **Admin** link (or go to `/admin`) to finish LLM setup, approve other users, and set token limits. Everyone else gets an account by registering at `/register` and being approved by an admin — see [`07-user-guide.md`](07-user-guide.md).

### 4. Access points

| | |
|---|---|
| Dashboard | http://localhost:3000 |
| Request an account | http://localhost:3000/register |
| Your account | http://localhost:3000/account |
| Admin console | http://localhost:3000/admin |
| Backend API docs (Swagger) | http://localhost:8000/docs |
| Backend health check | http://localhost:8000/health |

### 5. Get a build in

Simplest path: drop a zipped or unzipped `allure-results` folder into `ingest-source/`, set `AUTO_INGEST_ENABLED=true` in `.env`, and it appears in the dashboard within ~30 seconds. Three other ways to ingest (HTTP upload, the dashboard's "Add Build" box, a one-shot container) are covered in [`07-user-guide.md`](07-user-guide.md).

### Everyday commands

| I want to… | Command |
|---|---|
| Start both services | `docker compose up -d` |
| Stop both | `docker compose down` (data is untouched) |
| Watch logs | `docker compose logs -f` |
| Rebuild after a backend code change | `docker compose up -d --build backend` |
| Rebuild after a frontend code change | `docker compose up -d --build frontend` |

More detail on rebuilding, relocating storage, and the full Docker picture: [`05-docker.md`](05-docker.md).

---

## Option B — Local dev (no Docker)

For anyone actively editing `services/` or `frontend/`.

### Prerequisites

- Python 3.10+ (the pinned `requirements.txt` is tested against 3.12)
- Node.js 18+

### Install

```bash
git clone <this repository>
cd sentinel-qa-analytics-dashboard

python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
```

`requirements.txt` already includes the auth stack (`python-jose[cryptography]`, `bcrypt`) — no separate install step needed.

Create a root `.env` (same file Docker reads — see Option A above for the essentials) and a `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Ingest a build

```bash
cd universal_ingester
python ingester.py          # reads config2.json at the repo root
cd ..
```

### Run it

```bash
# Backend, from the repo root
python -m services.main

# Frontend, in a second terminal
cd frontend
npm install
npm run dev
```

Access points are the same as the Docker table above (`:3000` / `:8000`).

### Useful commands while developing

```bash
# Initialize the auth DB / manage users
python -m services.admin_users init-db
python -m services.admin_users create-user --username admin --role cto
python -m services.admin_users reset-password --username admin
python -m services.admin_users list-users

# Tests
python -m pytest tests/ -q
python verify_system.py     # dependency/DB/API sanity check
```

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Frontend can't reach the backend from your browser | Confirm `NEXT_PUBLIC_API_URL` was set at *build* time (it's inlined into the JS bundle) and that `CORS_ALLOWED_ORIGINS` includes the frontend's origin. |
| Backend won't start, complains about `SECRET_KEY` | It must be 32+ characters if you set it explicitly — or just leave it unset and let it auto-generate. |
| Can't log in | No accounts exist yet — see the bootstrap-admin step above, or (Docker) check `docker compose logs backend` for the generated password. |
| Using Ollama and the backend can't reach it (Docker) | `OLLAMA_URL=http://localhost:11434` points at the *container*. Use `http://host.docker.internal:11434` instead. |
| Backend takes ~30–45s to answer its first request | That's LanceDB/DuckDB opening the selected ingestion, not a model download (the embedding model is already baked into the image/venv). |

For the full technical picture once you're past first run, see [`03-architecture-guide.md`](03-architecture-guide.md).
