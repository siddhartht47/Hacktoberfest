@echo off
cd /d "%~dp0ollama-setup-buddy"
call .venv\Scripts\activate.bat
python run.py
pause

