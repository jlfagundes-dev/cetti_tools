# Instalação no computador do cliente

Este passo a passo assume que o repositório já foi clonado no PC do cliente.

## 1. Clonar o repositório

```powershell
git clone <URL_DO_REPOSITORIO>
cd cetti_tools
```

## 2. Configurar variáveis

Edite o arquivo `.env` com pelo menos:

- `GEMINI_API_KEY`
- `CAMINHO_RAIZ_DRIVE`
- `ADVOGADO_PADRAO`

Opcional para comportamento remoto por domínio público:

- `STREAMLIT_REMOTE_HOSTS=streamlit.cetti.me,app.seucliente.com`

## 3. Rodar o setup

Execute:

```bat
setup-ambiente.bat
```

O script:

- cria o ambiente virtual `.venv`
- instala as dependências
- configura o túnel Cloudflare dedicado
- cria a tarefa agendada para abrir o app no logon

Se o túnel ainda não existir, `start_cetti.ps1` sobe apenas o Streamlit local e avisa que o `setup-ambiente.bat` precisa ser executado uma vez para publicar o acesso pelo celular.

## Sequência correta

1. Execute `setup-ambiente.bat` uma única vez. Ele cria a `.venv`, instala dependências, cria ou reutiliza o tunnel Cloudflare e registra a inicialização automática.
2. Depois, `start_cetti.ps1` passa a servir para iniciar o app localmente e, quando a configuração do tunnel já existir, também sobe o Cloudflare Tunnel para publicar o Streamlit.

Quando o acesso vier de um host listado em `STREAMLIT_REMOTE_HOSTS`, o frontend força automaticamente o modo remoto (sem abrir Explorer no PC servidor).

## Nome do aplicativo

No painel e na documentação, o sistema aparece como Arquivista Digital Inteligente da Cetti.

## 4. Testar localmente

Abra:

```bat
executar_organizador_cetti_streamlit.bat
```

## 5. Acessar pelo celular

Use o hostname informado no setup, por exemplo:

```text
https://streamlit.cetti.me
```
