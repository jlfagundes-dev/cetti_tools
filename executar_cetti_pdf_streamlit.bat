@echo off
REM Inicia o monitor PDF sem IA e o painel Streamlit no mesmo computador.

setlocal
cd /d "%~dp0"

set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Nao foi possivel encontrar "%PYTHON%"
    echo Execute setup-ambiente.bat primeiro.
    pause
    exit /b 1
)

echo Iniciando monitor PDF sem IA em uma janela separada...
start "Cetti - Monitor PDF" /min cmd /c "cd /d "%~dp0" && "%PYTHON%" organizador_cetti_pdf.py"

echo.
echo Painel do advogado: http://localhost:8501
echo Para acesso pelo celular, inicie tambem start_cetti.ps1 apos configurar o Cloudflare.
echo Feche este terminal para encerrar o Streamlit.
echo.
"%PYTHON%" -m streamlit run app_streamlit.py --server.address 127.0.0.1 --server.port 8501

endlocal