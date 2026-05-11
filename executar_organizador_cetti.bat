@echo off
REM Script para executar o organizador principal com o ambiente virtual

cd /d "%~dp0"

set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
	echo Nao foi possivel encontrar "%PYTHON%"
	pause
	exit /b 1
)

echo Iniciando organizador com "%PYTHON%"...
echo.

REM Executa o script da V2 usando o Python do venv
"%PYTHON%" organizador_cetti_v2.py

if errorlevel 1 (
	echo Falha ao iniciar o organizador.
	pause
	exit /b 1
)

pause