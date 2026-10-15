@echo off
setlocal
cd /d "%~dp0.."

set "PYTHON=%~dp0..\..\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo Ambiente virtual nao encontrado em "%PYTHON%".
    exit /b 1
)

"%PYTHON%" organizador_cetti.py
exit /b %errorlevel%
