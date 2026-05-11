@echo off
REM Script para configurar o ambiente virtual e instalar dependências
REM Execute este arquivo uma única vez no computador do cliente

setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ========================================================
echo   Arquivista Digital Inteligente da Cetti - Setup do Cliente
echo ========================================================
echo.

REM -----------------------------------------------------------------
REM 1) Verifica Python e prepara o ambiente virtual local do projeto.
REM -----------------------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo ERRO: Python nao foi encontrado no PATH.
    echo Instale Python 3.10+ e marque a opcao Add Python to PATH.
    exit /b 1
)

if not exist ".venv" (
    echo Criando ambiente virtual em .venv...
    python -m venv .venv
    if errorlevel 1 (
        echo ERRO: nao foi possivel criar o ambiente virtual.
        exit /b 1
    )
)

set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo ERRO: nao encontrei o Python do ambiente virtual em "%PYTHON%".
    exit /b 1
)

echo Atualizando pip e instalando dependencias...
"%PYTHON%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

REM -----------------------------------------------------------------
REM 2) Coleta os dados do tunel Cloudflare sem sobrescrever outros projetos.
REM -----------------------------------------------------------------
set "CLOUDFLARED_CONFIG=%USERPROFILE%\.cloudflared\cetti-saas-config.yml"
set "CLOUDFLARED_DIR=%USERPROFILE%\.cloudflared"
set "TUNNEL_NAME=cetti-saas"
set "HOSTNAME=streamlit.cetti.me"
set "STREAMLIT_PORT=8501"

set /p TUNNEL_NAME=Nome do tunnel [cetti-saas]: 
if "%TUNNEL_NAME%"=="" set "TUNNEL_NAME=cetti-saas"

set /p HOSTNAME=Hostname publico para o Streamlit [streamlit.cetti.me]: 
if "%HOSTNAME%"=="" set "HOSTNAME=streamlit.cetti.me"

REM -----------------------------------------------------------------
REM 3) Garante que o cloudflared esteja disponivel e autenticado.
REM -----------------------------------------------------------------
where cloudflared >nul 2>&1
if errorlevel 1 (
    echo ERRO: cloudflared nao foi encontrado no PATH.
    echo Instale o cloudflared antes de continuar.
    exit /b 1
)

if not exist "%CLOUDFLARED_DIR%" mkdir "%CLOUDFLARED_DIR%"

set "CREDENTIALS_FILE="
for /f "delims=" %%F in ('dir /b /a-d /o-d "%CLOUDFLARED_DIR%\*.json" 2^>nul') do (
    if not defined CREDENTIALS_FILE set "CREDENTIALS_FILE=%CLOUDFLARED_DIR%\%%F"
)

if not defined CREDENTIALS_FILE (
    echo Nenhuma credencial do Cloudflare foi encontrada.
    echo Abrindo login do cloudflared para criar ou vincular o tunnel...
    cloudflared tunnel login
    if errorlevel 1 (
        echo ERRO: falha no login do cloudflared.
        exit /b 1
    )
)

cloudflared tunnel list | findstr /i /c:"%TUNNEL_NAME%" >nul 2>&1
if errorlevel 1 (
    echo Criando tunnel dedicado para este cliente: %TUNNEL_NAME%
    cloudflared tunnel create "%TUNNEL_NAME%"
    if errorlevel 1 (
        echo ERRO: nao foi possivel criar o tunnel.
        exit /b 1
    )

    set "CREDENTIALS_FILE="
    for /f "delims=" %%F in ('dir /b /a-d /o-d "%CLOUDFLARED_DIR%\*.json" 2^>nul') do (
        if not defined CREDENTIALS_FILE set "CREDENTIALS_FILE=%CLOUDFLARED_DIR%\%%F"
    )
)

if not defined CREDENTIALS_FILE (
    echo ERRO: nao foi possivel localizar o arquivo de credenciais do tunnel.
    exit /b 1
)

REM -----------------------------------------------------------------
REM 4) Escreve uma configuracao dedicada para o Streamlit.
REM -----------------------------------------------------------------
( 
    echo tunnel: %TUNNEL_NAME%
    echo credentials-file: %CREDENTIALS_FILE%
    echo.
    echo ingress:
    echo ^  - hostname: %HOSTNAME%
    echo ^    service: http://localhost:%STREAMLIT_PORT%
    echo ^  - service: http_status:404
) > "%CLOUDFLARED_CONFIG%"

echo Configuracao criada em: %CLOUDFLARED_CONFIG%

echo Registrando DNS do tunnel...
cloudflared tunnel route dns "%TUNNEL_NAME%" "%HOSTNAME%"

REM -----------------------------------------------------------------
REM 5) Cria a tarefa agendada para iniciar tudo no logon do Windows.
REM -----------------------------------------------------------------
set "TASK_NAME=ArquivistaDigitalInteligenteCetti"
set "START_SCRIPT=%~dp0start_cetti.ps1"

schtasks /Create /SC ONLOGON /TN "%TASK_NAME%" /TR "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ""%START_SCRIPT%""" /F
if errorlevel 1 (
    echo Aviso: nao foi possivel criar a tarefa agendada. Tentando fallback na pasta Startup...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
        "$wsh = New-Object -ComObject WScript.Shell; $startup = [Environment]::GetFolderPath('Startup'); $shortcut = $wsh.CreateShortcut((Join-Path $startup 'Arquivista Digital Inteligente da Cetti.lnk')); $shortcut.TargetPath = 'powershell.exe'; $shortcut.Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ""' + $args[0] + '""'; $shortcut.WorkingDirectory = Split-Path -Parent $args[0]; $shortcut.Save()" ^
        "%START_SCRIPT%"
    if errorlevel 1 (
        echo ERRO: nao foi possivel criar a inicializacao automatica.
        exit /b 1
    )
)

echo.
echo ========================================================
echo Setup concluido com sucesso.
echo ========================================================
echo.
echo Tunnel: %TUNNEL_NAME%
echo Hostname: %HOSTNAME%
echo Config: %CLOUDFLARED_CONFIG%
echo Tarefa agendada: %TASK_NAME%
echo Inicializacao automatica: tarefa agendada ou atalho na pasta Startup
echo.
echo Proximos passos:
echo   1. Preencha o arquivo .env com GEMINI_API_KEY e CAMINHO_RAIZ_DRIVE.
echo   2. Execute o atalho executar_organizador_cetti_streamlit.bat para testar.
echo   3. Acesse o app pelo hostname do Cloudflare no celular.
echo.
exit /b 0
