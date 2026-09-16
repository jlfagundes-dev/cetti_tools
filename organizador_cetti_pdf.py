import logging
import os
import re
import shutil
import time
import unicodedata
from pathlib import Path

from dotenv import load_dotenv
from pypdf import PdfReader
from watchdog.events import FileSystemEventHandler
from watchdog.observers.polling import PollingObserver

from cetti_core import garantir_estrutura, obter_raiz
from cetti_logging import log_monitor
from cetti_logging import LOG_FILE


load_dotenv(override=True)

EXTENSAO_PERMITIDA = ".pdf"
EXTENSOES_ASSINATURA = (".p7s", ".p7m", ".sig")
EXTENSOES_WORD = (".doc", ".docx", ".docm")
CLIENTE_DESCONHECIDO = "00_CLIENTE_NAO_IDENTIFICADO"
ROTULOS_DOCUMENTO_EXTERNO = ("pagador", "nome", "titular", "beneficiario", "beneficiário")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger("cetti_pdf")


ROTULOS_CLIENTE = (
    "cliente",
    "requerente",
    "autor",
    "autora",
    "contratante",
    "outorgante",
    "interessado",
    "interessada",
    "nome completo",
)

ROTULOS_PARTE_CLIENTE = (
    "reu",
    "réu",
    "requerido",
    "requerida",
    "vitima",
    "vítima",
    "outorgante",
)

PALAVRAS_NOME_ARQUIVO = {
    "acao",
    "acordo",
    "autos",
    "certidao",
    "comprovante",
    "contestacao",
    "contrato",
    "decisao",
    "documento",
    "peticao",
    "processo",
    "requerimento",
    "sentenca",
}

PALAVRAS_IGNORADAS = {
    "cliente",
    "requerente",
    "autor",
    "autora",
    "contratante",
    "outorgante",
    "interessado",
    "interessada",
    "nome",
    "completo",
    "cpf",
    "rg",
    "documento",
    "brasileiro",
    "brasileira",
    "qualificacao",
}

PALAVRAS_DE_FRASE = {
    "alem",
    "disso",
    "esclareceu",
    "esclarece",
    "testemunha",
    "conforme",
    "declarou",
    "informou",
    "requer",
    "requerendo",
    "processo",
    "peticao",
    "documento",
}


def sem_acentos(texto: str) -> str:
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(char for char in normalizado if not unicodedata.combining(char))


def nome_seguro(texto: str, fallback: str) -> str:
    texto = sem_acentos(texto).upper()
    texto = re.sub(r"[^A-Z0-9 ]+", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip(" .")
    palavras = texto.split()
    while len(palavras) > 1 and len(palavras[-1]) == 1 and palavras[-1].isalpha():
        fragmento = palavras.pop()
        palavras[-1] += fragmento
    texto = " ".join(palavras)
    return texto[:100] or fallback


def extrair_texto_ocr(caminho: Path) -> str:
    try:
        import importlib

        fitz = importlib.import_module("pymupdf")
        pytesseract = importlib.import_module("pytesseract")
        image_module = importlib.import_module("PIL.Image")
    except ImportError as erro:
        raise ValueError(
            "PDF escaneado: instale pymupdf, pytesseract, Pillow e o executavel Tesseract OCR."
        ) from erro

    paginas = []
    idiomas = set(pytesseract.get_languages(config=""))
    idioma = "por+eng" if {"por", "eng"}.issubset(idiomas) else "por" if "por" in idiomas else "eng"
    with fitz.open(caminho) as documento:
        for pagina in documento:
            pixmap = pagina.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            imagem = image_module.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
            paginas.append(pytesseract.image_to_string(imagem, lang=idioma))
    return "\n".join(paginas).strip()


def extrair_texto_pdf(caminho: Path) -> str:
    leitor = PdfReader(str(caminho))
    paginas = []
    for pagina in leitor.pages:
        paginas.append(pagina.extract_text() or "")
    texto = "\n".join(paginas).strip()
    if not texto:
        texto = extrair_texto_ocr(caminho)
    if not texto:
        raise ValueError("PDF sem texto extraivel, mesmo apos OCR.")
    return texto


def limpar_candidato(valor: str) -> str:
    valor = re.sub(r"\s+", " ", valor).strip(" .,:;-|")
    valor = re.sub(r"\b(?:cpf|rg|cnpj)\s*[:.\-]?\s*[0-9./-]+", "", valor, flags=re.IGNORECASE)
    palavras = [palavra for palavra in valor.split() if palavra.lower() not in PALAVRAS_IGNORADAS]
    valor = " ".join(palavras).strip(" .,:;-|")
    palavras_normalizadas = {palavra.lower() for palavra in normalizar_busca_cliente(valor).split()}
    if not 2 <= len(valor.split()) <= 8 or len(valor) > 80:
        return ""
    if palavras_normalizadas & PALAVRAS_DE_FRASE:
        return ""
    if any(char.isdigit() for char in valor):
        return ""
    return valor


def candidato_citado_no_nome_arquivo(candidato: str, nome_arquivo: str) -> bool:
    tokens_candidato = set(normalizar_busca_cliente(candidato).split())
    tokens_arquivo = {
        token
        for token in normalizar_busca_cliente(Path(nome_arquivo).stem).split()
        if token not in PALAVRAS_NOME_ARQUIVO and len(token) >= 3
    }
    return bool(tokens_candidato & tokens_arquivo)


def identificar_cliente(texto: str, nome_arquivo: str) -> str:
    linhas = [re.sub(r"\s+", " ", linha).strip() for linha in texto.splitlines()]
    padroes = "|".join(re.escape(rotulo) for rotulo in ROTULOS_CLIENTE)
    candidatos = []

    # Em tabelas de partes, o reu/requerido e a vitima sao o cliente, nao o autor.
    for linha in linhas:
        for rotulo in ROTULOS_PARTE_CLIENTE:
            correspondencia = re.search(
                rf"^(.+?)\s*\(\s*{re.escape(rotulo)}\s*\)$|^(.+?)\s+{re.escape(rotulo)}$",
                linha,
                re.IGNORECASE,
            )
            if correspondencia:
                candidato = limpar_candidato(correspondencia.group(1) or correspondencia.group(2))
                if candidato:
                    candidatos.append(candidato)

        correspondencia = re.search(
            r"\bparte\s+(?:re|ré|autora?|requerida?)\s*[:\-]\s*(.+)$",
            linha,
            re.IGNORECASE,
        )
        if correspondencia:
            candidato = limpar_candidato(correspondencia.group(1))
            if candidato:
                candidatos.append(candidato)

    for linha in linhas:
        correspondencia = re.search(rf"(?:^|\b)(?:{padroes})\s*[:\-]\s*(.+)$", linha, re.IGNORECASE)
        if correspondencia:
            candidato = limpar_candidato(correspondencia.group(1))
            if candidato:
                candidatos.append(candidato)

    texto_normalizado = re.sub(r"\s+", " ", texto).strip()
    texto_sem_acentos = sem_acentos(texto_normalizado)
    padroes_juridicos = (
        r"([A-Z][A-Z' -]{5,})\s*,?\s*ja\s+qualificad\s*[oa]",
        r"(?:^|\n)\s*([A-Z][A-Z' -]{5,})\s*,\s*(?:brasileir[oa]|solteir[oa]|casad[oa]|divorciad[oa]|vi[uú]v[oa]|nascid[oa])\b",
        r"(?:^|\n)\s*([A-Z][A-Z' -]{5,})\s*,?\s*(?:outorgante|outorga)\b",
    )
    for padrao in padroes_juridicos:
        correspondencia = re.search(padrao, texto_sem_acentos, re.IGNORECASE)
        if correspondencia:
            candidato = limpar_candidato(correspondencia.group(1))
            if candidato:
                candidatos.append(candidato)

    for candidato in candidatos:
        if candidato_citado_no_nome_arquivo(candidato, nome_arquivo):
            return nome_seguro(candidato, CLIENTE_DESCONHECIDO)

    # Sem correspondencia com o nome do arquivo, nao ha seguranca suficiente
    # para criar uma pasta de cliente a partir de um candidato do texto.
    return CLIENTE_DESCONHECIDO


def normalizar_busca_cliente(texto: str) -> str:
    """Normaliza o texto para comparar nomes extraidos de documentos externos."""
    return re.sub(r"[^A-Z0-9]+", " ", sem_acentos(texto).upper()).strip()


def extrair_nomes_externos(texto: str) -> list[str]:
    """Extrai nomes de campos externos, inclusive quando o valor esta na linha seguinte."""
    return [candidato for _, candidato in extrair_campos_externos(texto)]


def extrair_campos_externos(texto: str) -> list[tuple[str, str]]:
    """Extrai o rotulo e o nome dos campos de documentos externos."""
    linhas = [re.sub(r"\s+", " ", linha).strip() for linha in texto.splitlines()]
    rotulos = "|".join(re.escape(rotulo) for rotulo in ROTULOS_DOCUMENTO_EXTERNO)
    candidatos = []
    for indice, linha in enumerate(linhas):
        correspondencia = re.search(
            rf"(?:^|\b)({rotulos})\s*[:.\-]?\s*(.+)$", linha, re.IGNORECASE
        )
        if correspondencia:
            candidatos.append((correspondencia.group(1).lower(), correspondencia.group(2)))
        elif re.fullmatch(rf"(?:{rotulos})\s*[:.\-]?", linha, re.IGNORECASE) and indice + 1 < len(linhas):
            rotulo = re.match(rf"({rotulos})", linha, re.IGNORECASE)
            if rotulo:
                candidatos.append((rotulo.group(1).lower(), linhas[indice + 1]))
    return [
        (rotulo, normalizar_busca_cliente(candidato))
        for rotulo, candidato in candidatos
        if candidato
    ]


def buscar_cliente_externo(texto: str, nome_arquivo: str, clientes_dir: Path) -> str:
    """Procura um cliente ja cadastrado sem criar pasta durante o fluxo externo."""
    conteudo = normalizar_busca_cliente(f"{nome_arquivo}\n{texto}")
    candidatos = extrair_campos_externos(texto) + [("", conteudo)]
    melhor_cliente = ""
    melhor_pontuacao = 0
    for pasta in clientes_dir.iterdir():
        if not pasta.is_dir() or pasta.name.startswith("00_"):
            continue
        nome = normalizar_busca_cliente(pasta.name)
        tokens = [token for token in nome.split() if len(token) > 2]
        pontuacao = 0
        for rotulo, candidato in candidatos:
            correspondencia = sum(token in candidato.split() for token in tokens)
            if rotulo == "pagador":
                correspondencia += 1000
            pontuacao = max(pontuacao, correspondencia)
        if nome and nome in conteudo:
            pontuacao += 100
        if pontuacao > melhor_pontuacao:
            melhor_pontuacao = pontuacao
            melhor_cliente = pasta.name
    return melhor_cliente if melhor_pontuacao >= 2 else ""


def esta_protocolado(texto: str, nome_arquivo: str) -> bool:
    conteudo = sem_acentos(f"{nome_arquivo}\n{texto}").lower()
    marcadores = ("protocolado", "protocolo", "distribuido", "distribuicao", "processo distribuido")
    return any(marcador in conteudo for marcador in marcadores) or "assinado" in conteudo


def identificar_documento(caminho: Path) -> tuple[str, bool]:
    texto = extrair_texto_pdf(caminho)
    cliente = identificar_cliente(texto, caminho.name)
    return cliente, esta_protocolado(texto, caminho.name)


def mover_com_retry(origem: Path, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    for tentativa in range(1, 4):
        try:
            shutil.move(str(origem), str(destino))
            return
        except PermissionError:
            if tentativa == 3:
                raise
            time.sleep(5)


def processar_pendentes(pastas: dict[str, Path]) -> None:
    """Move pendentes somente quando o documento externo corresponde a cliente cadastrado."""
    entrada = pastas["entrada"]
    if any(
        caminho.is_file()
        and caminho.suffix.lower() in (EXTENSAO_PERMITIDA, *EXTENSOES_ASSINATURA)
        for caminho in entrada.iterdir()
    ):
        return
    pendentes = pastas["nao_identificados"]
    if not pendentes.exists():
        return
    for caminho in sorted(pendentes.glob("*.pdf")):
        try:
            texto = extrair_texto_pdf(caminho)
            cliente = buscar_cliente_externo(texto, caminho.name, pastas["clientes"])
            if not cliente:
                continue
            assinatura = encontrar_assinatura(caminho)
            cliente = resolver_pasta_cliente_existente(cliente, pastas["clientes"])
            destino = pastas["clientes"] / cliente / caminho.name
            mover_com_retry(caminho, destino)
            if assinatura is not None and assinatura.exists():
                arquivar_assinatura(assinatura, destino, pastas)
            log.info("Documento externo identificado | cliente=%s | pdf=%s", cliente, caminho.name)
        except Exception as erro:
            log.error("Nao foi possivel reavaliar %s: %s", caminho.name, erro)


def chave_nome_documento(caminho: Path) -> str:
    """Normaliza nomes como Documento.pdf e Documento.pdf.p7s para a mesma chave."""
    nome = caminho.name
    for extensao in EXTENSOES_ASSINATURA:
        if nome.casefold().endswith(extensao):
            nome = nome[: -len(extensao)]
            break
    if nome.casefold().endswith(EXTENSAO_PERMITIDA):
        nome = nome[: -len(EXTENSAO_PERMITIDA)]
    return re.sub(r"[^a-z0-9]", "", sem_acentos(nome).casefold())


def encontrar_assinatura(caminho_pdf: Path) -> Path | None:
    """Localiza assinatura mesmo quando ela inclui '.pdf' antes de '.p7s'."""
    nome_base = chave_nome_documento(caminho_pdf)
    for candidato in caminho_pdf.parent.iterdir():
        if not candidato.is_file() or candidato.suffix.lower() not in EXTENSOES_ASSINATURA:
            continue
        if chave_nome_documento(candidato) == nome_base:
            return candidato
    return None


def encontrar_pdf_da_assinatura(caminho_assinatura: Path, raiz: Path) -> Path | None:
    nome_base = chave_nome_documento(caminho_assinatura)
    candidatos = []
    for candidato in raiz.rglob("*"):
        if candidato.is_file() and candidato.suffix.lower() == EXTENSAO_PERMITIDA:
            if chave_nome_documento(candidato) == nome_base:
                candidatos.append(candidato)
    candidatos.sort(key=lambda candidato: (0 if candidato.parent == caminho_assinatura.parent else 1, str(candidato).lower()))
    if candidatos:
        return candidatos[0]
    return None


def notificar_cliente(mensagem: str) -> None:
    log.warning(mensagem)
    log_monitor(f"AVISO AO CLIENTE: {mensagem}")


def resolver_pasta_cliente_existente(cliente: str, clientes_dir: Path) -> str:
    """Reutiliza uma pasta equivalente e evita duplicatas por falha de OCR."""
    cliente_normalizado = nome_seguro(cliente, CLIENTE_DESCONHECIDO)
    chave_cliente = normalizar_busca_cliente(cliente_normalizado).replace(" ", "")
    if not clientes_dir.exists():
        return cliente_normalizado

    for pasta in clientes_dir.iterdir():
        if not pasta.is_dir() or pasta.name.startswith("00_"):
            continue
        chave_pasta = normalizar_busca_cliente(pasta.name).replace(" ", "")
        if chave_pasta == chave_cliente:
            return pasta.name
    return cliente_normalizado


def pasta_cliente_do_pdf(pdf: Path, pastas: dict[str, Path]) -> Path | None:
    clientes = pastas["clientes"]
    if pdf.parent == pastas["nao_identificados"]:
        return pastas["nao_identificados"]
    if clientes in pdf.parents:
        relativo = pdf.relative_to(clientes)
        if len(relativo.parts) >= 1:
            return clientes / relativo.parts[0]
    return None


def arquivar_assinatura(assinatura: Path, pdf: Path, pastas: dict[str, Path]) -> None:
    pasta_cliente = pasta_cliente_do_pdf(pdf, pastas)
    if pasta_cliente is None:
        log.warning("PDF correspondente encontrado, mas a pasta do cliente nao foi identificada: %s", pdf)
        return

    # A pasta de nao identificados mantem PDFs e assinaturas diretamente no mesmo nivel.
    pasta_assinados = (
        pasta_cliente
        if pasta_cliente == pastas["nao_identificados"]
        else pasta_cliente / "Documentos Assinados"
    )
    assinaturas_existentes = [
        caminho for caminho in pasta_assinados.glob("*")
        if caminho.is_file()
        and caminho.suffix.lower() in EXTENSOES_ASSINATURA
        and chave_nome_documento(caminho) == chave_nome_documento(assinatura)
    ]
    if assinaturas_existentes:
        nome_existente = assinaturas_existentes[0].name
        notificar_cliente(
            f"Ja existe assinatura para o documento {pdf.name}. "
            f"Arquivo existente: {nome_existente}. A duplicata {assinatura.name} sera removida da entrada."
        )
        assinatura.unlink()
        return

    destino = pasta_assinados / assinatura.name
    mover_com_retry(assinatura, destino)
    log.info("Assinatura arquivada em %s", destino)


def mover_arquivo_word(caminho: Path, pastas: dict[str, Path]) -> None:
    destino = pastas["arquivos_word"] / caminho.name
    destino.parent.mkdir(parents=True, exist_ok=True)
    mover_com_retry(caminho, destino)
    log.info("Arquivo Word movido para 02_ARQUIVOS_DO_WORD: %s", caminho.name)


def achatar_pasta_nao_identificados(pastas: dict[str, Path]) -> None:
    """Migra a pasta antiga de desconhecidos para o novo nivel da biblioteca."""
    pasta_antiga = pastas["clientes"] / CLIENTE_DESCONHECIDO
    pasta_nova = pastas["nao_identificados"]
    if not pasta_antiga.exists():
        return
    pasta_nova.mkdir(parents=True, exist_ok=True)
    for item in sorted(pasta_antiga.rglob("*")):
        if not item.is_file():
            continue
        destino = pasta_nova / item.name
        if destino.exists():
            destino = pasta_nova / f"{item.stem}_duplicado{item.suffix}"
        mover_com_retry(item, destino)
    for diretorio in sorted(pasta_antiga.rglob("*"), reverse=True):
        if diretorio.is_dir():
            try:
                diretorio.rmdir()
            except OSError:
                pass
    try:
        pasta_antiga.rmdir()
    except OSError:
        log.warning("Nao foi possivel remover a pasta antiga: %s", pasta_antiga)


def migrar_pasta_clientes_antiga(pastas: dict[str, Path]) -> None:
    """Move clientes da pasta CLIENTES antiga para 01_CLIENTES."""
    pasta_antiga = pastas["clientes_antigos"]
    pasta_nova = pastas["clientes"]
    if not pasta_antiga.exists() or pasta_antiga == pasta_nova:
        return

    pasta_nova.mkdir(parents=True, exist_ok=True)
    for item in sorted(pasta_antiga.iterdir()):
        destino = pasta_nova / item.name
        if destino.exists():
            if item.is_dir() and destino.is_dir():
                for arquivo in item.rglob("*"):
                    if arquivo.is_file():
                        destino_arquivo = destino / arquivo.relative_to(item)
                        mover_com_retry(arquivo, destino_arquivo)
                continue
            destino = pasta_nova / f"{item.stem}_duplicado{item.suffix}"
        mover_com_retry(item, destino)
    try:
        pasta_antiga.rmdir()
    except OSError:
        log.warning("Nao foi possivel remover a pasta antiga: %s", pasta_antiga)


def processar_pdf(caminho: Path, pastas: dict[str, Path]) -> None:
    if caminho.suffix.lower() != EXTENSAO_PERMITIDA or not caminho.is_file():
        return

    assinatura = encontrar_assinatura(caminho)
    try:
        cliente, protocolado = identificar_documento(caminho)
        if cliente != CLIENTE_DESCONHECIDO:
            cliente = resolver_pasta_cliente_existente(cliente, pastas["clientes"])
        pasta_destino = (
            pastas["nao_identificados"]
            if cliente == CLIENTE_DESCONHECIDO
            else pastas["clientes"] / cliente
        )
        destino = pasta_destino / caminho.name
        mover_com_retry(caminho, destino)
        status = "Protocolado" if protocolado else "Nao protocolado"
        log.info("%s | cliente=%s | pdf=%s", status, cliente, destino)

        if assinatura is not None and assinatura.exists():
            arquivar_assinatura(assinatura, destino, pastas)
    except Exception as erro:
        log.error("Nao foi possivel processar %s: %s", caminho.name, erro)


def processar_assinatura(caminho: Path, pastas: dict[str, Path], raiz: Path) -> None:
    if caminho.suffix.lower() not in EXTENSOES_ASSINATURA or not caminho.is_file():
        return

    pdf = encontrar_pdf_da_assinatura(caminho, raiz)
    if pdf is None:
        log.warning("Assinatura aguardando PDF correspondente: %s", caminho.name)
        return

    if pdf.parent == pastas["entrada"]:
        processar_pdf(pdf, pastas)
        return

    try:
        arquivar_assinatura(caminho, pdf, pastas)
    except Exception as erro:
        log.error("Nao foi possivel arquivar a assinatura %s: %s", caminho.name, erro)


class Handler(FileSystemEventHandler):
    def __init__(self, pastas: dict[str, Path], raiz: Path):
        self.pastas = pastas
        self.raiz = raiz

    def on_created(self, event):
        caminho = Path(event.src_path)
        if event.is_directory:
            if caminho.parent == self.pastas["clientes"]:
                processar_pendentes(self.pastas)
            return
        if caminho.suffix.lower() in EXTENSOES_WORD and caminho.parent == self.pastas["entrada"]:
            time.sleep(2)
            mover_arquivo_word(caminho, self.pastas)
        elif caminho.suffix.lower() == EXTENSAO_PERMITIDA:
            time.sleep(2)
            processar_pdf(caminho, self.pastas)
            # Depois de concluir o PDF da entrada, tenta os documentos externos se a entrada esvaziou.
            processar_pendentes(self.pastas)
        elif caminho.suffix.lower() in EXTENSOES_ASSINATURA:
            time.sleep(2)
            processar_assinatura(caminho, self.pastas, self.raiz)
            # Depois de concluir a assinatura da entrada, tenta os documentos externos se a entrada esvaziou.
            processar_pendentes(self.pastas)


def processar_existentes(pastas: dict[str, Path]) -> None:
    entrada = pastas["entrada"]
    for caminho in sorted(entrada.iterdir()):
        if caminho.is_file() and caminho.suffix.lower() in EXTENSOES_WORD:
            mover_arquivo_word(caminho, pastas)
    for caminho in sorted(entrada.glob("*.pdf")):
        processar_pdf(caminho, pastas)
    for caminho in sorted(entrada.iterdir()):
        if caminho.is_file() and caminho.suffix.lower() in EXTENSOES_ASSINATURA:
            processar_assinatura(caminho, pastas, entrada)
    processar_pendentes(pastas)


def executar() -> None:
    raiz = obter_raiz()
    if raiz is None:
        raise SystemExit("ERRO: a pasta Documentos do Windows nao foi localizada")

    pastas = garantir_estrutura(raiz)
    pastas["entrada"].mkdir(parents=True, exist_ok=True)
    pastas["arquivos_word"].mkdir(parents=True, exist_ok=True)
    pastas["clientes"].mkdir(parents=True, exist_ok=True)
    pastas["nao_identificados"].mkdir(parents=True, exist_ok=True)
    migrar_pasta_clientes_antiga(pastas)
    achatar_pasta_nao_identificados(pastas)
    processar_existentes(pastas)

    observador = PollingObserver()
    handler = Handler(pastas, raiz)
    observador.schedule(handler, str(pastas["entrada"]), recursive=False)
    observador.schedule(handler, str(pastas["clientes"]), recursive=False)
    observador.start()
    log.info("Monitorando somente PDFs em %s", pastas["entrada"])

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observador.stop()
    observador.join()


if __name__ == "__main__":
    executar()
