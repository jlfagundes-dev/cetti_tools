# Recuperação e reversão

## Falha durante uma movimentação

`cetti_operacoes.move_document` registra `move_started`, executa a movimentação sem sobrescrever e reindexa o sistema. Se a indexação falhar, tenta restaurar o arquivo à origem e registra `move_rolled_back`.

Quando não for possível determinar o estado, não mova manualmente os dois caminhos. Verifique se origem e destino existem:

```python
from cetti_operacoes import recover_move

recover_move(origem, destino, root, database)
```

A recuperação apenas reindexa o estado observado. Se origem e destino existirem ao mesmo tempo, a função interrompe e exige revisão humana.

## Arquivo renomeado ou removido manualmente

Execute novamente:

```powershell
python cetti_indexador.py
```

O índice marca arquivos ausentes como `removed` e tenta reconhecer renomeações por hash sem alterar o sistema de arquivos.

## Falha de OCR ou Ollama

A pesquisa básica e a indexação continuam disponíveis sem OCR e sem Ollama. Instale/verifique as dependências somente quando precisar de extração avançada. Nenhum modelo é baixado automaticamente.

## Reversão da migração do repositório

As versões legadas estão em `versao_1/`, `versao_2/` e `versao_3/`. Os arquivos antigos da raiz foram removidos e não há commit criado pelo agente. Antes de confirmar as alterações, use o histórico local ou um backup do repositório para restaurar a estrutura anterior.

Não restaure arquivos da raiz por cima dos módulos novos sem revisar os caminhos e imports.
