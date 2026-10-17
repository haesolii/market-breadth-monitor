@echo off
rem One-time setup: Python venv + backend deps, frontend deps + production build, .env
setlocal
cd /d "%~dp0.."

where py >nul 2>nul && (py -3.12 --version >nul 2>nul && set "PY=py -3.12")
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [ERROR] Python 3.12+ not found. Install: winget install -e --id Python.Python.3.12
  exit /b 1
)
where npm >nul 2>nul || (echo [ERROR] Node.js not found. Install: winget install -e --id OpenJS.NodeJS.LTS & exit /b 1)

if not exist backend\.venv (
  echo [setup] creating Python venv...
  %PY% -m venv backend\.venv || exit /b 1
)
backend\.venv\Scripts\python -m pip install -q --upgrade pip
backend\.venv\Scripts\pip install -q -r backend\requirements.txt || exit /b 1

if not exist .env copy .env.example .env >nul

pushd frontend
call npm install --no-audit --no-fund || (popd & exit /b 1)
call npm run build || (popd & exit /b 1)
popd
echo [setup] done.
