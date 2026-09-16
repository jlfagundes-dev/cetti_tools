import os
import unicodedata
import subprocess
import sys
import ctypes
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

def obter_raiz() -> Path | None:
    """Retorna a pasta Documentos do usuário, inclusive no Windows localizado."""
    if os.name == "nt":
        caminho = ctypes.create_unicode_buffer(260)
        resultado = ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, caminho)
        if resultado == 0 and caminho.value:
            return Path(caminho.value)

    for nome in ("Documents", "Documentos"):
        caminho = Path.home() / nome
        if caminho.exists():
            return caminho
    return Path.home() / "Documents"


def garantir_estrutura(raiz: Path) -> dict[str, Path]:
    return {
        "entrada": raiz,
        "arquivos_word": raiz / "02_ARQUIVOS_DO_WORD",
        "clientes": raiz / "01_CLIENTES",
        "clientes_antigos": raiz / "CLIENTES",
        "nao_identificados": raiz / "00_ARQUIVOS_NAO_ORGANIZADOS_AUTOMATICAMENTE",
        # Mantidos para compatibilidade com a versão anterior baseada em status.
        "nao_protocolado": raiz / "01_Nao_Protocolado",
        "protocolado": raiz / "02_Protocolado",
    }


def normalizar_texto(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(caractere for caractere in texto if not unicodedata.combining(caractere))
    return " ".join(texto.lower().replace("_", " ").replace("-", " ").split())


def buscar_pastas_clientes(termo: str, raiz: Path | None = None) -> list[Path]:
    raiz = raiz or obter_raiz()
    if not raiz or not raiz.exists():
        return []
    termo_normalizado = normalizar_texto(termo)
    candidatos: list[tuple[int, Path]] = []

    # Stop words to ignore in natural language queries like 'tem oficio da evani'
    STOP_WORDS = {"tem", "documento", "documentos", "da", "do", "de", "dos", "das", "o", "a", "e", "que", "um", "uma", "por", "para", "com"}

    tokens_termo = [t for t in termo_normalizado.split() if t and t not in STOP_WORDS and len(t) > 1]

    for caminho in raiz.rglob("*"):
        if not caminho.is_dir():
            continue

        if caminho == raiz:
            continue

        nome = normalizar_texto(caminho.name)
        relativo = normalizar_texto(caminho.relative_to(raiz).as_posix())

        # Exact folder name match
        if termo_normalizado == nome:
            candidatos.append((4, caminho))
            continue

        # Strong token match: all significant tokens present in folder name
        if tokens_termo and all(token in nome for token in tokens_termo):
            candidatos.append((3, caminho))
            continue

        # Partial match: any token present
        if tokens_termo and any(token in nome for token in tokens_termo):
            candidatos.append((2, caminho))
            continue

        # Fallback: term appears in the relative path
        if termo_normalizado in relativo:
            candidatos.append((1, caminho))

    candidatos.sort(key=lambda item: (-item[0], len(item[1].as_posix()), item[1].as_posix().lower()))
    return [caminho for _, caminho in candidatos]


def resolver_pasta_cliente(termo: str, raiz: Path | None = None) -> Path | None:
    pastas = buscar_pastas_clientes(termo, raiz)
    return pastas[0] if pastas else None


DOC_TYPE_KEYWORDS = {
    "oficio": "OFICIO",
    "ofício": "OFICIO",
    "oficios": "OFICIO",
    "peticao": "PETICAO",
    "petição": "PETICAO",
    "contrato": "CONTRATO",
    "rg": "RG",
    "comprovante": "COMPROVANTE",
}


def resolver_cliente_e_tipo(termo: str, raiz: Path | None = None) -> tuple[Path | None, Path | None]:
    """Tenta resolver uma pasta de cliente e, opcionalmente, uma subpasta de tipo.

    Retorna (pasta_cliente, pasta_tipo) onde pasta_tipo é uma subpasta dentro de pasta_cliente quando encontrada.
    """
    raiz = raiz or obter_raiz()
    if not raiz or not raiz.exists():
        return None, None

    termo_normalizado = normalizar_texto(termo)
    # detect document type token
    tipo_token = None
    for key in DOC_TYPE_KEYWORDS.keys():
        if key in termo_normalizado:
            tipo_token = DOC_TYPE_KEYWORDS[key]
            break

    # Remove stop words and doc token for client search
    STOP_WORDS = {"tem", "documento", "documentos", "da", "do", "de", "dos", "das", "o", "a", "e", "que", "um", "uma", "por", "para", "com"}
    tokens = [t for t in termo_normalizado.split() if t and t not in STOP_WORDS and t not in (tipo_token or "")]
    busca_cliente = " ".join(tokens) if tokens else termo_normalizado

    cliente_path = resolver_pasta_cliente(busca_cliente, raiz) if busca_cliente else None

    if cliente_path and tipo_token:
        # look for a folder under cliente_path that matches the tipo_token
        for child in cliente_path.iterdir():
            if child.is_dir():
                nome = normalizar_texto(child.name)
                if normalizar_texto(tipo_token).lower() in nome:
                    return cliente_path, child
        # fallback: check directly under NAO_PROTOCOLADO/PROTOCOLADO structures
        for folder in (raiz / "01_Nao_Protocolado", raiz / "02_Protocolado"):
            candidate = folder / cliente_path.name / tipo_token
            if candidate.exists():
                return cliente_path, candidate

    return cliente_path, None


def buscar_documentos(termo: str, raiz: Path | None = None) -> list[Path]:
    raiz = raiz or obter_raiz()
    if not raiz or not raiz.exists():
        return []

    termo_normalizado = normalizar_texto(termo)
    resultados: list[Path] = []

    for caminho in raiz.rglob("*"):
        if not caminho.is_file():
            continue

        nome = normalizar_texto(caminho.name)
        relativo = normalizar_texto(caminho.relative_to(raiz).as_posix())
        if termo_normalizado in nome or termo_normalizado in relativo:
            resultados.append(caminho)

    return sorted(resultados, key=lambda item: item.as_posix().lower())


def abrir_local(caminho: Path) -> None:
    if os.name == "nt":
        if caminho.is_file():
            subprocess.Popen(["explorer", "/select,", str(caminho)])
        else:
            subprocess.Popen(["explorer", str(caminho)])
        return

    if sys.platform == "darwin":
        subprocess.Popen(["open", str(caminho)])
    else:
        subprocess.Popen(["xdg-open", str(caminho)])


def resumo_caminho(caminho: Path, raiz: Path | None = None) -> str:
    raiz = raiz or obter_raiz()
    if raiz and raiz in caminho.parents:
        return caminho.relative_to(raiz).as_posix()
    return caminho.as_posix()
