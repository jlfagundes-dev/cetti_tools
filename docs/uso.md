# Uso da base local

## Indexação

Configure `CETTI_ROOT` e, opcionalmente, `CETTI_DB_PATH`. Depois execute:

```powershell
python cetti_indexador.py
```

A operação percorre a raiz somente para leitura e imprime um resumo com arquivos novos, modificados, renomeados, removidos e ignorados.

## Pesquisa

A pesquisa pode ser usada por código:

```python
from cetti_busca import search_documents

resultados = search_documents(
    'Encontre a petição inicial do processo 1234567 em outubro de 2026',
    root=r'C:\Dados\Cetti\Documentos',
    database=r'C:\Dados\Cetti\Estado\cetti.sqlite3',
)

for resultado in resultados:
    print(resultado.path)
```

A interpretação não depende de IA. Consultas ambíguas retornam todos os candidatos para escolha da interface.

## Explorer

Depois de validar o resultado, use uma das ações protegidas:

```python
from cetti_busca import open_containing_folder, open_document, select_in_explorer

open_containing_folder(resultado.path, root)
select_in_explorer(resultado.path, root)
open_document(resultado.path, root)
```

Cada ação rejeita caminhos fora da raiz autorizada.

## Movimentação

Movimentações devem usar `move_document` para atualizar o índice e registrar o histórico:

```python
from cetti_operacoes import move_document

move_document(origem, destino, root, database)
```

O destino existente causa erro e não é sobrescrito. Se a reindexação falhar, o arquivo é restaurado à origem quando possível.

## Extração e IA local

```python
from cetti_extracao import extract_pdf

resultado = extract_pdf('documento.pdf', use_ocr=True)
print(resultado.text)
print(resultado.review_required, resultado.review_reasons)
```

Ollama é opcional:

```python
from cetti_ia_local import OllamaClient

cliente = OllamaClient()
if cliente.is_available():
    resultado = extract_pdf(
        'documento.pdf',
        ocr_backend='auto',
        ollama_client=cliente,
    )
    interpretacao = cliente.interpret_document(resultado.text, len(resultado.pages))
```

O Tesseract é a primeira tentativa. O `glm-ocr` só é usado no modo `auto` quando o Tesseract está indisponível ou abaixo do limite de confiança. Respostas do modelo são rejeitadas quando não seguem o esquema ou informam páginas inválidas.
