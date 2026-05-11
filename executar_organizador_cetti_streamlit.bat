@echo off
REM Inicia a interface e o monitor em modo silencioso, sem abrir dois terminais.

setlocal
cd /d "%~dp0"

set "SCRIPT_PS1=%~dp0start_cetti.ps1"

if not exist "%SCRIPT_PS1%" (
	echo Nao foi possivel encontrar "%SCRIPT_PS1%"
	exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_PS1%"

exit /b %errorlevel%

