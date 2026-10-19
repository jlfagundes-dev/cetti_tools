# Arquitetura atual

A base nova foi implementada na raiz do repositório, sem criar `versao_4/`, conforme decisão do projeto. As versões legadas continuam isoladas em `versao_1/`, `versao_2/` e `versao_3/`.

## Componentes da base nova

- `cetti_db.py`: usa somente `sqlite3`; mantém clientes, documentos, operações e versão do esquema.
- `cetti_indexador.py`: percorre a raiz de documentos, registra caminhos relativos, hash, tamanho e modificação, extrai PDFs novos/alterados e atualiza o índice de conteúdo, sem mover arquivos.
- `cetti_busca.py`: combina interpretação determinística com busca por metadados e conteúdo FTS5, retornando página, trecho e origem da correspondência.
- `cetti_operacoes.py`: coordena movimentação física, reindexação, prevenção de sobrescrita e rollback.
- `cetti_extracao.py`: extrai texto nativo com PyMuPDF, usa Tesseract como OCR padrão e pode fazer fallback para `glm-ocr`.
- `cetti_ia_local.py`: acessa somente Ollama em loopback, valida respostas com evidência de página e pode expandir consultas sem escolher arquivos diretamente.
- `cetti_organizacao.py`: compara primeiro o nome do arquivo com as pastas existentes,
  incluindo pequenas diferenças de grafia, e só depois usa nomes extraídos do documento
  para identificar ou criar a pasta do cliente.

## Limites de armazenamento

O sistema de arquivos continua sendo o armazenamento principal. O SQLite é somente um índice e não contém os PDFs.

A raiz de documentos e o banco são caminhos distintos:

- `CETTI_ROOT`: raiz autorizada dos documentos.
- `CETTI_DB_PATH`: arquivo SQLite local, fora de `CETTI_ROOT`.

O banco padrão fica em `%LOCALAPPDATA%\Cetti\Arquivista\cetti.sqlite3` no Windows.

## Busca por conteúdo

O SQLite também armazena o texto extraído por página em `document_pages` e mantém
um índice FTS5 local em `document_search`. Os PDFs permanecem na pasta original;
o banco guarda somente o índice necessário para localizar os arquivos.

A atualização extrai texto nativo por padrão. O OCR pode ser habilitado
explicitamente na interface ou por código para PDFs digitalizados. PDFs que não
podem ser lidos ficam registrados em `document_text` com status `error`, sem
interromper a indexação dos demais arquivos.

A busca combina nome, caminho, cliente e demais metadados com o texto das páginas.
Quando o Ollama local está disponível, ele pode interpretar a linguagem natural e
expandir termos (por exemplo, `carteira de trabalho` e `CTPS`). A execução da
consulta continua sendo feita pelo SQLite; se o Ollama estiver indisponível, a
busca determinística e textual permanece disponível.

## Independência das versões

- v1: `versao_1/organizador_cetti.py`, Gemini e configuração própria.
- v2: `versao_2/organizador_cetti_v2.py`, módulos próprios copiados e log próprio.
- v3: `versao_3/organizador_cetti_pdf.py`, OCR/PDF local e painel próprio.
- Base nova: módulos na raiz, sem alterar os pontos de entrada legados.

Os módulos compartilhados foram duplicados entre v2 e v3. A base nova não importa código das versões legadas.

## Segurança operacional

- Caminhos de abertura e movimentação são validados contra `CETTI_ROOT`.
- Destinos existentes não são sobrescritos.
- Ollama aceita somente `localhost`, `127.0.0.1` ou `::1`.
- Modelos não são baixados automaticamente.
- A indexação inicial não altera os documentos.

## Estratégia híbrida de OCR

1. PDFs com texto nativo são processados diretamente pelo PyMuPDF.
2. Páginas sem texto usam Tesseract por padrão.
3. Quando a confiança do Tesseract fica abaixo do limite, `glm-ocr` pode ser usado como fallback se um `OllamaClient` local for fornecido.
4. Resultados de baixa confiança, páginas vazias e resultados do `glm-ocr` são marcados para revisão humana.
