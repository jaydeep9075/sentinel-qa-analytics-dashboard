import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
BASE_DIR = Path(__file__).parent.parent
DATA_PATH = BASE_DIR / "universal_ingester" / "lancedb_tidb_test"

# LLM
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
LLM_MODEL = os.getenv("LLM_MODEL", "models/gemini-2.5-flash")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Misc
MAX_HISTORY_TURNS = 10