# Cloudflare Tunnel para o Arquivista Digital Inteligente da Cetti

Este projeto usa um túnel dedicado para publicar apenas o Streamlit do cliente. A ideia é não mexer no túnel de outros projetos e não expor porta pública do Windows.
O hostname publica o painel do Arquivista Digital Inteligente da Cetti para acesso no celular do cliente.

## Modelo de configuração

O setup cria um arquivo separado em:

```text
C:\Users\<usuario>\.cloudflared\cetti-saas-config.yml
```

Exemplo equivalente:

```yaml
tunnel: cetti-saas
credentials-file: C:\Users\<usuario>\.cloudflared\<tunnel-id>.json

ingress:
  - hostname: streamlit.cetti.me
    service: http://localhost:8501
  - service: http_status:404
```

## Como funciona

- `tunnel`: nome do túnel usado pelo cloudflared.
- `credentials-file`: credencial local criada no login ou na criação do túnel.
- `hostname`: endereço público que o cliente abre no celular.
- `service`: endereço local do Streamlit.

## Regras importantes

- O Streamlit deve rodar em `127.0.0.1:8501` ou `localhost:8501`.
- O tunnel publica apenas a interface web.
- O acesso no celular depende do PC estar ligado e com internet.

## Segurança

Se o hostname ficar público, proteja com Cloudflare Access.

Recomendação mínima:

1. Criar uma aplicação no Cloudflare Zero Trust.
2. Restringir o acesso por email ou autenticação de dois fatores.
3. Nunca expor o hostname sem alguma camada de acesso.
