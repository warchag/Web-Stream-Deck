@echo off
setlocal
cd /d "%~dp0"

if "%WEB_DECK_PORT%"=="" set "WEB_DECK_PORT=5001"
if "%WEB_DECK_TOKEN%"=="" set "WEB_DECK_TOKEN=1234"
set "WEB_DECK_URL=http://127.0.0.1:%WEB_DECK_PORT%/?token=%WEB_DECK_TOKEN%"

echo Starting Web Stream Deck...
echo Deck URL: %WEB_DECK_URL%

start "" "%WEB_DECK_URL%"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" app.py
) else (
  py app.py
)

pause
