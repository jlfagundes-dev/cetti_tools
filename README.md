# Arquivista Digital Cetti

O repositório mantém as versões legadas do Arquivista Digital separadas por diretório. Os arquivos originais da raiz foram removidos depois da migração; as cópias versionadas são a referência atual.

## Versões

- `versao_1/`: organizador baseado em Gemini, com entrada em `organizador_cetti.py`.
- `versao_2/`: organizador baseado em Gemini com interação e busca, com entrada em `organizador_cetti_v2.py`.
- `versao_3/`: organizador local de PDFs com OCR e painel Streamlit, com entrada em `organizador_cetti_pdf.py`.
- As etapas 3 a 6 da nova base foram implementadas na raiz, conforme solicitado, sem criar `versao_4/`.

Cada versão possui seus próprios scripts, configurações de exemplo, dependências, documentação e logs. Os documentos dos clientes não fazem parte deste repositório.

## Nova base local

Os módulos da base local são:

- `cetti_db.py`: SQLite, esquema, clientes, documentos e histórico.
- `cetti_indexador.py`: indexação somente leitura e detecção de alterações.
- `cetti_busca.py`: pesquisa determinística e abertura segura no Explorer.
- `cetti_operacoes.py`: movimentação segura, reindexação e recuperação.
- `cetti_extracao.py`: extração nativa de PDF e OCR opcional.
- `cetti_ia_local.py`: integração opcional com Ollama local.

Os documentos reais não fazem parte do repositório. Consulte [docs/arquitetura.md](docs/arquitetura.md), [docs/instalacao.md](docs/instalacao.md), [docs/uso.md](docs/uso.md), [docs/testes.md](docs/testes.md) e [docs/recuperacao.md](docs/recuperacao.md).
