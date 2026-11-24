@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto ready
py -3.12 -m venv .venv 2>nul
if exist ".venv\Scripts\python.exe" goto ready
powershell -NoProfile -Command "$r=Get-AppxPackage 'OpenAI.CodexPrimaryRuntime*' | Sort-Object Version -Descending | Select-Object -First 1; if ($r) { $p=Join-Path $r.InstallLocation 'dependencies\python\python.exe'; if(Test-Path -LiteralPath $p) { & $p -m venv .venv; exit $LASTEXITCODE } }; exit 1"
if not exist ".venv\Scripts\python.exe" (
  echo Install Python 3.12 or use the Docker option in README.md.
  pause
  exit /b 1
)
:ready
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  pause
  exit /b 1
)
".venv\Scripts\python.exe" serve.py --desktop
pause

