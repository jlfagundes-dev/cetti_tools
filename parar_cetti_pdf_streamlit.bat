@echo off
REM Encerra o monitor PDF e o painel Streamlit deste projeto.

set "CETTI_ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$root = $env:CETTI_ROOT; Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe', 'pythonw.exe') -and $_.CommandLine -like ('*' + $root + '*') -and $_.CommandLine -match 'streamlit|organizador_cetti_pdf' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

exit /b 0
