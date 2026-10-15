# Arquitetura do Arquivista Digital Inteligente da Cetti

O projeto foi desenhado para rodar no computador do cliente, sem servidor externo e sem Docker.
Ele atua como um arquivista digital: monitora o Google Drive em tempo real, lê PDFs localmente e organiza os documentos sem IA. Nesta v3, o painel serve apenas para acompanhamento operacional.

## Componentes

- `app_streamlit.py`: painel operacional com status, logs, avisos e estrutura monitorada.
- `organizador_cetti_v2.py`: versão anterior com leitura por IA.
- `organizador_cetti_pdf.py`: monitor opcional sem IA, com leitura por `pypdf` e fallback OCR para PDFs escaneados.
- `cetti_core.py`: funções compartilhadas para raiz e estrutura de pastas.
- `cetti_logging.py`: grava e lê os logs mostrados no Streamlit.
- `cetti_interaction.py`: módulo legado da versão com interação por chat.
- `start_cetti.ps1`: inicialização silenciosa do Streamlit e do Cloudflare Tunnel.

## Fluxo

1. O usuário salva documentos diretamente na biblioteca `Documentos` do Windows.
2. O worker escolhido lê o texto do PDF localmente e usa regras determinísticas para decidir cliente e status.
3. O PDF é movido imediatamente para `Documentos/01_CLIENTES/<cliente>`.
4. Um arquivo `.p7s`, `.p7m` ou `.sig` é associado pelo mesmo nome-base do PDF e movido para `Documentos/01_CLIENTES/<cliente>/Documentos Assinados`.
5. Se a assinatura chegar antes do PDF, ela permanece em `Documentos` até o PDF correspondente aparecer. Arquivos sem cliente vão para `Documentos/00_ARQUIVOS_NAO_ORGANIZADOS_AUTOMATICAMENTE`.
6. A classificação de PDFs considera somente arquivos cuja data de modificação seja do dia anterior; arquivos recebidos hoje aguardam na entrada até a virada do dia.
7. O Streamlit mostra o estado do monitor, os logs, os avisos e as pastas acompanhadas.
8. O Cloudflare Tunnel pode publicar esse painel para acompanhamento remoto.

## Premissas

- O computador do cliente precisa ficar ligado e conectado à internet.
- O Google Drive precisa estar sincronizado localmente.
- O tunnel deve apontar para `http://localhost:8501`.
- Para OCR, instale as dependências do `requirements.txt` e o executável Tesseract OCR no computador do cliente. O idioma português é usado quando estiver instalado.
