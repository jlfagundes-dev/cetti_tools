@echo off
REM Script para configurar o ambiente virtual e instalar dependências
REM Execute este arquivo uma única vez no computador do cliente

echo.
echo ========================================================
echo   Cetti Organizador - Setup do Ambiente Virtual
echo ========================================================
echo.

REM Verifica se Python está instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ ERRO: Python não foi encontrado no PATH
    echo 💡 Instale Python 3.8+ de https://www.python.org
    echo    Marque a opção "Add Python to PATH" durante a instalação
    pause
    exit /b 1
)

echo ✅ Python encontrado
python --version
echo.

REM Cria o ambiente virtual
echo 📦 Criando ambiente virtual...
python -m venv venv

if not exist venv (
    echo ❌ ERRO: Falha ao criar ambiente virtual
    pause
    exit /b 1
)

echo ✅ Ambiente virtual criado
echo.

REM Ativa o ambiente virtual
echo 🔧 Ativando ambiente virtual...
call venv\Scripts\activate.bat

REM Atualiza pip
echo 📦 Atualizando pip...
python -m pip install --upgrade pip -q

REM Instala dependências
echo 📦 Instalando dependências...
pip install -r requirements.txt -q

echo.
echo ========================================================
echo   ✅ Setup concluído com sucesso!
echo ========================================================
echo.
echo 📝 Próximas etapas:
echo    1. Coloque sua GEMINI_API_KEY no arquivo .env
echo    2. Execute: executar_organizador_cetti.bat
echo.
pause
