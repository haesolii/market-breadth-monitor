@echo off
rem Headless data refresh (used by Windows Task Scheduler). Only stale sources are fetched.
cd /d "%~dp0..\backend"
if not exist ..\data mkdir ..\data
.venv\Scripts\python -m app.refresh --only-stale >> ..\data\refresh_task.log 2>&1
