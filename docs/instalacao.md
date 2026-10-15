# Instalação e configuração

A base nova usa Python e a biblioteca padrão `sqlite3`. Não é necessário servidor de banco de dados.

## Ambiente

Na raiz do projeto:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

PyMuPDF, pytesseract e Pillow são dependências da extração/OCR. O executável Tesseract também precisa estar instalado no Windows e disponível no `PATH` quando OCR for usado.

O Ollama é opcional. A aplicação não instala nem baixa modelos automaticamente.

## Variáveis

```powershell
$env:CETTI_ROOT = 'C:\Dados\Cetti\Documentos'
$env:CETTI_DB_PATH = 'C:\Dados\Cetti\Estado\cetti.sqlite3'
$env:CETTI_OLLAMA_URL = 'http://127.0.0.1:11434'
$env:CETTI_TEXT_MODEL = 'qwen3:4b'
$env:CETTI_OCR_MODEL = 'glm-ocr'
```

O banco deve ficar fora de `CETTI_ROOT` e fora de uma pasta sincronizada pelo OneDrive. Não coloque documentos reais dentro do repositório.

## Dependências legadas

As versões antigas possuem seus próprios `requirements.txt` e configurações de exemplo dentro das respectivas pastas. Não reutilize automaticamente o `.env` de uma versão em outra.
