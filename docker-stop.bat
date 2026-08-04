@echo off
REM Stops both containers. Data (data/, users.db) is untouched - bind
REM mounts, not container storage, so it survives this.

cd /d "%~dp0"
docker compose down
pause
