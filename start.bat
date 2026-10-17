@echo off
rem Starts backend (http://localhost:8000) and dashboard (http://localhost:3000).
setlocal
cd /d "%~dp0"

if not exist backend\.venv\Scripts\python.exe (
  call scripts\setup.bat || (echo Setup failed. & pause & exit /b 1)
)
if not exist frontend\.next\BUILD_ID (
  pushd frontend & call npm run build & popd
)
if not exist data mkdir data

start "breadth-backend" /D "%~dp0backend" cmd /k ".venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "breadth-frontend" /D "%~dp0frontend" cmd /k "npx next start -H 127.0.0.1 -p 3000"

rem wait for the dashboard, then open it
powershell -NoProfile -Command "for($i=0;$i -lt 60;$i++){try{Invoke-WebRequest -UseBasicParsing http://127.0.0.1:3000 -TimeoutSec 2 | Out-Null; break}catch{Start-Sleep 1}}"
start "" http://localhost:3000
echo Dashboard: http://localhost:3000   (close the two console windows to stop)
