# Arquitetura do Arquivista Digital Inteligente da Cetti

O projeto foi desenhado para rodar no computador do cliente, sem servidor externo e sem Docker.
Ele atua como um arquivista digital: monitora o Google Drive em tempo real, lê PDFs localmente e organiza os documentos sem IA. Nesta v3, o painel serve apenas para acompanhamento operacional.

## Componentes

- `app_streamlit.py`: painel operacional com status, logs, avisos e estrutura monitorada.
- `organizador_cetti_v2.py`: versão anterior com leitura por IA.
- `organizador_cetti_pdf.py`: monitor opcional sem IA, restrito a PDFs com texto extraível pelo `pypdf`.
- `cetti_core.py`: funções compartilhadas para raiz e estrutura de pastas.
- `cetti_logging.py`: grava e lê os logs mostrados no Streamlit.
- `cetti_interaction.py`: módulo legado da versão com interação por chat.
- `start_cetti.ps1`: inicialização silenciosa do Streamlit e do Cloudflare Tunnel.

## Fluxo

1. O usuário salva documentos na pasta `00_ENTRADA_AQUI` do Google Drive sincronizado.
2. O worker escolhido lê o texto do PDF localmente e usa regras determinísticas para decidir cliente, tipo e status.
3. O PDF é movido imediatamente para `CLIENTES/<cliente>/<tipo>`.
4. Um arquivo `.p7s`, `.p7m` ou `.sig` é associado pelo mesmo nome-base do PDF e movido para `CLIENTES/<cliente>/Documentos Assinados`.
5. Se a assinatura chegar antes do PDF, ela permanece na entrada até o PDF correspondente aparecer. Se já existir uma assinatura, o sistema não sobrescreve e publica um aviso ao cliente.
6. O Streamlit mostra o estado do monitor, os logs, os avisos e as pastas acompanhadas.
7. O Cloudflare Tunnel pode publicar esse painel para acompanhamento remoto.

## Premissas

- O computador do cliente precisa ficar ligado e conectado à internet.
- O Google Drive precisa estar sincronizado localmente.
- O tunnel deve apontar para `http://localhost:8501`.
- A versão sem IA não executa OCR: PDFs escaneados sem camada de texto vão para o log de erro e permanecem na entrada.
