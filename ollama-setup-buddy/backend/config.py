"""Central settings. Everything can be overridden with environment variables."""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
FRONTEND_DIR = ROOT_DIR / "frontend"

# Where the *helper* Ollama server lives (the one that runs Gemma for this app).
# Note: this is deliberately not called OLLAMA_HOST, because Ollama itself reads
# that variable and expects a different format.
OLLAMA_URL = os.getenv("HELPER_OLLAMA_URL", "http://localhost:11434").rstrip("/")

# The open-source model that powers the helper. gemma3:1b is small enough for
# almost any laptop. Use gemma3:4b for better explanations if you have 8 GB+ RAM.
HELPER_MODEL = os.getenv("HELPER_MODEL", "gemma3:1b")

# Seconds to wait for the helper model before falling back to rules only.
HELPER_TIMEOUT = float(os.getenv("HELPER_TIMEOUT", "90"))
