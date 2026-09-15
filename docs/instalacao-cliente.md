# Instalação local no computador do cliente

Este fluxo instala o arquivista localmente e faz o monitor PDF e o painel iniciarem automaticamente quando o usuário entrar no Windows.

## 1. Clonar o repositório

```powershell
git clone <URL_DO_REPOSITORIO>
cd cetti_tools
```

## 2. Executar o instalador local

Na pasta clonada, clique duas vezes em:

```bat
instalar_cliente_local.bat
```

O instalador:

- cria o ambiente virtual `.venv`;
- instala as dependências;
- cria o `.env` com o caminho do OneDrive, se ele ainda não existir;
- registra a tarefa `ArquivistaDigitalCettiLocal` no Agendador de Tarefas do Windows;
- configura o início automático no logon.

Se o Python não estiver instalado, o instalador tenta instalar o Python 3.13 automaticamente usando o `winget`. Caso o computador não tenha `winget`, instale o Python pelo site oficial e execute o instalador novamente.

Quando solicitado, informe a pasta raiz do OneDrive. Exemplo:

```text
C:\Users\usuario\OneDrive\Cetti_Organizador
```

## 3. Configurar variáveis

Edite o arquivo `.env` com pelo menos:

- `CAMINHO_RAIZ_DRIVE`

O arquivista PDF local não precisa de `GEMINI_API_KEY` nem de `ADVOGADO_PADRAO`.

Opcional para comportamento remoto por domínio público:

- `STREAMLIT_REMOTE_HOSTS=streamlit.cetti.me,app.seucliente.com`

## 4. Iniciar e testar

Para testar imediatamente sem reiniciar o computador:

```bat
iniciar_cetti_local.bat
```

Depois, o cliente pode acessar o painel local em:

```text
http://localhost:8501
```

No próximo logon do Windows, o monitor e o painel serão iniciados automaticamente em segundo plano.

## Nome do aplicativo

No painel e na documentação, o sistema aparece como Arquivista Digital Inteligente da Cetti.

## 5. Remover a inicialização automática

Se for necessário remover a tarefa criada pelo instalador:

```bat
schtasks /Delete /TN ArquivistaDigitalCettiLocal /F
```
