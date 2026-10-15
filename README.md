# Arquivista Digital Cetti

O repositório mantém as versões do Arquivista Digital separadas por diretório. Os arquivos originais da raiz foram preservados durante a migração para permitir reversão.

## Versões

- `versao_1/`: organizador baseado em Gemini, com entrada em `organizador_cetti.py`.
- `versao_2/`: organizador baseado em Gemini com interação e busca, com entrada em `organizador_cetti_v2.py`.
- `versao_3/`: organizador local de PDFs com OCR e painel Streamlit, com entrada em `organizador_cetti_pdf.py`.
- `versao_4/`: reservada para desenvolvimento posterior, conforme `docs/prompt_mestre_versao_4.md`.

Cada versão possui seus próprios scripts, configurações de exemplo, dependências, documentação e logs. Os documentos dos clientes não fazem parte deste repositório.

## Estado da migração

A migração foi realizada por cópia. Os arquivos antigos da raiz ainda não devem ser removidos até que os lançadores de cada versão sejam validados em ambiente de teste.

A v3 utiliza um ambiente virtual próprio em `versao_3/.venv`. A v1 e a v2 mantêm lançadores de compatibilidade que podem utilizar o ambiente legado da raiz até que seus instaladores próprios sejam executados.
