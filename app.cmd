@echo off
setlocal
set PYTHONUTF8=1
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Falta el entorno. Ejecuta: py -3.12 install.py
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0bin\app.py" %*
