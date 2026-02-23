@echo off
setlocal
cd /d "%~dp0"

echo ===============================================
echo YourMusicSucks Discord Music Bot - Installer
echo ===============================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
  echo Python is not installed or not on PATH.
  echo Installing Python 3.12 with winget...
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  if %errorlevel% neq 0 (
    echo Failed to install Python automatically.
    echo Install Python manually, then re-run install.bat
    pause
    exit /b 1
  )
)

where ffmpeg >nul 2>nul
if %errorlevel% neq 0 (
  echo FFmpeg is not installed or not on PATH.
  echo Installing FFmpeg with winget...
  winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
  if %errorlevel% neq 0 (
    echo Failed to install FFmpeg automatically.
    echo Install FFmpeg manually, then re-run install.bat
    pause
    exit /b 1
  )
)

if not exist ".venv" (
  echo Creating virtual environment...
  python -m venv .venv
  if %errorlevel% neq 0 (
    echo Failed to create virtual environment.
    pause
    exit /b 1
  )
)

echo Installing Python dependencies...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if %errorlevel% neq 0 (
  echo Failed to install dependencies.
  pause
  exit /b 1
)

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Created .env from .env.example
)

echo.
echo Install complete.
echo Next: open .env and set your Discord and Spotify credentials.
echo Then run run.bat
echo.
pause
