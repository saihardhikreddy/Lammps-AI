"""Configuration settings for Local LAMMPS Research Assistant."""
import os
from pathlib import Path

# Base project paths
BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
DATA_DIR = BASE_DIR / "data"
DOCS_DIR = DATA_DIR / "docs"
EXAMPLES_DIR = DATA_DIR / "examples"
INDEX_DIR = DATA_DIR / "index"
SIMULATIONS_DIR = BASE_DIR / "simulations"
GENERATED_DIR = SIMULATIONS_DIR / "generated"
RUNS_DIR = SIMULATIONS_DIR / "runs"
DB_PATH = DATA_DIR / "memory.db"
ENV_FILE = BASE_DIR / ".env"

# Ensure all runtime and persistence directories exist
for p in [DOCS_DIR, EXAMPLES_DIR, INDEX_DIR, GENERATED_DIR, RUNS_DIR]:
    p.mkdir(parents=True, exist_ok=True)


def _load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines from .env into os.environ (stdlib fallback for python-dotenv).

    Variables already set in the real environment take precedence over the file.
    """
    if not path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(path, override=False)
        return
    except ImportError:
        pass
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# Load .env BEFORE reading any setting so that every variable in it takes effect
_load_env_file(ENV_FILE)

HOST = os.getenv("LAMMPS_ASSISTANT_HOST", "127.0.0.1")
PORT = int(os.getenv("LAMMPS_ASSISTANT_PORT", "8000"))

# Local Execution & LAMMPS Settings
LAMMPS_EXECUTABLE = os.getenv("LAMMPS_EXECUTABLE", "")
# Long enough for the default transport runs; override with LAMMPS_EXECUTION_TIMEOUT (seconds)
EXECUTION_TIMEOUT_SECONDS = int(os.getenv("LAMMPS_EXECUTION_TIMEOUT", "900"))

# Optional cloud LLM (Google Gemini). Leave GEMINI_API_KEY empty to stay fully offline.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

# Optional local LLM (Ollama)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
OLLAMA_TAGS_URL = os.getenv("OLLAMA_TAGS_URL", "http://127.0.0.1:11434/api/tags")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")
