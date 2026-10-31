"""Start the app:  python run.py   then open http://localhost:8000"""
import os
import sys
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

# Auto-switch to virtual environment if running with system Python
HERE = Path(__file__).resolve().parent
VENV_PYTHON = HERE / ".venv" / ("Scripts\\python.exe" if sys.platform == "win32" else "bin/python")

if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
    sys.exit(subprocess.call([str(VENV_PYTHON)] + sys.argv, cwd=str(HERE)))

try:
    import uvicorn
except ImportError:
    print("Error: Missing required packages.")
    print("Please run: pip install -r requirements.txt")
    sys.exit(1)

def _open_browser():
    time.sleep(1.2)
    webbrowser.open("http://localhost:8000")

if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False)
