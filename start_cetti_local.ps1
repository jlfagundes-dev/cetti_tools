Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $Python)) {
    throw "Python do ambiente virtual nao encontrado em $Python"
}

Start-Process -FilePath $Python -ArgumentList @(
    'organizador_cetti_pdf.py'
) -WorkingDirectory $ProjectRoot -WindowStyle Hidden

Start-Process -FilePath $Python -ArgumentList @(
    '-m', 'streamlit', 'run', 'app_streamlit.py',
    '--server.headless', 'true',
    '--server.address', '127.0.0.1',
    '--server.port', '8501'
) -WorkingDirectory $ProjectRoot -WindowStyle Hidden
