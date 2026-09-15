# Arquitetura do Arquivista Digital Inteligente da Cetti

O projeto foi desenhado para rodar no computador do cliente, sem servidor externo e sem Docker.
Ele atua como uma sentinela documental: monitora o Google Drive em tempo real, lê PDFs com IA, organiza a fila de documentos e disponibiliza a busca e a abertura das pastas pelo navegador do celular.

## Componentes

- `app_streamlit.py`: interface de chat e busca para o usuário final.
- `organizador_cetti_v2.py`: monitor do Drive sincronizado, leitura com IA e movimentação automática.
- `organizador_cetti_pdf.py`: monitor opcional sem IA, restrito a PDFs com texto extraível pelo `pypdf`.
- `cetti_core.py`: funções compartilhadas de raiz, busca, normalização e abertura de pastas.
- `cetti_logging.py`: grava e lê os logs mostrados no Streamlit.
- `cetti_interaction.py`: canal para perguntas pendentes sobre cliente desconhecido.
- `start_cetti.ps1`: inicialização silenciosa do Streamlit e do Cloudflare Tunnel.

## Fluxo

1. O usuário salva documentos na pasta `00_ENTRADA_AQUI` do Google Drive sincronizado.
2. O worker escolhido lê o texto do PDF localmente e usa regras determinísticas para decidir cliente, tipo e status.
3. O PDF é movido imediatamente para `01_Nao_Protocolado` ou `02_Protocolado`, mesmo sem assinatura.
4. Um arquivo `.p7s`, `.p7m` ou `.sig` é associado pelo mesmo nome-base do PDF e movido para `Documentos Assinados` dentro da pasta do cliente.
5. Se a assinatura chegar antes do PDF, ela permanece na entrada até o PDF correspondente aparecer. Se já existir uma assinatura, o sistema não sobrescreve e publica um aviso ao cliente.
6. O Streamlit mostra os logs e permite busca por cliente, documento ou trecho do nome.
7. O Cloudflare Tunnel publica a interface para acesso pelo celular do cliente.

## Premissas

- O computador do cliente precisa ficar ligado e conectado à internet.
- O Google Drive precisa estar sincronizado localmente.
- O tunnel deve apontar para `http://localhost:8501`.
- A versão sem IA não executa OCR: PDFs escaneados sem camada de texto vão para o log de erro e permanecem na entrada.
