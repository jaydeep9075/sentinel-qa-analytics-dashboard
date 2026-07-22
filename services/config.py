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