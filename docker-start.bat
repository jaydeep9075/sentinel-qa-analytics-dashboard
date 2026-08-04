@echo off
REM Builds (if needed) and starts both the backend and frontend containers.
REM Each runs in its own container ("separate space") - this one command
REM starts both together. Safe to run again later: unchanged images are
REM reused, nothing rebuilds unless the code changed.
REM
REM This script no longer creates users.db / config2.json / ingest-source.
REM All three now live inside DIRECTORIES that Docker creates by itself
REM (state\, data\, ingest-source\), and the backend seeds the files inside
REM them on startup - so there is nothing left to prepare by hand. .env is
REM the only thing a human has to supply.

cd /d "%~dp0"

if not exist ".env" (
    echo [!] .env not found. Copying .env.example to .env - EDIT IT before
    echo     continuing.
    echo.
    echo     Fill in the three values under section A:
    echo       SECRET_KEY                 signs login tokens ^(32+ chars^)
    echo       LLM_API_KEY                your LLM credential
    echo       BOOTSTRAP_ADMIN_PASSWORD   the first admin account
    copy .env.example .env >nul
    echo.
    echo Opening .env for you now. Save and close it, then re-run this script.
    notepad .env
    exit /b 1
)

echo Starting backend + frontend...
docker compose up --build -d
if errorlevel 1 (
    echo.
    echo [!] Startup failed. See what went wrong with:  docker compose logs
    pause
    exit /b 1
)

echo.
echo Dashboard: http://localhost:3000
echo Backend:   http://localhost:8000  ^(docs at /docs^)
echo.
echo Sign in with the BOOTSTRAP_ADMIN_USERNAME / BOOTSTRAP_ADMIN_PASSWORD
echo you set in .env. Everyone else requests access at /register, and you
echo approve them from the dashboard's Users page.
echo.
echo View logs:    docker compose logs -f
echo Stop:         docker-stop.bat
pause
