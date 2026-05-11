import streamlit as st
import mimetypes
import os

from cetti_core import (
    abrir_local,
    buscar_documentos,
    garantir_estrutura,
    obter_raiz,
    resolver_cliente_e_tipo,
    resumo_caminho,
)
from cetti_interaction import ler_pedido_pendente, responder_pedido
from cetti_logging import ler_logs_recentes


st.set_page_config(
    page_title="Arquivista Digital Inteligente da Cetti",
    page_icon="📁",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
    <style>
        .stApp {
            background: linear-gradient(135deg, #f4efe8 0%, #fffaf4 38%, #eef6f1 100%);
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #102a43 0%, #16324f 100%);
            color: #f8fafc;
        }
        [data-testid="stSidebar"] * {
            color: #f8fafc;
        }
        .hero {
            padding: 1.25rem 1.4rem;
            border-radius: 1.4rem;
            background: rgba(255, 255, 255, 0.68);
            border: 1px solid rgba(16, 42, 67, 0.08);
            box-shadow: 0 16px 40px rgba(16, 42, 67, 0.08);
        }
        .result-card {
            padding: 0.9rem 1rem;
            border-radius: 1rem;
            background: rgba(255, 255, 255, 0.88);
            border: 1px solid rgba(16, 42, 67, 0.08);
            margin-bottom: 0.75rem;
        }
        .stChatMessage {
            background-color: rgba(240, 242, 246, 0.5) !important;
        }
        .stChatMessage p {
            color: #1a1a1a !important;
        }
        [role="status"] p {
            color: #1a1a1a !important;
        }
        [data-testid="stTextInput"] input {
            color: #1a1a1a !important;
            background: white !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


if "mensagens" not in st.session_state:
    st.session_state.mensagens = [
        {"role": "assistant", "content": "Digite algo como: onde está a petição inicial do José Fagundes?"}
    ]

if "logs_vistos" not in st.session_state:
    st.session_state.logs_vistos = set()

if "pedidos_vistos" not in st.session_state:
    st.session_state.pedidos_vistos = set()


def detectar_acesso_mobile() -> tuple[bool, str]:
    user_agent = ""
    try:
        headers = st.context.headers
        user_agent = headers.get("User-Agent") or headers.get("user-agent") or ""
    except Exception:
        user_agent = ""

    ua = user_agent.lower()
    mobile = any(token in ua for token in ("android", "iphone", "ipad", "mobile"))
    return mobile, user_agent


def host_requisicao() -> str:
    try:
        headers = st.context.headers
        host = headers.get("X-Forwarded-Host") or headers.get("x-forwarded-host") or headers.get("Host") or headers.get("host") or ""
        host = host.split(",")[0].strip().split(":")[0].lower()
        return host
    except Exception:
        return ""


def hosts_remotos_configurados() -> set[str]:
    bruto = os.getenv("STREAMLIT_REMOTE_HOSTS", "streamlit.cetti.me")
    itens = bruto.replace(";", ",").split(",")
    return {item.strip().lower() for item in itens if item.strip()}


def mime_do_arquivo(caminho):
    mime, _ = mimetypes.guess_type(str(caminho))
    return mime or "application/octet-stream"


@st.fragment(run_every="1s")
def feed_ao_vivo():
    logs = ler_logs_recentes(quantidade=20)
    for log in logs:
        if log not in st.session_state.logs_vistos:
            st.session_state.logs_vistos.add(log)
            st.session_state.mensagens.append({"role": "assistant", "content": f"📋 {log}"})

    pedido = ler_pedido_pendente()
    if pedido and pedido.get("status") in {"pending", "answered"}:
        pedido_id = pedido.get("id")
        if pedido_id and pedido_id not in st.session_state.pedidos_vistos:
            st.session_state.pedidos_vistos.add(pedido_id)
            prompt = pedido.get("prompt") or f"Qual é o cliente deste documento? {pedido.get('arquivo', '')}"
            st.session_state.mensagens.append({
                "role": "assistant",
                "content": f"❓ {prompt}",
            })

        if pedido.get("status") == "pending" and pedido_id:
            st.markdown("### Responder cliente pendente")
            st.write(f"Arquivo: {pedido.get('arquivo', 'desconhecido')}")
            nome_cliente = st.text_input(
                "Qual é o cliente deste documento?",
                key=f"cliente_pendente_{pedido_id}",
                placeholder="Digite o nome do cliente",
            )
            if st.button("Enviar cliente", key=f"enviar_cliente_{pedido_id}"):
                if nome_cliente.strip():
                    if responder_pedido(pedido_id, nome_cliente.strip()):
                        st.session_state.mensagens.append(
                            {"role": "assistant", "content": f"✅ Cliente informado: {nome_cliente.strip()}"}
                        )
                        st.rerun()
                else:
                    st.warning("Informe um nome de cliente antes de enviar.")

    for mensagem in st.session_state.mensagens:
        with st.chat_message(mensagem["role"]):
            st.write(mensagem["content"])


def executar_busca(pergunta: str) -> dict:
    raiz = obter_raiz()
    if raiz is None:
        return {"erro": "Defina CAMINHO_RAIZ_DRIVE no arquivo .env antes de usar a busca."}

    termo = pergunta.lower()
    termo = termo.replace("buscar", "").replace("onde está", "").replace("onde", "").strip()
    if not termo:
        return {"erro": "Escreva o nome do cliente, documento ou parte do caminho."}

    resultados = buscar_documentos(termo, raiz)
    pasta_cliente, pasta_tipo = resolver_cliente_e_tipo(termo, raiz)
    return {"termo": termo, "resultados": resultados, "pasta_cliente": pasta_cliente, "pasta_tipo": pasta_tipo, "raiz": raiz}


st.sidebar.title("Arquivista Digital Inteligente da Cetti")
st.sidebar.write("Triagem inteligente e busca ativa em Google Drive.")
st.sidebar.markdown(
    """
    <div style="padding:0.9rem 1rem; border-radius:1rem; background:rgba(255,255,255,0.12); line-height:1.45;">
    é um agente operacional especializado na gestão documental jurídica que atua como uma sentinela de alta precisão,
    monitorando pastas do Google Drive em tempo real para realizar a triagem automática de documentos através da inteligência artificial.
    Sem a necessidade de bancos de dados complexos, ele lê o conteúdo dos PDFs, identifica clientes e tipos de petição, e organiza fluxos
    de trabalho entre arquivos originais e assinados, permitindo que o advogado localize qualquer documento instantaneamente e abra a pasta
    correspondente pelo celular, eliminando gargalos operacionais e garantindo uma organização impecável com baixo custo de manutenção.
    </div>
    """,
    unsafe_allow_html=True,
)

acesso_mobile, _user_agent = detectar_acesso_mobile()
host_atual = host_requisicao()
hosts_remotos = hosts_remotos_configurados()
forcar_remoto_por_host = bool(host_atual and host_atual in hosts_remotos)

opcoes_modo = ["PC (abre Explorer)", "Celular/remoto (somente listar e baixar)"]
modo_padrao = opcoes_modo[1] if acesso_mobile else opcoes_modo[0]

if "modo_abertura" not in st.session_state:
    st.session_state.modo_abertura = modo_padrao

if forcar_remoto_por_host:
    st.session_state.modo_abertura = opcoes_modo[1]
    st.sidebar.warning(f"Modo remoto forçado para host público: {host_atual}")
    st.sidebar.caption(
        "Configuração via .env: STREAMLIT_REMOTE_HOSTS="
        + ", ".join(sorted(hosts_remotos))
    )
else:
    st.session_state.modo_abertura = st.sidebar.radio(
        "Comportamento ao encontrar documentos",
        opcoes_modo,
        index=opcoes_modo.index(st.session_state.modo_abertura) if st.session_state.modo_abertura in opcoes_modo else opcoes_modo.index(modo_padrao),
    )

abrir_no_pc = st.session_state.modo_abertura == opcoes_modo[0]

if not abrir_no_pc:
    st.sidebar.info("Modo remoto ativo: o sistema não abre janelas no servidor; ele mostra caminhos e downloads.")

raiz = obter_raiz()
if raiz is None:
    st.sidebar.error("CAMINHO_RAIZ_DRIVE não configurado")
else:
    pastas = garantir_estrutura(raiz)
    st.sidebar.success("Base conectada")
    st.sidebar.caption(f"Raiz: {raiz}")
    st.sidebar.caption(f"Entrada: {pastas['entrada']}")
    st.sidebar.caption(f"Não protocolado: {pastas['nao_protocolado']}")
    st.sidebar.caption(f"Protocolado: {pastas['protocolado']}")


st.markdown(
    """
    <div class="hero">
        <h1 style="margin:0 0 0.35rem 0; color:#102a43;">Arquivista Digital Inteligente da Cetti</h1>
        <p style="margin:0; color:#334e68; font-size:1.02rem;">
            Agente operacional para triagem documental jurídica, busca instantânea e abertura da pasta correta no celular ou no PC.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


feed_ao_vivo()


entrada = st.chat_input("Busque por cliente, documento ou termo do arquivo")

if entrada:
    st.session_state.mensagens.append({"role": "user", "content": entrada})
    resultado = executar_busca(entrada)

    if "erro" in resultado:
        resposta = resultado["erro"]
    else:
        arquivos = resultado["resultados"]
        termo = resultado["termo"]
        pasta_cliente = resultado.get("pasta_cliente")
        pasta_tipo = resultado.get("pasta_tipo")
        if pasta_tipo:
            nome_cliente = pasta_tipo.parent.name
            if abrir_no_pc:
                resposta = f"Encontrei a pasta de '{pasta_tipo.name}' para {nome_cliente}. Abrindo a pasta do tipo."
                abrir_local(pasta_tipo)
            else:
                resposta = f"Encontrei a pasta de '{pasta_tipo.name}' para {nome_cliente}. Vou listar os arquivos para acesso no celular."
        elif pasta_cliente:
            nome_cliente = pasta_cliente.name
            if abrir_no_pc:
                resposta = f"Encontrei a cliente '{nome_cliente}'. Abrindo a pasta da cliente."
                abrir_local(pasta_cliente)
            else:
                resposta = f"Encontrei a cliente '{nome_cliente}'. Vou listar os arquivos para acesso no celular."
        else:
            if arquivos:
                resposta = f"Encontrei {len(arquivos)} arquivo(s) para '{termo}'."
            else:
                resposta = f"Não encontrei arquivos para '{termo}'."

    st.session_state.mensagens.append({"role": "assistant", "content": resposta})
    st.rerun()


if st.session_state.mensagens and st.session_state.mensagens[-1]["role"] == "assistant":
    ultimo = st.session_state.mensagens[-1]["content"]
    if ultimo.startswith("Encontrei") and raiz is not None and len(st.session_state.mensagens) >= 2:
        termo_ativo = st.session_state.mensagens[-2]["content"]
        busca = executar_busca(termo_ativo)
        arquivos = busca.get("resultados", [])
        pasta_cliente = busca.get("pasta_cliente")
        pasta_tipo = busca.get("pasta_tipo")

        if pasta_tipo:
            with st.container():
                st.markdown(
                    f"<div class='result-card'><strong>Tipo confirmado:</strong> {pasta_tipo.name} (Cliente: {pasta_tipo.parent.name})<br>{pasta_tipo}</div>",
                    unsafe_allow_html=True,
                )
                if abrir_no_pc:
                    st.caption("Pasta do tipo aberta automaticamente no Explorer.")
                else:
                    st.caption("Modo remoto: pasta identificada; use os downloads abaixo.")
        elif pasta_cliente:
            with st.container():
                st.markdown(
                    f"<div class='result-card'><strong>Cliente confirmado:</strong> {pasta_cliente.name}<br>{pasta_cliente}</div>",
                    unsafe_allow_html=True,
                )
                if abrir_no_pc:
                    st.caption("Pasta da cliente aberta automaticamente no Explorer.")
                else:
                    st.caption("Modo remoto: cliente identificado; use os downloads abaixo.")

        for indice, caminho in enumerate(arquivos, start=1):
            with st.container():
                st.markdown(
                    f"<div class='result-card'><strong>{indice}. {resumo_caminho(caminho, raiz)}</strong><br>{caminho.parent}</div>",
                    unsafe_allow_html=True,
                )
                coluna_abrir_pasta, coluna_abrir_arquivo, coluna_download = st.columns(3)
                with coluna_abrir_pasta:
                    if st.button("Abrir pasta", key=f"pasta_{indice}_{caminho}", disabled=not abrir_no_pc):
                        abrir_local(caminho.parent)
                        st.toast("Pasta aberta no Explorer")
                with coluna_abrir_arquivo:
                    if st.button("Abrir arquivo", key=f"arquivo_{indice}_{caminho}", disabled=not abrir_no_pc):
                        abrir_local(caminho)
                        st.toast("Arquivo aberto no sistema")
                with coluna_download:
                    try:
                        st.download_button(
                            "Baixar",
                            data=caminho.read_bytes(),
                            file_name=caminho.name,
                            mime=mime_do_arquivo(caminho),
                            key=f"download_{indice}_{caminho}",
                        )
                    except Exception:
                        st.caption("Download indisponível")
