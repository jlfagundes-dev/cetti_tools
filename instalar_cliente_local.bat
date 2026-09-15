@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "PROJECT_ROOT=%~dp0"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
set "PYTHON_BASE="
set "START_SCRIPT=%~dp0start_cetti_local.ps1"
set "TASK_NAME=ArquivistaDigitalCettiLocal"

 echo.
echo ========================================================
echo   Instalação local do Arquivista Digital Cetti v3
echo ========================================================
echo.

py -3 --version >nul 2>&1
if not errorlevel 1 set "PYTHON_BASE=py -3"

if not defined PYTHON_BASE (
    python --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_BASE=python"
)

if not defined PYTHON_BASE (
    echo Python nao encontrado. Tentando instalar Python 3.13 pelo winget...
    where winget >nul 2>&1
    if errorlevel 1 (
        echo ERRO: Python e winget nao foram encontrados.
        echo Instale Python em https://www.python.org/downloads/windows/
        echo Depois execute este instalador novamente.
        pause
        exit /b 1
    )

    winget install --id Python.Python.3.13 -e --scope user --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo ERRO: nao foi possivel instalar Python automaticamente.
        echo Instale Python manualmente em https://www.python.org/downloads/windows/
        pause
        exit /b 1
    )

    if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PYTHON_BASE=%LocalAppData%\Programs\Python\Python313\python.exe"
    if not defined PYTHON_BASE (
        py -3 --version >nul 2>&1
        if not errorlevel 1 set "PYTHON_BASE=py -3"
    )
)

if not defined PYTHON_BASE (
    echo ERRO: Python foi instalado, mas nao esta disponivel nesta sessao.
    echo Feche e abra o instalador novamente.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo Criando ambiente virtual...
    %PYTHON_BASE% -m venv .venv
    if errorlevel 1 goto :erro
)

if not exist "%PYTHON%" (
    echo ERRO: Python do ambiente virtual nao foi criado.
    goto :erro
)

echo Instalando dependencias...
"%PYTHON%" -m pip install --upgrade pip
if errorlevel 1 goto :erro
"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto :erro

if not exist ".env" (
    echo.
    set /p CAMINHO_RAIZ=Informe o caminho da pasta raiz do OneDrive [C:\Users\%USERNAME%\OneDrive\Cetti_Organizador]: 
    if "!CAMINHO_RAIZ!"=="" set "CAMINHO_RAIZ=C:\Users\%USERNAME%\OneDrive\Cetti_Organizador"
    >.env echo CAMINHO_RAIZ_DRIVE=!CAMINHO_RAIZ!
    echo Arquivo .env criado.
) else (
    echo Arquivo .env ja existe. O caminho configurado sera preservado.
)

if not exist "%START_SCRIPT%" (
    echo ERRO: arquivo de inicializacao nao encontrado.
    goto :erro
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$project=$env:PROJECT_ROOT; $script=$env:START_SCRIPT; $task=$env:TASK_NAME; schtasks /Create /SC ONLOGON /TN $task /TR ('powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ""' + $script + '""') /DELAY 0000:30 /F | Out-Null; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }"
if errorlevel 1 goto :erro

 echo.
echo ========================================================
echo Instalação concluída.
echo ========================================================
echo.
echo Inicialização automática: %TASK_NAME%
echo Painel local: http://localhost:8501
echo.
echo Para iniciar agora, execute:
echo   iniciar_cetti_local.bat
echo.
pause
exit /b 0

:erro
echo.
echo ERRO: a instalação nao foi concluida.
pause
exit /b 1
