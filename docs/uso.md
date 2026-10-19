# Uso da base local

## Indexação

Configure `CETTI_ROOT` e, opcionalmente, `CETTI_DB_PATH`. Depois execute:

```powershell
python cetti_indexador.py
```

A operação percorre a raiz somente para leitura e imprime um resumo com arquivos novos, modificados, renomeados, removidos, ignorados, PDFs com texto indexado e erros de extração.

Para indexar PDFs digitalizados com OCR:

```python
from cetti_indexador import index_documents

resumo = index_documents(
    root=r'C:\Dados\Cetti\Documentos',
    database=r'C:\Dados\Cetti\Estado\cetti.sqlite3',
    use_ocr=True,
)
print(resumo.as_dict())
```

## Organização pela interface

Abra `python organizador_cetti_v4.py ui` e use a aba **Ler e organizar
documentos**. Um único clique executa a varredura dos arquivos diretamente na
pasta configurada, valida se cada arquivo terminou de ser copiado, extrai o
texto dos PDFs, tenta identificar o cliente pelas pastas existentes e move os
arquivos para a estrutura oficial. Arquivos já dentro de subpastas não são
movidos novamente. A entrada considera somente PDF, P7S/P7M/SIG e Word
(DOC/DOCX/DOCM); arquivos como `.url` e `desktop.ini` permanecem intocados e
não aparecem na varredura.

PDFs cujo cliente não pôde ser identificado vão para
`00_ARQUIVOS_NAO_ORGANIZADOS_AUTOMATICAMENTE`. Eles continuam disponíveis para
pesquisa e revisão manual. Nenhum arquivo é sobrescrito: em caso de nome
duplicado, o destino recebe o sufixo `_duplicado`. Ao finalizar, a interface
mostra o resultado individual de cada arquivo processado, incluindo o cliente
identificado e o caminho de destino.

Se a opção de Ollama estiver marcada, a aplicação reutiliza uma instância local
já ativa ou inicia `ollama serve` somente durante a rotina. Ao terminar, encerra
apenas o processo iniciado pela aplicação; não interfere em uma instância que já
estava ativa.

O painel também oferece o diagnóstico detalhado de cada PDF. Ele informa se o
texto veio do PyMuPDF nativo, Tesseract ou `glm-ocr`, qual modelo Ollama foi
usado, o nome retornado pelo modelo Qwen e o prompt enviado. Quando Ollama não
foi usado, isso também é registrado explicitamente.

Quando o Ollama está disponível, o Qwen lista as partes encontradas no texto,
incluindo nome e papel processual, em vez de escolher somente a primeira parte.
O organizador compara todos esses nomes com o nome do arquivo e escolhe a
correspondência mais forte, inclusive tolerando pequenos erros de digitação.
Isso permite escolher `ELTECH` a partir de `Sentenca Eltch.pdf` mesmo quando
`HEVELLY` aparece como autora e `ELTECH` como réu. As regras locais permanecem
como fallback caso o Ollama não esteja disponível ou não retorne partes válidas.

Para evitar o timeout observado no modo de raciocínio padrão do `qwen3:4b`, as
gerações Qwen usam `think=false`, temperatura `0` e no máximo `256` tokens. O
A identificação do cliente usa no máximo 128 tokens; as demais gerações usam
256. O timeout de geração padrão é de 300 segundos (5 minutos), enquanto a verificação do serviço
usa um timeout separado de 15 segundos. Esses valores podem ser alterados no
`.env` por `CETTI_OLLAMA_TIMEOUT` e `CETTI_OLLAMA_STATUS_TIMEOUT`.

Na identificação do cliente, o prompt envia somente os primeiros 8.000
caracteres do texto extraído, priorizando a primeira página e os primeiros
parágrafos. O diagnóstico detalhado registra o prompt, a resposta bruta do
Qwen e o erro da chamada quando houver timeout ou outra falha.

Cada execução também é preservada em um log permanente. O arquivo fica em
`logs\cetti_organizacao.log`, ao lado do banco SQLite (portanto, normalmente
fora da pasta de documentos), e contém o identificador da execução, progresso,
resultado de cada arquivo, erros e os diagnósticos completos do Ollama. A
interface mostra o caminho do arquivo e oferece o botão **Baixar log completo
da organização** ao final da rotina. Como o log pode conter texto extraído e
prompts com dados jurídicos, mantenha-o em local protegido.

O nome configurado em `ADVOGADO_PADRAO` nunca é considerado cliente. A regra
vale tanto para a resposta do Qwen quanto para os candidatos extraídos
localmente; por exemplo, `DR. GENELÚCIO` também bloqueia o nome completo do
advogado quando ele aparece no documento.

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

A pesquisa consulta metadados e o conteúdo textual indexado por página. Por exemplo,
`carteira de trabalho do Erasmo` pode encontrar `CTPS Erasmo.pdf` pelo conteúdo,
mesmo sem uma correspondência literal completa no nome do arquivo. A interface pode
usar o Ollama local para expandir a consulta; a busca continua funcionando sem ele.
Cada resultado informa a página, o trecho e se a correspondência veio de metadados
ou conteúdo.

## Explorer

Depois de validar o resultado, use uma das ações protegidas:

```python
from cetti_busca import open_containing_folder, open_document, select_in_explorer

open_containing_folder(resultado.path, root)
select_in_explorer(resultado.path, root)
open_document(resultado.path, root)
```

Cada ação rejeita caminhos fora da raiz autorizada.

Na tela de resultados, **Copiar endereço** copia o caminho local completo do
arquivo selecionado. Esse endereço pode ser colado em um assinador ou enviado
ao cliente somente quando o computador do cliente tiver acesso à mesma pasta,
por exemplo por uma pasta compartilhada ou sincronizada. Um caminho local do
seu computador não transfere o arquivo nem funciona automaticamente em outro
computador.

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
