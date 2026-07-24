
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base directory where all ingestion folders live
BASE_DIR = Path(__file__).parent.parent
DATA_BASE_PATH = BASE_DIR / "data"
DATA_BASE_PATH.mkdir(exist_ok=True)


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_origins(raw: str) -> list[str]:
    if not raw:
        return ["http://localhost:3000"]
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or ["http://localhost:3000"]

# LLM
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
# Prefer explicit LLM_API_KEY, then fall back to common provider-specific variables.
LLM_API_KEY = (
    os.getenv("LLM_API_KEY")
    or os.getenv("OPENAI_API_KEY")
    or os.getenv("GEMINI_API_KEY")
    or os.getenv("ANTHROPIC_API_KEY")
    or ""
)
LLM_MODEL = os.getenv("LLM_MODEL", "models/gemini-2.5-flash")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
LLM_API_BASE = os.getenv("LLM_API_BASE") or os.getenv("OPENAI_API_BASE") or ""

# Security
SECRET_KEY = os.getenv("SECRET_KEY", "")
BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12"))

# CORS
CORS_ALLOWED_ORIGINS = _parse_origins(os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000"))

# Auth storage (free, local defaults)
AUTH_BACKEND = os.getenv("AUTH_BACKEND", "db").strip().lower()  # db | memory
AUTH_USER_STORE_URL = os.getenv("AUTH_USER_STORE_URL", f"sqlite:///{(BASE_DIR / 'users.db').as_posix()}")
AUTH_AUTO_SEED_USERS = _get_bool("AUTH_AUTO_SEED_USERS", False)
AUTH_SEED_FILE = os.getenv("AUTH_SEED_FILE", str(BASE_DIR / "auth_seed_users.json"))

# Misc
MAX_HISTORY_TURNS = 10
DEFAULT_WORKSPACE_ID = os.getenv("DEFAULT_WORKSPACE_ID", "default").strip().lower() or "default"

# Live test execution (reporter -> backend ingestion)
# Shared secret the @sentinel/playwright reporter sends as `x-api-key`.
# Left empty in local/dev by default so `playwright test` works with zero
# setup; set it before exposing the backend beyond your own machine.
LIVE_INGEST_API_KEY = os.getenv("LIVE_INGEST_API_KEY", "")
LIVE_RUNS_DIR = DATA_BASE_PATH / "runs"
# Optional. Unset (default) = single-instance mode: the live SSE bus and
# live-frame cache stay in-process, which is correct and free as long as
# there's exactly one backend process. Set this only once you actually run
# more than one backend instance behind a load balancer - it makes the SSE
# push and live-frame cache work correctly across instances instead of only
# within whichever one instance happened to receive a given request. See
# services/live_exec/bus.py and screencast.py.
REDIS_URL = os.getenv("REDIS_URL", "")

# RBA: Projects and roles root directories
PROJECTS_ROOT = os.getenv("PROJECTS_ROOT", str(BASE_DIR / "projects"))
ROLES_ROOT = os.getenv("ROLES_ROOT", str(BASE_DIR / "roles"))

# Ingestion guards (background ingestion runs off the request thread, but
# still needs sane bounds so one huge/malformed source can't hang forever)
INGEST_MAX_FILE_SIZE_BYTES = int(os.getenv("INGEST_MAX_FILE_SIZE_BYTES", str(200 * 1024 * 1024)))
INGEST_MAX_ROWS = int(os.getenv("INGEST_MAX_ROWS", "500000"))
INGEST_TIMEOUT_SECONDS = float(os.getenv("INGEST_TIMEOUT_SECONDS", "600"))

# Number of ingestions kept "warm" (loaded LanceDB/DuckDB connections) at once.
# Switching between more than this many distinct ingestions evicts the least
# recently used one instead of paying a full reload every time it's revisited.
INGESTION_POOL_SIZE = int(os.getenv("INGESTION_POOL_SIZE", "3"))

# Cross-build chat/chart questions ("how are we trending", "compare to the
# last build"). Two different costs, two different caps:
# - Trend/comparison answers read only each build's small pre-aggregated
#   summary.json (a few KB each) - cheap regardless of history size, so this
#   just bounds how far back "recent builds" means, not a performance guard.
MAX_TREND_BUILDS = int(os.getenv("MAX_TREND_BUILDS", "12"))
# - Row-level cross-build SQL (e.g. "which tests failed in the last 3
#   builds") re-runs a real query against each build's full dataset - this
#   one IS a real latency guard, so it's deliberately small and independent
#   of how much ingestion history actually exists.
MAX_CROSS_BUILD_QUERY_BUILDS = int(os.getenv("MAX_CROSS_BUILD_QUERY_BUILDS", "5"))


def validate_runtime_config() -> None:
    provider = (LLM_PROVIDER or "").strip().lower()
    model = (LLM_MODEL or "").strip()

    if not provider:
        raise ValueError("LLM_PROVIDER is required")
    if not model:
        raise ValueError("LLM_MODEL is required")

    if provider != "ollama" and not LLM_API_KEY:
        raise ValueError(
            "No API key configured. Set LLM_API_KEY (or provider-specific key), "
            "or switch LLM_PROVIDER=ollama for local/free inference."
        )

    if not SECRET_KEY or len(SECRET_KEY) < 32:
        raise ValueError("SECRET_KEY must be set and at least 32 characters")

    if BCRYPT_ROUNDS < 10 or BCRYPT_ROUNDS > 16:
        raise ValueError("BCRYPT_ROUNDS must be between 10 and 16")

    if AUTH_BACKEND not in {"db", "memory"}:
        raise ValueError("AUTH_BACKEND must be either 'db' or 'memory'")

    Path(PROJECTS_ROOT).mkdir(parents=True, exist_ok=True)
    Path(ROLES_ROOT).mkdir(parents=True, exist_ok=True)