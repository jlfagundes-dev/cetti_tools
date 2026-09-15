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


load_dotenv(override=True)

EXTENSAO_PERMITIDA = ".pdf"
CLIENTE_DESCONHECIDO = "CLIENTE_NAO_IDENTIFICADO"
TIPO_DESCONHECIDO = "OUTROS"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("cetti_pdf.log", encoding="utf-8"),
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


def processar_arquivo(caminho: Path, pastas: dict[str, Path]) -> None:
    if caminho.suffix.lower() != EXTENSAO_PERMITIDA or not caminho.is_file():
        return

    try:
        cliente, tipo, protocolado = identificar_documento(caminho)
        grupo = pastas["protocolado"] if protocolado else pastas["nao_protocolado"]
        destino = grupo / cliente / tipo / caminho.name
        mover_com_retry(caminho, destino)
        status = "Protocolado" if protocolado else "Nao protocolado"
        log.info("%s | cliente=%s | tipo=%s | destino=%s", status, cliente, tipo, destino)
    except Exception as erro:
        log.error("Nao foi possivel processar %s: %s", caminho.name, erro)


class Handler(FileSystemEventHandler):
    def __init__(self, pastas: dict[str, Path]):
        self.pastas = pastas

    def on_created(self, event):
        if event.is_directory:
            return
        caminho = Path(event.src_path)
        if caminho.suffix.lower() == EXTENSAO_PERMITIDA:
            time.sleep(2)
            processar_arquivo(caminho, self.pastas)


def processar_existentes(pastas: dict[str, Path]) -> None:
    entrada = pastas["entrada"]
    for caminho in sorted(entrada.glob("*.pdf")):
        processar_arquivo(caminho, pastas)


def executar() -> None:
    raiz = obter_raiz()
    if raiz is None:
        raise SystemExit("ERRO: defina CAMINHO_RAIZ_DRIVE no arquivo .env")

    pastas = garantir_estrutura(raiz)
    pastas["entrada"].mkdir(parents=True, exist_ok=True)
    processar_existentes(pastas)

    observador = PollingObserver()
    observador.schedule(Handler(pastas), str(pastas["entrada"]), recursive=False)
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
