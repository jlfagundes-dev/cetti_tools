# Instalação e configuração

A base nova usa Python e a biblioteca padrão `sqlite3`. Não é necessário servidor de banco de dados.

## Ambiente

Na raiz do projeto, usando o Python 3.11 ou mais recente:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

O Streamlit e o `python-dotenv` fazem parte das dependências da aplicação. PyMuPDF,
pytesseract e Pillow são usados pela extração/OCR. O executável Tesseract também
precisa estar instalado no Windows e disponível no `PATH` quando OCR for usado.

O Ollama é opcional. A aplicação não instala nem baixa modelos automaticamente.

## Variáveis

Copie `.env.example` para `.env` na raiz do projeto e ajuste os dois caminhos:

```powershell
Copy-Item .env.example .env
notepad .env
```

O arquivo `.env` é ignorado pelo Git. Não coloque chaves ou documentos reais no
repositório.

Exemplo:

```powershell
CETTI_ROOT=C:/Dados/Cetti/Documentos
CETTI_DB_PATH=C:/Dados/Cetti/Estado/cetti.sqlite3
CETTI_OLLAMA_URL=http://127.0.0.1:11434
CETTI_TEXT_MODEL=qwen3:4b
CETTI_OCR_MODEL=glm-ocr
CETTI_OLLAMA_TIMEOUT=120
CETTI_OLLAMA_STATUS_TIMEOUT=15
ADVOGADO_PADRAO=DR. GENELÚCIO
```

O aplicativo carrega automaticamente o `.env` da raiz. Variáveis definidas
explicitamente no PowerShell têm precedência. O banco deve ficar fora de
`CETTI_ROOT` e fora de uma pasta sincronizada pelo OneDrive.

Para o Qwen, o aplicativo desativa o raciocínio prolongado (`think=false`),
limita a resposta a 256 tokens e usa temperatura zero. Isso reduz o tempo de
identificação sem alterar a resposta JSON esperada. A identificação do cliente
limita a geração a 128 tokens, enquanto as demais operações Qwen usam 256.
`CETTI_OLLAMA_TIMEOUT`
controla a geração; `CETTI_OLLAMA_STATUS_TIMEOUT` controla somente a verificação
rápida de disponibilidade do serviço.

Configure `ADVOGADO_PADRAO` com o nome do advogado responsável pelo
escritório. Esse nome é enviado ao Qwen como uma exclusão obrigatória e também
é bloqueado pelas regras locais, inclusive quando aparece como parte de um
nome completo. Para cadastrar mais de um advogado, separe os nomes por vírgula.

## Execução

Com o ambiente virtual ativado:

```powershell
python organizador_cetti_v4.py status
python organizador_cetti_v4.py index
python organizador_cetti_v4.py search "petição do cliente"
python organizador_cetti_v4.py ui
```

O painel abre em `http://127.0.0.1:8501`. Para extrair um PDF:

Para iniciar diretamente o painel no Windows, na raiz do projeto execute:

```powershell
.venv\Scripts\Activate.ps1
python organizador_cetti_v4.py ui
```

Se o ambiente virtual já estiver ativo, basta executar o segundo comando.

Na interface, use a aba **Ler e organizar documentos** e clique em
**Ler pasta e organizar automaticamente**. A operação valida arquivos estáveis,
analisa PDFs, move Word para `02_ARQUIVOS_DO_WORD`, move PDFs identificados para
`01_CLIENTES\<cliente>`, envia PDFs sem identificação para
`00_ARQUIVOS_NAO_ORGANIZADOS_AUTOMATICAMENTE`, arquiva assinaturas correspondentes
e atualiza o índice. O andamento aparece na própria tela. Arquivos com erro ou
sem correspondência permanecem na entrada para revisão.

```powershell
python organizador_cetti_v4.py extract "C:\Dados\Cetti\Documentos\arquivo.pdf" --ocr auto
```

Na interface, a opção **Iniciar Ollama durante a rotina para OCR** vem marcada.
Ela inicia o Ollama automaticamente quando ele não estiver rodando. O processo
iniciado pela rotina é encerrado ao final; uma instância que já estava rodando
não é encerrada. Instale previamente o Ollama e baixe os modelos configurados
(`CETTI_OCR_MODEL`, por padrão `glm-ocr`).
No CLI, use `--ollama` para o mesmo comportamento.
Para OCR somente com Tesseract, use `--ocr tesseract`; para desativar OCR, use
`--ocr off`.

## Dependências legadas

As versões antigas possuem seus próprios `requirements.txt` e configurações de exemplo dentro das respectivas pastas. Não reutilize automaticamente o `.env` de uma versão em outra.
