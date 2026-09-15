@echo off
REM Executa o organizador local de PDFs sem IA

cd /d "%~dp0"

set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Nao foi possivel encontrar "%PYTHON%"
    echo Execute setup-ambiente.bat primeiro.
    pause
    exit /b 1
)

echo Iniciando organizador PDF sem IA com "%PYTHON%"...
echo.
"%PYTHON%" organizador_cetti_pdf.py

if errorlevel 1 (
    echo Falha ao iniciar o organizador PDF.
    pause
    exit /b 1
)

pause
