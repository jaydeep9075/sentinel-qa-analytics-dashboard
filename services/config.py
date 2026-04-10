import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base directory where all ingestion folders live
BASE_DIR = Path(__file__).parent.parent
DATA_BASE_PATH = BASE_DIR / "data"
DATA_BASE_PATH.mkdir(exist_ok=True)

# LLM
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
LLM_MODEL = os.getenv("LLM_MODEL", "models/gemini-2.5-flash")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Misc
MAX_HISTORY_TURNS = 10

# RBA: Projects and roles root directories
PROJECTS_ROOT = os.getenv("PROJECTS_ROOT", str(BASE_DIR / "projects"))
ROLES_ROOT = os.getenv("ROLES_ROOT", str(BASE_DIR / "roles"))