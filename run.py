"""Root launcher: runs ollama-setup-buddy/run.py"""
import sys
import subprocess
from pathlib import Path

target = Path(__file__).resolve().parent / "ollama-setup-buddy" / "run.py"
venv_python = Path(__file__).resolve().parent / "ollama-setup-buddy" / ".venv" / ("Scripts\\python.exe" if sys.platform == "win32" else "bin/python")

python_bin = str(venv_python) if venv_python.exists() else sys.executable
sys.exit(subprocess.call([python_bin, str(target)] + sys.argv[1:], cwd=str(target.parent)))

