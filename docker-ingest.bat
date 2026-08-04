@echo off
REM Triggers a one-shot ingestion run against whatever you dropped in
REM ingest-source\. Does NOT start/require the backend or frontend to be
REM running first - this runs independently and writes into data\, which
REM the backend picks up live (no restart needed) if it happens to be up.

cd /d "%~dp0"

REM config2.json now lives in state\ and is seeded automatically the first
REM time the backend starts. If you have never started the stack, do that
REM once (docker-start.bat) so the file exists, then edit it.
if not exist "state\config2.json" (
    echo [!] state\config2.json not found.
    echo     Start the stack once with docker-start.bat - the backend seeds
    echo     a default config there - then edit its "path" to point at
    echo     whatever you dropped under ingest-source\ and re-run this.
    pause
    exit /b 1
)

echo Drop your data into ingest-source\ first if you haven't already.
echo Running ingestion using state\config2.json...
echo.
docker compose run --rm ingest

echo.
echo Done. New ingestion should now appear at GET /ingestions on the
echo running backend, or start the dashboard with docker-start.bat.
pause
