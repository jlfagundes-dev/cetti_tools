@echo off
REM Inicia o monitor PDF e o painel sem abrir terminal ou navegador.

set "START_SCRIPT=%~dp0start_cetti_local.ps1"

if not exist "%START_SCRIPT%" exit /b 1

start "" /b powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%START_SCRIPT%"
exit /b 0