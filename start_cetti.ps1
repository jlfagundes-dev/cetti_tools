Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Arquivo de inicializacao silenciosa do Arquivista Digital Inteligente da Cetti.
# Ele sobe o Streamlit localmente e, em seguida, inicia o cloudflared
# apontando para a configuracao dedicada deste projeto.

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$Cloudflared = (Get-Command cloudflared.exe -ErrorAction SilentlyContinue).Source
if (-not $Cloudflared) {
    $Cloudflared = Join-Path $env:USERPROFILE '.cloudflared\cloudflared.exe'
}

$CloudflaredDir = Join-Path $env:USERPROFILE '.cloudflared'
$PreferredConfig = Join-Path $CloudflaredDir 'cetti-streamlit-config.yml'
$LegacyConfig = Join-Path $CloudflaredDir 'cetti-saas-config.yml'

function Get-StreamlitTunnelConfig {
    $candidates = @(
        $PreferredConfig,
        $LegacyConfig
    )

    if (Test-Path $CloudflaredDir) {
        $candidates += Get-ChildItem -Path $CloudflaredDir -Filter '*.yml' -File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
        $candidates += Get-ChildItem -Path $CloudflaredDir -Filter '*.yaml' -File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
    }

    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (-not (Test-Path $candidate)) {
            continue
        }

        $content = Get-Content -Path $candidate -Raw -ErrorAction SilentlyContinue
        if ($content -match 'localhost:8501' -or $content -match 'streamlit\.cetti\.me' -or $content -match 'service:\s*http://localhost:8501') {
            return $candidate
        }
    }

    return $null
}

if (-not (Test-Path $Python)) {
    throw "Python do ambiente virtual nao encontrado em $Python"
}

if (-not (Test-Path $Cloudflared)) {
    Write-Host "cloudflared nao encontrado. O Streamlit sera iniciado apenas em modo local." -ForegroundColor Yellow
}

$CloudflaredConfig = Get-StreamlitTunnelConfig
if (-not $CloudflaredConfig) {
    Write-Host "Nenhuma configuracao dedicada do tunnel foi encontrada em $CloudflaredDir." -ForegroundColor Yellow
    Write-Host "Execute setup-ambiente.bat uma vez para criar o tunnel e habilitar acesso pelo celular." -ForegroundColor Yellow
}

# O Streamlit precisa ficar acessivel apenas no PC local; o tunnel publica a interface.
Start-Process -FilePath $Python -ArgumentList @(
    '-m', 'streamlit', 'run', 'app_streamlit.py',
    '--server.headless', 'true',
    '--server.address', '127.0.0.1',
    '--server.port', '8501'
) -WorkingDirectory $ProjectRoot -WindowStyle Hidden

if ($CloudflaredConfig -and (Test-Path $Cloudflared)) {
    # Inicia o tunnel usando o arquivo dedicado criado pelo setup.
    Start-Process -FilePath $Cloudflared -ArgumentList @(
        '--config', $CloudflaredConfig,
        'tunnel', 'run'
    ) -WorkingDirectory $ProjectRoot -WindowStyle Hidden
}
