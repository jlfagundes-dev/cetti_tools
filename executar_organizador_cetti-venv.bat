@echo off
REM Script para executar o organizador com o ambiente virtual

cd /d "%~dp0"

REM Ativa o ambiente virtual
call venv\Scripts\activate.bat

REM Executa o script
python organizador_cetti.py

pause
