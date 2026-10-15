# Testes e validação

Execute a suíte completa com:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Os testes usam apenas diretórios temporários e arquivos fictícios.

## Cobertura atual

- Criação e reabertura do SQLite.
- Indexação inicial sem movimentação.
- Reexecução sem duplicação.
- Detecção de alteração, renomeação e remoção.
- Banco rejeitado dentro da raiz de documentos.
- Pesquisa por nome, tipo, cliente, processo e mês/ano.
- Clientes com nomes semelhantes.
- Rejeição de caminhos externos.
- Movimentação sem sobrescrita.
- Rollback quando a atualização do índice falha.
- Recuperação de movimentação interrompida.
- Ausência de PyMuPDF/OCR sem produzir resultado falso.
- Preferência pelo texto nativo e pelo Tesseract antes do fallback `glm-ocr`.
- Marcação de revisão humana para baixa confiança e uso do `glm-ocr`.
- Validação de respostas do Ollama e páginas de evidência.
- Rejeição de endpoint Ollama externo.

## Limitações atuais

- Não foi feita movimentação de documentos reais.
- Não foram executados BATs ou scripts PowerShell neste ambiente.
- O OCR real de um PDF escaneado ainda precisa ser validado com um documento de teste apropriado.
- Ollama e os modelos `glm-ocr` e `qwen3:4b` não foram executados.
