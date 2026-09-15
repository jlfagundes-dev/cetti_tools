@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=%~dp0.venv\Scripts\python.exe"
set "START_SCRIPT=%~dp0start_cetti_local.ps1"

if not exist "%PYTHON%" (
    echo Ambiente nao instalado. Execute instalar_cliente_local.bat primeiro.
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%START_SCRIPT%"
echo Monitor e painel iniciados.
echo Acesse http://localhost:8501
endlocal
