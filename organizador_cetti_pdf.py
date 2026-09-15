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
CLIENTE_DESCONHECIDO = "CLIENTE_NAO_IDENTIFICADO"
TIPO_DESCONHECIDO = "OUTROS"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger("cetti_pdf")


TIPOS_DOCUMENTO = (
    ("requerimento", "REQUERIMENTO"),
    ("comprovante de residencia", "COMPROVANTE_RESIDENCIA"),
    ("comprovante de endereço", "COMPROVANTE_RESIDENCIA"),
    ("contrato de honorarios", "CONTRATO_HONORARIOS"),
    ("contrato de honorários", "CONTRATO_HONORARIOS"),
    ("procuracao", "PROCURACAO"),
    ("procuração", "PROCURACAO"),
    ("peticao inicial", "PETICAO_INICIAL"),
    ("petição inicial", "PETICAO_INICIAL"),
    ("contestacao", "CONTESTACAO"),
    ("contestação", "CONTESTACAO"),
    ("sentenca", "SENTENCA"),
    ("sentença", "SENTENCA"),
    ("certidao", "CERTIDAO"),
    ("certidão", "CERTIDAO"),
    ("oficio", "OFICIO"),
    ("ofício", "OFICIO"),
    ("intimacao", "INTIMACAO"),
    ("intimação", "INTIMACAO"),
    ("rg", "RG"),
    ("cpf", "CPF"),
    ("cnpj", "CNPJ"),
    ("laudo", "LAUDO"),
    ("recibo", "RECIBO"),
)

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
    "qualificacao",
}


def sem_acentos(texto: str) -> str:
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(char for char in normalizado if not unicodedata.combining(char))


def nome_seguro(texto: str, fallback: str) -> str:
    texto = sem_acentos(texto).upper()
    texto = re.sub(r"[^A-Z0-9 ]+", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip(" .")
    return texto[:100] or fallback


def extrair_texto_pdf(caminho: Path) -> str:
    leitor = PdfReader(str(caminho))
    paginas = []
    for pagina in leitor.pages:
        paginas.append(pagina.extract_text() or "")
    texto = "\n".join(paginas).strip()
    if not texto:
        raise ValueError("PDF sem texto extraivel. PDFs digitalizados exigem OCR, que esta versao nao executa.")
    return texto


def identificar_tipo(texto: str, nome_arquivo: str) -> str:
    texto_busca = sem_acentos(f"{nome_arquivo}\n{texto}").lower()
    for palavra, tipo in TIPOS_DOCUMENTO:
        if sem_acentos(palavra).lower() in texto_busca:
            return tipo
    return TIPO_DESCONHECIDO


def limpar_candidato(valor: str) -> str:
    valor = re.sub(r"\s+", " ", valor).strip(" .,:;-|")
    valor = re.sub(r"\b(?:cpf|rg|cnpj)\s*[:.\-]?\s*[0-9./-]+", "", valor, flags=re.IGNORECASE)
    palavras = [palavra for palavra in valor.split() if palavra.lower() not in PALAVRAS_IGNORADAS]
    valor = " ".join(palavras).strip(" .,:;-|")
    if not 2 <= len(valor.split()) <= 8:
        return ""
    if any(char.isdigit() for char in valor):
        return ""
    return valor


def identificar_cliente(texto: str, nome_arquivo: str) -> str:
    linhas = [re.sub(r"\s+", " ", linha).strip() for linha in texto.splitlines()]
    padroes = "|".join(re.escape(rotulo) for rotulo in ROTULOS_CLIENTE)
    candidatos = []

    for linha in linhas:
        correspondencia = re.search(rf"(?:^|\b)(?:{padroes})\s*[:\-]\s*(.+)$", linha, re.IGNORECASE)
        if correspondencia:
            candidato = limpar_candidato(correspondencia.group(1))
            if candidato:
                candidatos.append(candidato)

    if candidatos:
        return nome_seguro(candidatos[0], CLIENTE_DESCONHECIDO)

    texto_normalizado = re.sub(r"\s+", " ", texto).strip()
    padroes_juridicos = (
        r"([A-ZÀ-Ú][A-ZÀ-Ú' -]{5,})\s*,?\s*já\s+qualificad\s*[oa]",
        r"(?:em face de|em desfavor de|em nome de)\s+([A-ZÀ-Ú][A-ZÀ-Ú' -]{5,})",
    )
    for padrao in padroes_juridicos:
        correspondencia = re.search(padrao, texto_normalizado, re.IGNORECASE)
        if correspondencia:
            candidato = limpar_candidato(correspondencia.group(1))
            if candidato:
                return nome_seguro(candidato, CLIENTE_DESCONHECIDO)

    return CLIENTE_DESCONHECIDO


def esta_protocolado(texto: str, nome_arquivo: str) -> bool:
    conteudo = sem_acentos(f"{nome_arquivo}\n{texto}").lower()
    marcadores = ("protocolado", "protocolo", "distribuido", "distribuicao", "processo distribuido")
    return any(marcador in conteudo for marcador in marcadores) or "assinado" in conteudo


def identificar_documento(caminho: Path) -> tuple[str, str, bool]:
    texto = extrair_texto_pdf(caminho)
    cliente = identificar_cliente(texto, caminho.name)
    tipo = identificar_tipo(texto, caminho.name)
    return cliente, tipo, esta_protocolado(texto, caminho.name)


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


def pasta_cliente_do_pdf(pdf: Path, pastas: dict[str, Path]) -> Path | None:
    clientes = pastas["clientes"]
    if clientes in pdf.parents:
        relativo = pdf.relative_to(clientes)
        if len(relativo.parts) >= 2:
            return clientes / relativo.parts[0]
    return None


def arquivar_assinatura(assinatura: Path, pdf: Path, pastas: dict[str, Path]) -> None:
    pasta_cliente = pasta_cliente_do_pdf(pdf, pastas)
    if pasta_cliente is None:
        log.warning("PDF correspondente encontrado, mas a pasta do cliente nao foi identificada: %s", pdf)
        return

    pasta_assinados = pasta_cliente / "Documentos Assinados"
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


def processar_pdf(caminho: Path, pastas: dict[str, Path]) -> None:
    if caminho.suffix.lower() != EXTENSAO_PERMITIDA or not caminho.is_file():
        return

    assinatura = encontrar_assinatura(caminho)
    try:
        cliente, tipo, protocolado = identificar_documento(caminho)
        destino = pastas["clientes"] / cliente / tipo / caminho.name
        mover_com_retry(caminho, destino)
        status = "Protocolado" if protocolado else "Nao protocolado"
        log.info("%s | cliente=%s | tipo=%s | pdf=%s", status, cliente, tipo, destino)

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
        if event.is_directory:
            return
        caminho = Path(event.src_path)
        if caminho.suffix.lower() == EXTENSAO_PERMITIDA:
            time.sleep(2)
            processar_pdf(caminho, self.pastas)
        elif caminho.suffix.lower() in EXTENSOES_ASSINATURA:
            time.sleep(2)
            processar_assinatura(caminho, self.pastas, self.raiz)


def processar_existentes(pastas: dict[str, Path]) -> None:
    entrada = pastas["entrada"]
    for caminho in sorted(entrada.glob("*.pdf")):
        processar_pdf(caminho, pastas)
    for caminho in sorted(entrada.iterdir()):
        if caminho.is_file() and caminho.suffix.lower() in EXTENSOES_ASSINATURA:
            processar_assinatura(caminho, pastas, entrada.parent)


def executar() -> None:
    raiz = obter_raiz()
    if raiz is None:
        raise SystemExit("ERRO: defina CAMINHO_RAIZ_DRIVE no arquivo .env")

    pastas = garantir_estrutura(raiz)
    pastas["entrada"].mkdir(parents=True, exist_ok=True)
    pastas["clientes"].mkdir(parents=True, exist_ok=True)
    processar_existentes(pastas)

    observador = PollingObserver()
    observador.schedule(Handler(pastas, raiz), str(pastas["entrada"]), recursive=False)
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
