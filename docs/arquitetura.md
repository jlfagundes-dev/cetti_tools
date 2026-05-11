# Arquitetura do Arquivista Digital Inteligente da Cetti

O projeto foi desenhado para rodar no computador do cliente, sem servidor externo e sem Docker.
Ele atua como uma sentinela documental: monitora o Google Drive em tempo real, lê PDFs com IA, organiza a fila de documentos e disponibiliza a busca e a abertura das pastas pelo navegador do celular.

## Componentes

- `app_streamlit.py`: interface de chat e busca para o usuário final.
- `organizador_cetti_v2.py`: monitor do Drive sincronizado, leitura com IA e movimentação automática.
- `cetti_core.py`: funções compartilhadas de raiz, busca, normalização e abertura de pastas.
- `cetti_logging.py`: grava e lê os logs mostrados no Streamlit.
- `cetti_interaction.py`: canal para perguntas pendentes sobre cliente desconhecido.
- `start_cetti.ps1`: inicialização silenciosa do Streamlit e do Cloudflare Tunnel.

## Fluxo

1. O usuário salva documentos na pasta `00_ENTRADA_AQUI` do Google Drive sincronizado.
2. O worker lê o arquivo, chama o Gemini e decide cliente e tipo.
3. O arquivo é movido para `01_Nao_Protocolado` ou `02_Protocolado`.
4. O Streamlit mostra os logs e permite busca por cliente, documento ou trecho do nome.
5. O Cloudflare Tunnel publica a interface para acesso pelo celular do cliente.

## Premissas

- O computador do cliente precisa ficar ligado e conectado à internet.
- O Google Drive precisa estar sincronizado localmente.
- O tunnel deve apontar para `http://localhost:8501`.
