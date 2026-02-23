@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found.
  echo Run install.bat first.
  pause
  exit /b 1
)

if not exist ".env" (
  echo .env file not found.
  echo Copy .env.example to .env and fill your tokens.
  pause
  exit /b 1
)

echo Starting bot...
call ".venv\Scripts\python.exe" -u ".\bot.py"
