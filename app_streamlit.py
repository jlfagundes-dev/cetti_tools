import streamlit as st
import time
from html import escape
from datetime import datetime
from pathlib import Path
import re

from cetti_core import obter_raiz
from cetti_logging import LOG_FILE


PDF_LOG_FILE = Path(__file__).parent / "cetti_pdf.log"


st.set_page_config(
    page_title="Arquivista Digital Cetti v3",
    page_icon="📁",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
    <style>
        .stApp { background: #182b35; color: #ffffff; }
        [data-testid="stSidebar"] { background: #182b35; }
        [data-testid="stSidebar"] * { color: #ffffff; }
        [data-testid="stAppViewContainer"] { background: #182b35; }
        [data-testid="stMain"] { background: #182b35; }
        [data-testid="stAppViewBlockContainer"] { background: #182b35; }
        [data-testid="stHeader"] { background: #182b35; }
        [data-testid="stToolbar"] { display: none; }
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
        h1, h2, h3, h4, h5, h6, p, label, span, div { color: #ffffff; }
        .hero {
            padding: 1.5rem 1.7rem;
            background: #182b35;
            color: #ffffff;
            border: 1px solid #3d5963;
            border-radius: 10px;
            margin-bottom: 1.25rem;
        }
        .hero h1 { margin: 0 0 0.35rem 0; color: #ffffff !important; }
        .hero p { margin: 0; color: #ffffff !important; }
        .notices-panel { max-height: 210px; overflow-y: auto; padding-right: 0.35rem; }
        .notice { padding: 0.85rem 1rem; border-left: 4px solid #f0a35b; background: #182b35; color: #ffffff !important; border-top: 1px solid #3d5963; border-right: 1px solid #3d5963; border-bottom: 1px solid #3d5963; margin-bottom: 0.6rem; }
        .log-panel { max-height: 260px; overflow-y: auto; padding: 0.25rem 0.35rem 0.25rem 0; }
        .log-line { padding: 0.45rem 0.7rem; border-bottom: 1px solid #3d5963; color: #ffffff !important; white-space: pre-wrap; }
        [data-testid="stMetric"] { background: #182b35; border: 1px solid #3d5963; border-radius: 8px; padding: 0.8rem 1rem; }
        [data-testid="stMetricLabel"] p, [data-testid="stMetricValue"], [data-testid="stMetricDelta"] { color: #ffffff !important; }
        [data-testid="stAlert"] { background: #182b35 !important; border: 1px solid #3d5963 !important; }
        [data-testid="stAlert"] *, [data-testid="stCaptionContainer"] * { color: #ffffff !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


def status_monitor() -> tuple[str, str]:
    if not LOG_FILE.exists():
        return "Aguardando", "Nenhum monitor iniciou nesta instalação."

    ultima_modificacao = LOG_FILE.stat().st_mtime
    idade_segundos = max(0, int(time.time() - ultima_modificacao))
    if idade_segundos <= 30:
        return "Ativo", f"Última atividade há {idade_segundos}s"
    return "Monitoramento", f"Última atividade há {idade_segundos // 60}min"


def resumo_operacional(raiz: Path | None) -> tuple[int, int, int]:
    if raiz is None or not raiz.exists():
        return 0, 0, 0
    entrada = raiz
    clientes = raiz / "01_CLIENTES"
    return (
        sum(1 for caminho in entrada.iterdir() if caminho.is_file()) if entrada.exists() else 0,
        sum(1 for caminho in clientes.rglob("*") if caminho.is_file()) if clientes.exists() else 0,
        sum(1 for caminho in clientes.iterdir() if caminho.is_dir()) if clientes.exists() else 0,
    )


def data_do_log(linha: str, indice: int, data_arquivo: datetime) -> datetime:
    correspondencia = re.search(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:,\d+)?", linha)
    if correspondencia:
        return datetime.strptime(
            f"{correspondencia.group(1)} {correspondencia.group(2)}", "%Y-%m-%d %H:%M:%S"
        )

    correspondencia = re.search(r"\[(\d{2}:\d{2}:\d{2})\]", linha)
    if correspondencia:
        hora = datetime.strptime(correspondencia.group(1), "%H:%M:%S").time()
        return datetime.combine(data_arquivo.date(), hora)

    return datetime.min.replace(microsecond=0) + (data_arquivo - data_arquivo.replace(hour=0, minute=0, second=0, microsecond=0)) * 0 + indice * datetime.resolution


def ler_log_completo(caminho: Path) -> list[str]:
    if not caminho.exists():
        return []
    linhas = [linha.strip() for linha in caminho.read_text(encoding="utf-8", errors="replace").splitlines() if linha.strip()]
    data_arquivo = datetime.fromtimestamp(caminho.stat().st_mtime)
    enumeradas = [(data_do_log(linha, indice, data_arquivo), indice, linha) for indice, linha in enumerate(linhas)]
    enumeradas.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [linha for _, _, linha in enumeradas]


def renderizar_log(titulo: str, linhas: list[str]) -> None:
    st.markdown(f"### {titulo}")
    if not linhas:
        st.info("Nenhum registro encontrado.")
        return
    conteudo = "<div class='log-panel'>"
    conteudo += "".join(f"<div class='log-line'>{escape(linha)}</div>" for linha in linhas)
    conteudo += "</div>"
    st.markdown(conteudo, unsafe_allow_html=True)


raiz = obter_raiz()
status, detalhe_status = status_monitor()
logs_monitor = ler_log_completo(LOG_FILE)
logs_pdf = ler_log_completo(PDF_LOG_FILE)
logs = logs_monitor
avisos = [linha for linha in logs if any(palavra in linha.lower() for palavra in ("warning", "error", "aviso", "aguardando", "duplicat", "erro"))]
entrada_count, documentos_clientes_count, clientes_count = resumo_operacional(raiz)

st.sidebar.title("Arquivista Digital Cetti v3")
st.sidebar.caption("Painel operacional do processamento local de PDFs.")
if raiz is None:
    st.sidebar.error("Pasta Documentos do Windows não localizada")
else:
    st.sidebar.success("Base conectada")
    st.sidebar.caption(str(raiz))

st.markdown(
    """
    <div class="hero">
        <h1>Arquivista Digital Cetti v3</h1>
        <p>Monitoramento operacional da organização automática de documentos PDF.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("### Estado do monitor")
col_status, col_entrada, col_nao, col_prot = st.columns(4)
with col_status:
    if status == "Ativo":
        st.success(f"{status}")
    else:
        st.warning(f"{status}")
    st.caption(detalhe_status)
with col_entrada:
    st.metric("Arquivos na entrada", entrada_count)
with col_nao:
    st.metric("Documentos em clientes", documentos_clientes_count)
with col_prot:
    st.metric("Clientes", clientes_count)

st.markdown("### Prompts e avisos")
if avisos:
    avisos_html = "<div class='notices-panel'>"
    avisos_html += "".join(f"<div class='notice'>{escape(aviso)}</div>" for aviso in avisos)
    avisos_html += "</div>"
    st.markdown(avisos_html, unsafe_allow_html=True)
else:
    st.success("Nenhum aviso pendente no monitor.")

renderizar_log("Monitor", logs_monitor)
renderizar_log("Processamento PDF", logs_pdf)

