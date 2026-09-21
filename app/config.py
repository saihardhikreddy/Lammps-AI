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

# Ensure all runtime and persistence directories exist
for p in [DOCS_DIR, EXAMPLES_DIR, INDEX_DIR, GENERATED_DIR, RUNS_DIR]:
    p.mkdir(parents=True, exist_ok=True)

# Local Server Settings
HOST = os.getenv("LAMMPS_ASSISTANT_HOST", "127.0.0.1")
PORT = int(os.getenv("LAMMPS_ASSISTANT_PORT", "8080"))

# Local Execution & LAMMPS Settings
LAMMPS_EXECUTABLE = os.getenv("LAMMPS_EXECUTABLE", "")
EXECUTION_TIMEOUT_SECONDS = 180

# Offline & Security Settings
OFFLINE_MODE = True
EXTERNAL_API_ENABLED = False
ALLOW_ARBITRARY_SHELL = False

# Local LLM Integration Settings
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_TAGS_URL = os.getenv("OLLAMA_TAGS_URL", "http://localhost:11434/api/tags")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")

