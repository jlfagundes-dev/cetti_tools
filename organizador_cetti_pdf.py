import logging
import os
import re
import shutil
import ctypes
import threading
import time
import unicodedata
from datetime import date, timedelta
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
PALAVRAS_RUIDO_OCR = {
    "a",
    "as",
    "cidade",
    "cep",
    "cpf",
    "do",
    "dos",
    "endereco",
    "enderego",
    "estado",
    "e",
    "matricula",
    "pagador",
    "pagadoricpf",
    "para",
    "uf",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger("cetti_pdf")
TRAVA_REAVALIACAO = threading.Lock()
NOME_MUTEX_MONITOR = "Global\\ArquivistaDigitalCettiPdfMonitor"


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
    "autor",
    "autora",
    "requerente",
    "reu",
    "réu",
    "re",
    "requerido",
    "requerida",
    "vitima",
    "vítima",
    "outorgante",
)

PREFIXOS_DOCUMENTO = (
    "declaracao de hipossuficiencia economica",
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
    "causa",
    "disso",
    "esclareceu",
    "esclarece",
    "justa",
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


def arquivo_anterior_de_hoje(caminho: Path, hoje: date | None = None) -> bool:
    """Permite classificar somente PDFs modificados no dia anterior pra tras."""
    try:
        data_referencia = hoje or date.today()
        return date.fromtimestamp(caminho.stat().st_mtime) < data_referencia - timedelta(days=1)
    except OSError:
        return False


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
    for prefixo in PREFIXOS_DOCUMENTO:
        valor = re.sub(
            rf"^\s*{re.escape(prefixo)}\s*[-:,.]?\s*",
            "",
            sem_acentos(valor),
            flags=re.IGNORECASE,
        )
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
    return pontuar_candidato_no_nome_arquivo(candidato, nome_arquivo) > 0


def pontuar_candidato_no_nome_arquivo(candidato: str, nome_arquivo: str) -> int:
    """Pontua quanto o nome do arquivo confirma um candidato completo do PDF."""
    tokens_candidato = [
        token
        for token in normalizar_busca_cliente(candidato).split()
        if token not in PALAVRAS_NOME_ARQUIVO and len(token) >= 3
    ]
    tokens_arquivo = {
        token
        for token in normalizar_busca_cliente(Path(nome_arquivo).stem).split()
        if token not in PALAVRAS_NOME_ARQUIVO and len(token) >= 3
    }
    correspondencias = set(tokens_candidato) & tokens_arquivo
    if not correspondencias:
        return 0

    pontuacao = len(correspondencias) * 10
    if len(correspondencias) == len(tokens_candidato):
        pontuacao += 5
    return pontuacao


def identificar_cliente(texto: str, nome_arquivo: str) -> str:
    linhas = [re.sub(r"\s+", " ", linha).strip() for linha in texto.splitlines()]
    padroes = "|".join(re.escape(rotulo) for rotulo in ROTULOS_CLIENTE)
    candidatos = []

    # As partes podem aparecer como autor/requerente ou reu/requerido; o nome
    # do arquivo decide qual delas e o cliente quando houver mais de uma.
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
                rf"^{re.escape(rotulo)}\s*[:\-]\s*(.+)$",
                linha,
                re.IGNORECASE,
            )
            if correspondencia:
                candidato = limpar_candidato(correspondencia.group(1))
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

    candidatos_confirmados = [
        (pontuar_candidato_no_nome_arquivo(candidato, nome_arquivo), indice, candidato)
        for indice, candidato in enumerate(candidatos)
        if candidato_citado_no_nome_arquivo(candidato, nome_arquivo)
    ]
    if candidatos_confirmados:
        _, _, melhor_candidato = max(candidatos_confirmados, key=lambda item: (item[0], -item[1]))
        return nome_seguro(melhor_candidato, CLIENTE_DESCONHECIDO)

    # Sem correspondencia com o nome do arquivo, nao ha seguranca suficiente
    # para criar uma pasta de cliente a partir de um candidato do texto.
    return CLIENTE_DESCONHECIDO


def normalizar_busca_cliente(texto: str) -> str:
    """Normaliza o texto para comparar nomes extraidos de documentos externos."""
    return re.sub(r"[^A-Z0-9]+", " ", sem_acentos(texto).upper()).strip()


def tokens_nome_cliente(texto: str) -> set[str]:
    return {
        token.lower()
        for token in normalizar_busca_cliente(texto).split()
        if len(token) > 2 and token.lower() not in PALAVRAS_RUIDO_OCR
    }


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
    """Procura um cliente existente com evidencias fortes e nao ambiguas."""
    tokens_arquivo = tokens_nome_cliente(Path(nome_arquivo).stem)
    candidatos = []
    for rotulo, candidato in extrair_campos_externos(texto):
        tokens_candidato = tokens_nome_cliente(candidato)
        if len(tokens_candidato) < 2:
            log.info("Candidato OCR descartado | campo=%s | valor=%s | motivo=poucos tokens reais", rotulo, candidato)
            continue
        candidatos.append((rotulo, tokens_candidato))

    resultados = []
    try:
        pastas_clientes = list(clientes_dir.iterdir())
    except OSError as erro:
        log.warning("Nao foi possivel consultar as pastas de clientes: %s", erro)
        return ""

    for pasta in pastas_clientes:
        if not pasta.is_dir() or pasta.name.startswith("00_"):
            continue
        tokens_cliente = tokens_nome_cliente(pasta.name)
        if not tokens_cliente:
            continue

        melhor_pontuacao = 0
        melhor_motivo = ""
        for rotulo, tokens_candidato in candidatos:
            correspondencias = tokens_cliente & tokens_candidato
            if len(tokens_cliente) >= 2 and len(correspondencias) >= 2:
                pontuacao = len(correspondencias) * 10
                if correspondencias == tokens_cliente:
                    pontuacao += 10
                if pontuacao > melhor_pontuacao:
                    melhor_pontuacao = pontuacao
                    melhor_motivo = f"OCR:{rotulo}"

        correspondencias_arquivo = tokens_cliente & tokens_arquivo
        if len(tokens_cliente) >= 2 and len(correspondencias_arquivo) >= 2:
            pontuacao = len(correspondencias_arquivo) * 20
            if correspondencias_arquivo == tokens_cliente:
                pontuacao += 20
            if pontuacao > melhor_pontuacao:
                melhor_pontuacao = pontuacao
                melhor_motivo = "nome do arquivo"
        elif len(tokens_cliente) == 1 and len(correspondencias_arquivo) == 1:
            token = next(iter(correspondencias_arquivo))
            if len(token) >= 4:
                melhor_pontuacao = max(melhor_pontuacao, 20)
                melhor_motivo = "nome do arquivo"

        if melhor_pontuacao:
            resultados.append((melhor_pontuacao, pasta.name, melhor_motivo))

    resultados.sort(reverse=True)
    if not resultados:
        log.info("Nenhum cliente confiavel encontrado | arquivo=%s", nome_arquivo)
        return ""
    if len(resultados) > 1 and resultados[0][0] == resultados[1][0]:
        log.info("Candidatos OCR ambiguos descartados | arquivo=%s | candidatos=%s", nome_arquivo, resultados[:2])
        return ""
    melhor_pontuacao, melhor_cliente, motivo = resultados[0]
    log.info("Cliente identificado com evidencia %s | cliente=%s | arquivo=%s", motivo, melhor_cliente, nome_arquivo)
    return melhor_cliente


def esta_protocolado(texto: str, nome_arquivo: str) -> bool:
    conteudo = sem_acentos(f"{nome_arquivo}\n{texto}").lower()
    marcadores = ("protocolado", "protocolo", "distribuido", "distribuicao", "processo distribuido")
    return any(marcador in conteudo for marcador in marcadores) or "assinado" in conteudo


def identificar_documento(caminho: Path) -> tuple[str, bool]:
    texto = extrair_texto_pdf(caminho)
    cliente = identificar_cliente(texto, caminho.name)
    return cliente, esta_protocolado(texto, caminho.name)


def aguardar_arquivo_pronto(caminho: Path, tentativas: int = 12, intervalo: float = 2.0) -> bool:
    """Aguarda a conclusao de copias ou sincronizacoes antes do processamento."""
    tamanho_anterior = None
    modificacao_anterior = None
    for _ in range(tentativas):
        try:
            estatisticas = caminho.stat()
            with caminho.open("rb"):
                pass
        except (FileNotFoundError, PermissionError, OSError):
            time.sleep(intervalo)
            continue

        tamanho_atual = estatisticas.st_size
        modificacao_atual = estatisticas.st_mtime_ns
        if (
            tamanho_atual > 0
            and tamanho_atual == tamanho_anterior
            and modificacao_atual == modificacao_anterior
        ):
            return True

        tamanho_anterior = tamanho_atual
        modificacao_anterior = modificacao_atual
        time.sleep(intervalo)
    return False


def mover_com_retry(origem: Path, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    for tentativa in range(1, 7):
        try:
            shutil.move(str(origem), str(destino))
            return
        except PermissionError:
            if tentativa == 6:
                raise
            time.sleep(5)


def garantir_clientes_disponivel(pastas: dict[str, Path], tentativas: int = 12, intervalo: float = 5.0) -> bool:
    """Garante que a estrutura oficial de clientes esteja acessivel antes de uma rodada."""
    clientes = pastas["clientes"]
    for tentativa in range(1, tentativas + 1):
        try:
            clientes.mkdir(parents=True, exist_ok=True)
            if clientes.is_dir():
                return True
        except OSError as erro:
            if tentativa == 1:
                log.warning("Pasta 01_CLIENTES indisponivel; aguardando para tentar novamente: %s", erro)
        if tentativa < tentativas:
            time.sleep(intervalo)

    log.error("Rodada interrompida: pasta 01_CLIENTES continua indisponivel: %s", clientes)
    return False


def processar_pendentes(pastas: dict[str, Path]) -> None:
    """Executa uma unica reavaliacao por vez."""
    if not TRAVA_REAVALIACAO.acquire(blocking=False):
        log.debug("Reavaliacao de documentos externos ja esta em andamento.")
        return
    try:
        _processar_pendentes(pastas)
    finally:
        TRAVA_REAVALIACAO.release()


def _processar_pendentes(pastas: dict[str, Path]) -> None:
    """Move pendentes somente quando o documento externo corresponde a cliente cadastrado."""
    if not garantir_clientes_disponivel(pastas):
        return
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
        if not caminho.exists():
            log.info("Documento externo ja foi movido por outra rotina: %s", caminho.name)
            continue
        if not arquivo_anterior_de_hoje(caminho):
            log.debug("Documento externo aguardando o dia seguinte para reavaliacao: %s", caminho.name)
            continue
        try:
            texto = extrair_texto_pdf(caminho)
            cliente = buscar_cliente_externo(texto, caminho.name, pastas["clientes"])
            if not cliente:
                continue
            assinatura = encontrar_assinatura(caminho)
            cliente = resolver_pasta_cliente_existente(cliente, pastas["clientes"])
            destino = pastas["clientes"] / cliente / caminho.name
            if not caminho.exists():
                log.info("Documento externo ja foi movido antes da transferencia: %s", caminho.name)
                continue
            mover_com_retry(caminho, destino)
            if assinatura is not None and assinatura.exists():
                arquivar_assinatura(assinatura, destino, pastas)
            log.info("Documento externo identificado | cliente=%s | pdf=%s", cliente, caminho.name)
        except FileNotFoundError:
            log.info("Documento externo ja foi movido durante a reavaliacao: %s", caminho.name)
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

    pastas_equivalentes = []
    for pasta in clientes_dir.iterdir():
        if not pasta.is_dir() or pasta.name.startswith("00_"):
            continue
        nome_pasta_normalizado = nome_seguro(pasta.name, "")
        chave_pasta = normalizar_busca_cliente(nome_pasta_normalizado).replace(" ", "")
        if chave_pasta == chave_cliente:
            pastas_equivalentes.append(pasta)

    for pasta in pastas_equivalentes:
        if pasta.name == cliente_normalizado:
            return pasta.name
    if pastas_equivalentes:
        return sorted(pastas_equivalentes, key=lambda pasta: pasta.name.casefold())[0].name
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
    if not arquivo_anterior_de_hoje(caminho):
        log.debug("PDF aguardando o dia seguinte para classificacao: %s", caminho.name)
        return
    if not aguardar_arquivo_pronto(caminho):
        log.warning("PDF aguardando conclusao da copia ou sincronizacao: %s", caminho.name)
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
        self._processamento_lock = threading.Lock()
        self._timer_lock = threading.Lock()
        self._pendentes_timer = None

    def _agendar_reavaliacao_ociosa(self) -> None:
        with self._timer_lock:
            if self._pendentes_timer is not None:
                self._pendentes_timer.cancel()
            self._pendentes_timer = threading.Timer(5, self._reavaliar_se_ociosa)
            self._pendentes_timer.daemon = True
            self._pendentes_timer.start()

    def _reavaliar_se_ociosa(self) -> None:
        with self._processamento_lock:
            if not garantir_clientes_disponivel(self.pastas):
                return
            processar_pendentes(self.pastas)

    def on_created(self, event):
        if not garantir_clientes_disponivel(self.pastas):
            return
        with self._processamento_lock:
            self._processar_evento(event)
        self._agendar_reavaliacao_ociosa()

    def _processar_evento(self, event):
        caminho = Path(event.src_path)
        if event.is_directory:
            return
        if caminho.suffix.lower() in EXTENSOES_WORD and caminho.parent == self.pastas["entrada"]:
            time.sleep(2)
            mover_arquivo_word(caminho, self.pastas)
        elif caminho.suffix.lower() == EXTENSAO_PERMITIDA:
            time.sleep(2)
            processar_pdf(caminho, self.pastas)
        elif caminho.suffix.lower() in EXTENSOES_ASSINATURA:
            time.sleep(2)
            processar_assinatura(caminho, self.pastas, self.raiz)


def processar_existentes(pastas: dict[str, Path]) -> None:
    if not garantir_clientes_disponivel(pastas):
        return
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


class InstanciaUnicaMonitor:
    def __init__(self):
        self.handle = None
        self.arquivo_lock = None

    def adquirir(self) -> bool:
        if os.name == "nt":
            self.handle = ctypes.windll.kernel32.CreateMutexW(None, False, NOME_MUTEX_MONITOR)
            if not self.handle:
                raise OSError("Nao foi possivel criar o mutex do monitor")
            if ctypes.windll.kernel32.GetLastError() == 183:
                ctypes.windll.kernel32.CloseHandle(self.handle)
                self.handle = None
                return False
            return True

        self.arquivo_lock = Path(__file__).with_suffix(".monitor.lock")
        try:
            descritor = os.open(self.arquivo_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(descritor)
        except FileExistsError:
            return False
        return True

    def liberar(self) -> None:
        if self.handle is not None:
            ctypes.windll.kernel32.CloseHandle(self.handle)
            self.handle = None
        if self.arquivo_lock is not None:
            try:
                self.arquivo_lock.unlink()
            except FileNotFoundError:
                pass
            self.arquivo_lock = None


def executar() -> None:
    instancia = InstanciaUnicaMonitor()
    if not instancia.adquirir():
        log.error("Monitor ja esta em execucao; esta instancia sera encerrada.")
        return
    try:
        _executar_monitor()
    finally:
        instancia.liberar()


def _executar_monitor() -> None:
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
        ultimo_dia = date.today()
        while True:
            time.sleep(1)
            hoje = date.today()
            if hoje != ultimo_dia:
                ultimo_dia = hoje
                processar_existentes(pastas)
    except KeyboardInterrupt:
        observador.stop()
    observador.join()


if __name__ == "__main__":
    executar()
