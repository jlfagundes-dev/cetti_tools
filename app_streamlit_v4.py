from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from cetti_busca import open_containing_folder, open_document, search_documents, select_in_explorer
from cetti_db import CettiDatabase
from cetti_extracao import extract_pdf
from cetti_indexador import default_root, index_documents, resolve_config
from cetti_organizacao import organize_documents


st.set_page_config(
    page_title="Arquivista Digital da Cetti v4",
    page_icon="📁",
    layout="wide",
)

st.title("📁 Arquivista Digital da Cetti")
st.caption("Versão 4 · execução local · arquivos permanecem nas pastas do cliente")

with st.sidebar:
    st.header("Configuração")
    raiz_padrao = str(default_root())
    raiz_texto = st.text_input(
        "Pasta principal de documentos",
        value=os.getenv("CETTI_ROOT", raiz_padrao),
        help="Pode ser uma pasta local ou sincronizada pelo OneDrive.",
    )

    banco_padrao = str(CettiDatabase().path)
    banco_texto = st.text_input(
        "Caminho do banco SQLite",
        value=os.getenv("CETTI_DB_PATH", banco_padrao),
        help="Mantenha o banco fora da pasta de documentos e, preferencialmente, fora do OneDrive.",
    )

    st.info("O painel deve ser usado localmente. Não publique documentos jurídicos na internet.")


def obter_config():
    return resolve_config(raiz_texto.strip(), banco_texto.strip())


def mostrar_status(config):
    with CettiDatabase(config.database) as db:
        total = db.conn.execute(
            "SELECT COUNT(*) FROM documents WHERE status = 'active'"
        ).fetchone()[0]
        clientes = db.conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Documentos indexados", total)
    c2.metric("Clientes no índice", clientes)
    c3.metric("Banco SQLite", "Disponível")


try:
    config = obter_config()
except Exception as erro:
    st.error(f"Configuração inválida: {erro}")
    st.stop()

st.write(f"**Pasta de documentos:** `{config.root}`")
st.write(f"**Banco local:** `{config.database}`")

tab_busca, tab_organizacao, tab_extracao = st.tabs(
    ["🔎 Pesquisar documentos", "📂 Ler e organizar documentos", "📄 Extrair texto de PDF"]
)

with tab_busca:
    st.subheader("Pesquisa")
    consulta = st.text_input(
        "O que você procura?",
        placeholder="Ex.: petição do José, contrato, processo 1234567",
        key="consulta_documentos",
    )
    if st.button("Pesquisar", type="primary", key="botao_pesquisar"):
        if not consulta.strip():
            st.warning("Digite o nome do cliente ou informações do documento.")
        else:
            try:
                st.session_state["cetti_resultados"] = search_documents(
                    consulta.strip(), config.root, config.database
                )
                st.session_state["cetti_consulta"] = consulta.strip()
            except Exception as erro:
                st.error(f"Falha na pesquisa: {erro}")

    resultados = st.session_state.get("cetti_resultados", [])
    if resultados:
        st.success(f"{len(resultados)} resultado(s) para: {st.session_state.get('cetti_consulta', '')}")
        opcoes = {
            f"{r.file_name} | cliente: {r.client_name or 'não identificado'} | {r.path}": r
            for r in resultados
        }
        rotulo_selecionado = st.selectbox("Selecione um documento", list(opcoes.keys()))
        selecionado = opcoes[rotulo_selecionado]

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Abrir arquivo", key="abrir_arquivo"):
                try:
                    open_document(selecionado.path, config.root)
                    st.success("Solicitação enviada ao sistema operacional.")
                except Exception as erro:
                    st.error(f"Não foi possível abrir o arquivo: {erro}")
        with col2:
            if st.button("Abrir pasta", key="abrir_pasta"):
                try:
                    open_containing_folder(selecionado.path, config.root)
                    st.success("Solicitação enviada ao sistema operacional.")
                except Exception as erro:
                    st.error(f"Não foi possível abrir a pasta: {erro}")
        with col3:
            if st.button("Mostrar no Explorer", key="selecionar_explorer"):
                try:
                    select_in_explorer(selecionado.path, config.root)
                    st.success("Solicitação enviada ao sistema operacional.")
                except Exception as erro:
                    st.error(f"Não foi possível localizar o arquivo: {erro}")

        st.write("**Detalhes do documento selecionado**")
        st.write(f"- Cliente: {selecionado.client_name or 'Não identificado'}")
        st.write(f"- Tipo: {selecionado.document_type or 'Não identificado'}")
        st.write(f"- Número do processo: {selecionado.process_number or 'Não identificado'}")
        st.write(f"- Data do documento: {selecionado.document_date or 'Não identificada'}")
        st.code(str(selecionado.path))
    elif "cetti_resultados" in st.session_state:
        st.info("Nenhum resultado encontrado. Se os documentos ainda não foram indexados, use a aba 'Atualizar índice'.")

with tab_organizacao:
    st.subheader("Ler e organizar documentos")
    st.write(
            "Clique uma vez para validar os arquivos da pasta de entrada, analisar PDFs, "
            "organizar documentos e atualizar a pesquisa. Arquivos já organizados não são reprocessados."
    )
    usar_ocr_organizacao = st.checkbox(
            "Usar OCR em PDFs digitalizados",
            value=True,
            help="Requer Tesseract instalado e disponível no PATH.",
    )
    usar_ollama_organizacao = st.checkbox(
            "Iniciar Ollama durante a rotina para OCR",
            value=True,
            help="A aplicação inicia o Ollama se necessário e o encerra ao final.",
    )
    if st.button("Ler pasta e organizar automaticamente", type="primary", key="organizar_documentos"):
        progresso = st.empty()
        barra = st.progress(0)
        try:
            cliente_ollama = None
            mensagens: list[str] = []

            def atualizar_progresso(mensagem: str) -> None:
                mensagens.append(mensagem)
                historico = "\n".join(f"- {item}" for item in mensagens[-12:])
                progresso.markdown(
                    f"**Arquivo/etapa atual:** {mensagem}\n\n"
                    f"**Últimas atualizações:**\n{historico}"
                )
                barra.progress(min(0.99, len(mensagens) / max(len(mensagens) + 1, 1)))

            with st.spinner("Executando validação, análise e organização..."):
                if usar_ollama_organizacao:
                    from cetti_ia_local import temporary_ollama

                    with temporary_ollama(allow_unavailable=True) as cliente_ollama:
                        if cliente_ollama is None:
                            atualizar_progresso(
                                "Ollama indisponível; continuando sem Ollama."
                            )
                        else:
                            atualizar_progresso(
                                "Ollama pronto para a rotina; será desligado ao finalizar."
                            )
                        resumo = organize_documents(
                            config.root,
                            config.database,
                            progress=atualizar_progresso,
                            use_ocr=usar_ocr_organizacao,
                            ollama_client=cliente_ollama,
                        )
                else:
                    resumo = organize_documents(
                        config.root,
                        config.database,
                        progress=atualizar_progresso,
                        use_ocr=usar_ocr_organizacao,
                        ollama_client=cliente_ollama,
                    )
            barra.progress(1.0)
            st.success("Varredura e organização concluídas.")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Analisados", resumo.pdfs_analyzed)
            c2.metric("Movidos", resumo.moved)
            c3.metric("Identificados", resumo.identified)
            c4.metric("Com erro", resumo.errors)
            st.json(resumo.as_dict())
            if resumo.file_statuses:
                with st.expander("Resultado de cada arquivo", expanded=True):
                    for status in resumo.file_statuses:
                        st.write(f"- {status}")
            if resumo.diagnostics:
                with st.expander("Diagnóstico detalhado: ferramentas e prompts", expanded=False):
                    for diagnostic in resumo.diagnostics:
                        st.code(diagnostic)
            if resumo.errors:
                st.warning("Alguns arquivos foram mantidos na entrada por exigirem revisão.")
                for mensagem in resumo.messages or []:
                    st.write(f"- {mensagem}")
        except Exception as erro:
            st.error(f"Falha na organização: {erro}")

    if st.button("Ver estado atual do índice", key="estado_indice"):
        try:
            mostrar_status(config)
        except Exception as erro:
            st.error(f"Não foi possível consultar o índice: {erro}")

with tab_extracao:
    st.subheader("Extrair texto de um PDF")
    st.caption("A extração apenas lê o PDF; não organiza nem movimenta o arquivo.")
    caminho_pdf = st.text_input(
        "Caminho completo do PDF neste computador",
        placeholder=r"C:\Documentos\cliente\arquivo.pdf",
    )
    usar_ocr = st.checkbox("Usar OCR em páginas digitalizadas", value=True)
    usar_ollama = st.checkbox(
        "Permitir fallback para Ollama (glm-ocr) se o Tesseract falhar ou tiver baixa confiança",
        value=False,
        help="O Ollama precisa estar iniciado e o modelo glm-ocr já deve estar instalado.",
    )

    if st.button("Extrair texto", key="extrair_texto"):
        if not caminho_pdf.strip():
            st.warning("Informe o caminho completo do PDF.")
        else:
            try:
                cliente_ollama = None
                if usar_ollama:
                    from cetti_ia_local import OllamaClient
                    cliente_ollama = OllamaClient()
                    if not cliente_ollama.is_available():
                        st.error("O Ollama não está disponível. Inicie o Ollama e tente novamente.")
                        st.stop()

                with st.spinner("Extraindo texto..."):
                    resultado = extract_pdf(
                        Path(caminho_pdf.strip()),
                        use_ocr=usar_ocr,
                        ocr_backend="auto",
                        ollama_client=cliente_ollama,
                    )

                st.write(f"**Arquivo:** `{resultado.path}`")
                st.write(f"**Texto extraído:** {'Sim' if resultado.has_text else 'Não'}")
                if resultado.review_required:
                    st.warning("Este resultado precisa de revisão humana.")
                    for motivo in resultado.review_reasons:
                        st.write(f"- {motivo}")
                for pagina in resultado.pages:
                    confianca = (
                        f" · confiança Tesseract: {pagina.confidence:.1f}%"
                        if pagina.confidence is not None
                        else ""
                    )
                    st.caption(
                        f"Página {pagina.page} · método: {pagina.method}{confianca}"
                    )
                st.text_area(
                    "Texto extraído",
                    value=resultado.text,
                    height=360,
                    key="texto_extraido",
                )
            except Exception as erro:
                st.error(f"Falha na extração: {erro}")

st.divider()
st.caption("Cetti Agentics · A indexação não substitui os arquivos originais nem confirma automaticamente os dados extraídos.")
