from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from cetti_busca import open_containing_folder, open_document, search_documents, select_in_explorer
from cetti_db import CettiDatabase
from cetti_extracao import extract_pdf
from cetti_indexador import default_root, index_documents, resolve_config


def configurar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ponto de entrada do Arquivista Digital da Cetti v4."
    )
    parser.add_argument(
        "--root",
        help="Pasta de documentos. Se omitida, usa CETTI_ROOT ou a pasta Documentos padrão.",
    )
    parser.add_argument(
        "--database",
        help="Caminho do SQLite. Se omitido, usa CETTI_DB_PATH ou o padrão do sistema.",
    )
    subparsers = parser.add_subparsers(dest="comando", required=True)

    subparsers.add_parser("index", help="Indexa/atualiza os arquivos sem movê-los.")

    busca = subparsers.add_parser("search", help="Pesquisa documentos já indexados.")
    busca.add_argument("consulta", help='Consulta, por exemplo: "petição do José"')

    extrair = subparsers.add_parser("extract", help="Extrai texto de um PDF.")
    extrair.add_argument("arquivo", help="Caminho completo do PDF.")
    extrair.add_argument(
        "--ocr",
        choices=("auto", "tesseract", "glm-ocr", "off"),
        default="auto",
        help="Mecanismo de OCR. Padrão: auto (Tesseract e, se habilitado, fallback Ollama).",
    )
    extrair.add_argument(
        "--ollama",
        action="store_true",
        help="Permite usar o Ollama como fallback quando --ocr auto ou glm-ocr for usado.",
    )

    subparsers.add_parser("status", help="Mostra os caminhos e o resumo do índice.")
    subparsers.add_parser("ui", help="Abre o painel Streamlit local.")

    return parser


def executar_indexacao(root: str | None, database: str | None) -> int:
    config = resolve_config(root, database)
    print(f"Raiz de documentos: {config.root}")
    print(f"Banco SQLite:       {config.database}")
    print("Indexando arquivos. Nenhum arquivo será movido...")
    resumo = index_documents(config.root, config.database)
    for chave, valor in resumo.as_dict().items():
        print(f"{chave}: {valor}")
    return 0


def executar_busca(consulta: str, root: str | None, database: str | None) -> int:
    config = resolve_config(root, database)
    resultados = search_documents(consulta, config.root, config.database)
    if not resultados:
        print("Nenhum resultado. Verifique a consulta ou execute 'index' primeiro.")
        return 0

    print(f"Resultados encontrados: {len(resultados)}")
    for numero, resultado in enumerate(resultados, start=1):
        print(f"\n{numero}. {resultado.file_name}")
        print(f"   Cliente: {resultado.client_name or 'Não identificado'}")
        print(f"   Tipo: {resultado.document_type or 'Não identificado'}")
        print(f"   Processo: {resultado.process_number or 'Não identificado'}")
        print(f"   Caminho: {resultado.path}")

    resposta = input("\nDigite o número para abrir a pasta (ou Enter para sair): ").strip()
    if resposta.isdigit() and 1 <= int(resposta) <= len(resultados):
        open_containing_folder(resultados[int(resposta) - 1].path, config.root)
    return 0


def executar_extracao(arquivo: str, modo_ocr: str, usar_ollama: bool) -> int:
    caminho = Path(arquivo).expanduser().resolve()
    cliente_ollama = None
    if usar_ollama or modo_ocr == "glm-ocr":
        try:
            from cetti_ia_local import OllamaClient
            cliente_ollama = OllamaClient()
            if not cliente_ollama.is_available():
                print("Aviso: Ollama não está disponível. Verifique se o serviço está iniciado.")
                return 2
        except Exception as erro:
            print(f"Não foi possível inicializar o Ollama: {erro}")
            return 2

    try:
        resultado = extract_pdf(
            caminho,
            use_ocr=(modo_ocr != "off"),
            ocr_backend=modo_ocr,
            ollama_client=cliente_ollama,
        )
    except Exception as erro:
        print(f"Falha na extração: {erro}")
        return 1

    print(f"Arquivo: {resultado.path}")
    print(f"Texto encontrado: {'sim' if resultado.has_text else 'não'}")
    for pagina in resultado.pages:
        confianca = (
            f", confiança {pagina.confidence:.1f}%"
            if pagina.confidence is not None
            else ""
        )
        print(f"Página {pagina.page}: método={pagina.method}{confianca}")
    if resultado.review_required:
        print("ATENÇÃO: o resultado exige revisão humana.")
        for motivo in resultado.review_reasons:
            print(f"- {motivo}")
    print("\n" + "=" * 60 + "\n")
    print(resultado.text or "(Nenhum texto foi extraído.)")
    return 0


def executar_status(root: str | None, database: str | None) -> int:
    config = resolve_config(root, database)
    with CettiDatabase(config.database) as db:
        total = db.conn.execute(
            "SELECT COUNT(*) FROM documents WHERE status = 'active'"
        ).fetchone()[0]
        clientes = db.conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    print(f"Raiz: {config.root}")
    print(f"Banco: {config.database}")
    print(f"Documentos ativos indexados: {total}")
    print(f"Clientes registrados no índice: {clientes}")
    return 0


def executar_interface() -> int:
    projeto = Path(__file__).resolve().parent
    app = projeto / "app_streamlit_v4.py"
    if not app.is_file():
        print(f"Não encontrei a interface: {app}")
        return 1
    comando = [
        sys.executable, "-m", "streamlit", "run", str(app),
        "--server.address", "127.0.0.1",
    ]
    try:
        return subprocess.call(comando, cwd=str(projeto))
    except FileNotFoundError:
        print("Streamlit não está instalado neste ambiente.")
        print("Instale com: python -m pip install streamlit")
        return 1


def main() -> int:
    parser = configurar_parser()
    args = parser.parse_args()

    try:
        if args.comando == "index":
            return executar_indexacao(args.root, args.database)
        if args.comando == "search":
            return executar_busca(args.consulta, args.root, args.database)
        if args.comando == "extract":
            return executar_extracao(args.arquivo, args.ocr, args.ollama)
        if args.comando == "status":
            return executar_status(args.root, args.database)
        if args.comando == "ui":
            return executar_interface()
    except (ValueError, OSError, RuntimeError) as erro:
        print(f"Erro: {erro}")
        return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
