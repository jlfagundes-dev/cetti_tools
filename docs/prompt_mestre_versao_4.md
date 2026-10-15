# PROJETO: ARQUIVISTA DIGITAL CETTI

## REORGANIZAÇÃO DO REPOSITÓRIO E DESENVOLVIMENTO DA VERSÃO 4
Atue como um engenheiro de software sênior especializado em Python, arquitetura de aplicações, automação de arquivos no Windows, SQLite, processamento de documentos e integração com modelos locais de IA.

Preciso reorganizar meu repositório do Arquivista Digital da Cetti para separar completamente as versões existentes e desenvolver uma nova versão 4.

**IMPORTANTE: comece somente inspecionando o projeto. Não mova, renomeie, exclua ou modifique arquivos antes de apresentar um diagnóstico e receber minha aprovação.**

---

## 1. CONTEXTO REAL DO PROJETO
O repositório contém três versões do Arquivista Digital da Cetti.

### Versão 1
Ponto de entrada:
`organizador_cetti.py`

### Versão 2
Ponto de entrada:
`organizador_cetti_v2.py`

### Versão 3
Ponto de entrada:
`organizador_cetti_pdf.py`

A versão 3 é a versão que utilizo atualmente.

**Não estou utilizando `cetti_core.py` como núcleo da versão 3. Não presuma que a v3 depende desse módulo.** Leia `organizador_cetti_pdf.py` e identifique suas dependências reais.

O repositório também pode conter arquivos relacionados a cada versão, como:

- Outros módulos Python.
- Scripts BAT.
- Scripts PowerShell.
- Arquivos de configuração.
- Arquivos de dependências.
- Logs.
- Documentação.
- Scripts de instalação e inicialização.
- Painéis e interfaces.
- Arquivos auxiliares de OCR e processamento de PDFs.
- Testes e outros recursos utilizados pelos programas.
Não classifique os arquivos somente pelo nome. Analise o conteúdo e as referências entre eles.

O objetivo é manter cada versão organizada e preservar a possibilidade de executar as versões anteriores.

---

## 2. OBJETIVO PRINCIPAL: SEPARAR COMPLETAMENTE AS VERSÕES
Quero uma estrutura de diretórios organizada por versão.

Cada versão deve ter uma pasta própria, contendo seu ponto de entrada e os arquivos necessários ao seu funcionamento.

Estrutura inicial desejada:

```
cetti_tools/
│
├── README.md
│
├── versao_1/
│   ├── organizador_cetti.py
│   ├── scripts/
│   ├── logs/
│   ├── config/
│   ├── docs/
│   └── demais arquivos efetivamente utilizados pela v1
│
├── versao_2/
│   ├── organizador_cetti_v2.py
│   ├── scripts/
│   ├── logs/
│   ├── config/
│   ├── docs/
│   └── demais arquivos efetivamente utilizados pela v2
│
├── versao_3/
│   ├── organizador_cetti_pdf.py
│   ├── scripts/
│   ├── logs/
│   ├── config/
│   ├── docs/
│   └── demais arquivos efetivamente utilizados pela v3
│
└── versao_4/
    ├── organizador_cetti_v4.py
    ├── cetti_db.py
    ├── cetti_indexador.py
    ├── cetti_busca.py
    ├── cetti_extracao.py
    ├── cetti_ia_local.py
    ├── scripts/
    ├── config/
    ├── docs/
    ├── tests/
    ├── logs/
    ├── requirements.txt
    └── demais arquivos exclusivos da v4
```
Essa estrutura é uma proposta inicial, não uma autorização para mover os arquivos imediatamente.

Adapte os subdiretórios às necessidades reais identificadas durante a inspeção.

Não crie pastas vazias sem propósito.

### Regras obrigatórias de separação

1. Os arquivos exclusivos da v1 devem ficar em `versao_1/`.
2. Os arquivos exclusivos da v2 devem ficar em `versao_2/`.
3. Os arquivos exclusivos da v3 devem ficar em `versao_3/`.
4. Os arquivos exclusivos da v4 devem ficar em `versao_4/`.
5. BATs, PowerShell, logs, documentação, configurações e dependências devem ser organizados junto da versão a que pertencem.
6. A documentação de uma versão não deve ser misturada com a documentação de outra.
7. Os logs de execução devem ser separados por versão.
8. Os arquivos de configuração não devem ser compartilhados implicitamente entre versões.
9. A v4 deve poder ser desenvolvida e testada sem modificar a implementação da v3.
10. As versões anteriores devem continuar executáveis após a reorganização.
Se houver arquivos compartilhados entre versões, não os mova arbitrariamente para uma das pastas.

Identifique o que realmente é compartilhado, explique a dependência e proponha uma solução que preserve o isolamento desejado.

A preferência é evitar dependências entre as versões. Se um arquivo compartilhado for indispensável, avalie duplicá-lo para manter cada versão independente, desde que isso não crie riscos de inconsistência ou problemas de licença.

Não introduza `cetti_core.py` como dependência da v3 sem evidência no código.

---

## 3. INSPEÇÃO OBRIGATÓRIA ANTES DA REORGANIZAÇÃO
Inspecione o repositório inteiro.

Comece pelos seguintes arquivos, caso existam:

- `organizador_cetti.py`
- `organizador_cetti_v2.py`
- `organizador_cetti_pdf.py`
- `cetti_core.py`
- `cetti_logging.py`
- `app_streamlit.py`
- `requirements.txt`
- Todos os arquivos BAT.
- Todos os arquivos PowerShell.
- Documentação e instruções de instalação.
- Arquivos de configuração.
- Testes automatizados.
- Outros módulos importados pelos três pontos de entrada.
Para cada versão, identifique:

1. Ponto de entrada.
2. Módulos Python importados.
3. Bibliotecas externas necessárias.
4. Scripts BAT e PowerShell utilizados.
5. Arquivos de configuração necessários.
6. Localização dos logs.
7. Dependências de OCR.
8. Dependências de PDF.
9. Dependências de interfaces.
10. Integrações externas.
11. Pastas e arquivos criados durante a execução.
12. Referências a caminhos relativos e absolutos.
13. Referências feitas pela documentação.
14. Recursos compartilhados com outras versões.
Monte um inventário relacionando cada arquivo à versão correspondente.

Quando um arquivo puder pertencer a mais de uma versão, registre a dúvida e explique por quê.

Não conclua que um arquivo pertence a uma versão apenas porque o nome contém `cetti`.

---

## 4. PLANO DE MIGRAÇÃO SEGURA
Depois da inspeção, apresente uma proposta detalhada de migração.

Inclua uma tabela com:

Arquivo atualVersão responsávelDestino propostoDependênciasRiscoExplique como manter cada versão executável após a mudança.

Analise especialmente:

- Imports Python.
- Caminho de execução dos BATs.
- Diretório de trabalho utilizado pelos scripts.
- Caminhos de logs.
- Caminhos de configuração.
- Referências na documentação.
- Arquivos de dependências.
- Localização dos ambientes virtuais.
- Caminhos para os documentos monitorados.
Os documentos dos clientes não devem ser movidos como parte da reorganização do código-fonte.

Não mova os documentos do OneDrive para dentro das pastas `versao_1`, `versao_2`, `versao_3` ou `versao_4`.

As pastas de versões são destinadas ao código, aos recursos de desenvolvimento e aos arquivos técnicos de cada versão.

Logs, bancos de dados, configurações e documentos gerados em execução devem ter destinos apropriados e documentados.

Apresente também um plano de reversão para restaurar a estrutura anterior se algum script deixar de funcionar.

**Não execute a migração até que eu aprove expressamente o plano.**

---

## 5. DESENVOLVIMENTO INDEPENDENTE DA VERSÃO 4
Depois que a reorganização for aprovada e concluída, desenvolva a v4 dentro de `versao_4/`.

A v4 deverá ser uma aplicação independente, com seu próprio ponto de entrada, configurações, dependências, documentação, logs e testes.

Não modifique os pontos de entrada da v1, v2 ou v3 para implementar funcionalidades da v4.

Utilize a versão 3 como referência funcional para compreender as regras de organização já existentes, mas não a transforme no código da v4 por meio de alterações diretas.

Antes de reaproveitar qualquer função, verifique se ela pode ser copiada ou adaptada de forma independente.

Documente a origem das regras reaproveitadas.

A v4 deverá preservar as regras de organização que forem relevantes, incluindo o tratamento de arquivos de assinatura digital existente na v3, após confirmar seu comportamento real no código.

---

## 6. OBJETIVOS FUNCIONAIS DA VERSÃO 4
A v4 deve manter a organização de documentos e acrescentar:

1. Indexação de arquivos existentes.
2. Banco de dados SQLite.
3. Cadastro e identificação de clientes.
4. Extração de dados de PDFs e imagens.
5. Pesquisa por cliente, tipo de documento, número de processo e data.
6. Abertura de pastas e arquivos pelo Windows Explorer.
7. Atualização do índice após movimentações.
8. Detecção de arquivos renomeados ou removidos manualmente.
9. Histórico de operações.
10. Recuperação de falhas.
11. OCR e interpretação com modelos locais, de forma opcional.
12. Documentação e testes específicos da v4.
A aplicação deve continuar utilizando o sistema de arquivos como armazenamento principal.

O SQLite será um índice dos documentos e clientes. Não deverá substituir o OneDrive nem exigir que os PDFs sejam armazenados dentro do banco.

---

## 7. ARQUITETURA DO SQLITE
Utilize o módulo padrão `sqlite3` do Python.

Não instale um servidor de banco de dados.

O banco deverá ficar em uma pasta local estável, fora da pasta sincronizada pelo OneDrive.

Permita configurar o caminho do banco com:

`CETTI_DB_PATH`

Permita configurar a raiz de documentos com:

`CETTI_ROOT`

O local do banco não deve ser confundido com a raiz dos documentos.

Crie as tabelas necessárias para:

- Clientes.
- Documentos.
- Histórico de operações.
Implemente chaves estrangeiras, índices, consultas parametrizadas e evolução de esquema.

Armazene apenas os dados necessários para localizar, classificar e organizar documentos.

Não utilize CPF como nome da pasta do cliente.

Utilize identificadores internos estáveis e trate nomes semelhantes como uma possível ambiguidade.

A criação do banco e a indexação inicial não podem mover, renomear ou excluir documentos.

---

## 8. INDEXAÇÃO DOS DOCUMENTOS EXISTENTES
Implemente um indexador que percorra a raiz configurada e registre os arquivos existentes.

Ele deverá:

- Registrar caminhos relativos.
- Identificar nomes e extensões.
- Evitar duplicações.
- Detectar arquivos modificados.
- Detectar arquivos removidos.
- Ignorar o próprio banco de dados.
- Ignorar ambientes virtuais, caches e diretórios técnicos.
- Tratar arquivos temporários do Office e do OneDrive.
- Evitar seguir links simbólicos para fora da raiz.
- Apresentar um resumo da indexação.
A primeira execução deve ser somente de leitura em relação aos documentos.

Não mova arquivos durante a indexação.

---

## 9. PESQUISA E WINDOWS EXPLORER
A interface principal de arquivos do cliente continuará sendo o Windows Explorer.

A v4 deve permitir pesquisar por comandos como:

- "Encontre a petição inicial do José da Silva."
- "Localize o contrato da Maria."
- "Mostre os documentos do processo 1234567."
- "Encontre documentos de outubro de 2026."
A interpretação inicial poderá utilizar regras determinísticas, sem depender de IA.

Se houver resultados ambíguos, apresente as opções e solicite uma escolha.

Depois que o usuário selecionar um resultado, permita:

- Abrir a pasta do cliente.
- Abrir a pasta que contém o documento.
- Selecionar o arquivo no Explorer.
- Abrir o documento diretamente.
Valide os caminhos e não permita acesso a arquivos fora da raiz autorizada.

A pesquisa deverá funcionar mesmo que os modelos de IA não estejam instalados.

---

## 10. EXTRAÇÃO DE TEXTO E MODELOS LOCAIS
O ambiente de destino possui aproximadamente 8 GB de RAM e não tem GPU dedicada.

Todo o processamento dos documentos deve ocorrer localmente.

Não envie documentos para APIs externas.

Utilize PyMuPDF para extrair texto nativo de PDFs.

Para documentos digitalizados, utilize OCR local.

A integração com modelos de IA deverá ser opcional.

Modelos inicialmente previstos para avaliação:

- OCR: `glm-ocr`.
- Interpretação de texto: `qwen3:4b`.
A integração ocorrerá pelo Ollama local.

Não baixe modelos automaticamente durante a inicialização.

Não execute os modelos simultaneamente por padrão.

Se o Ollama não estiver disponível, o organizador e a pesquisa básica deverão continuar funcionando.

Valide as respostas antes de utilizar dados extraídos para classificar ou movimentar arquivos.

Não invente informações ausentes.

Registre a origem e a página de cada dado quando possível.

Encaminhe casos ambíguos para revisão humana.

---

## 11. ISOLAMENTO DE CONFIGURAÇÕES E LOGS
Cada versão deve possuir seus próprios scripts de inicialização, documentação e configuração de execução.

Os logs de cada versão devem ser separados.

Não reutilize automaticamente caminhos de logs, bancos de dados ou configurações entre versões.

As versões antigas devem manter os comportamentos necessários para continuar funcionando.

A v4 deverá ter suas próprias configurações, banco SQLite, logs e testes.

Não coloque o banco SQLite dentro da pasta sincronizada do OneDrive.

Não armazene documentos reais de clientes dentro da pasta do código-fonte.

---

## 12. TESTES E CRITÉRIOS DE ACEITAÇÃO
Utilize arquivos fictícios e diretórios temporários nos testes.

Não mova arquivos reais do cliente durante os testes automatizados.

Teste:

- Inicialização independente de cada versão.
- Resolução de imports após a reorganização.
- Funcionamento dos BATs e scripts PowerShell.
- Criação e reabertura do banco SQLite.
- Indexação inicial sem movimentações.
- Reexecução sem duplicação.
- Pesquisa por nome, tipo e número de processo.
- Clientes com nomes semelhantes.
- Arquivos renomeados ou removidos manualmente.
- Atualização de caminhos.
- Falhas durante movimentações.
- Caminhos com acentos e espaços.
- Tentativas de acessar caminhos fora da raiz autorizada.
- Ausência do Ollama.
- Ausência dos modelos de IA.
- Falhas de OCR.
- Preservação das regras de organização da v3.
Não afirme que os testes passaram sem executá-los.

Documente os testes que não puderam ser executados.

---

## 13. ETAPAS OBRIGATÓRIAS DE TRABALHO

### ETAPA 1 — INSPEÇÃO DO REPOSITÓRIO
Não modifique nenhum arquivo.

Entregue:

1. Inventário dos arquivos.
2. Dependências reais da v1.
3. Dependências reais da v2.
4. Dependências reais da v3.
5. Identificação dos arquivos compartilhados.
6. Identificação dos BATs, PowerShell, logs e documentação relacionados a cada versão.
7. Proposta de estrutura final.
8. Plano de migração.
9. Riscos e plano de reversão.
Aguarde minha aprovação.

### ETAPA 2 — REORGANIZAÇÃO DO REPOSITÓRIO
Execute somente depois da minha aprovação.

Organize os arquivos em suas respectivas pastas.

Atualize referências, imports, scripts e documentação.

Não modifique a lógica de negócio das versões antigas desnecessariamente.

Teste cada versão após a reorganização.

Não exclua os arquivos originais até que a migração tenha sido validada e exista uma forma de reversão.

### ETAPA 3 — IMPLEMENTAÇÃO DA V4: SQLITE E INDEXAÇÃO
Implemente o banco e o indexador.

Teste com arquivos fictícios.

Não mova documentos reais.

### ETAPA 4 — PESQUISA E WINDOWS EXPLORER
Implemente a pesquisa e a abertura de pastas e arquivos.

Teste com diretórios temporários.

### ETAPA 5 — INTEGRAÇÃO COM A ORGANIZAÇÃO AUTOMÁTICA
Integre a atualização do índice com as movimentações da v4.

Implemente recuperação de falhas e evite sobrescritas.

### ETAPA 6 — EXTRAÇÃO E IA LOCAL
Implemente extração de texto, OCR e integração opcional com Ollama.

### ETAPA 7 — DOCUMENTAÇÃO E VALIDAÇÃO FINAL
Documente a estrutura do repositório, instalação, configuração, uso, testes e recuperação.

Confirme a independência entre as versões.

---

## 14. FORMATO DAS RESPOSTAS
Ao final de cada etapa, apresente:

- Arquivos analisados.
- Arquivos criados ou modificados.
- Decisões técnicas.
- Testes efetivamente executados.
- Resultados dos testes.
- Dependências necessárias.
- Riscos pendentes.
- Próximos passos.
Não execute várias etapas de uma vez.

Não antecipe modificações que dependam de aprovação.

Não remova funcionalidades existentes sem autorização.

## INSTRUÇÃO INICIAL
Comece agora exclusivamente pela ETAPA 1.

Inspecione o repositório real, identifique as dependências de cada versão e proponha a estrutura final com o plano de migração.

**Não crie, mova, renomeie, exclua nem modifique nenhum arquivo nesta primeira etapa. Aguarde minha aprovação expressa antes de prosseguir.**
