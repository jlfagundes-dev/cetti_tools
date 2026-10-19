from __future__ import annotations

import os
import re
import shutil
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable

from cetti_logging import append_log, new_run_id
from cetti_db import CettiDatabase
from cetti_extracao import ExtractionResult, extract_pdf
from cetti_indexador import index_documents


WORD_SUFFIXES = {".doc", ".docx", ".docm"}
SIGNATURE_SUFFIXES = {".p7s", ".p7m", ".sig"}
PDF_SUFFIX = ".pdf"
GENERIC_FILENAME_TOKENS = {
    "acordo", "anexo", "ata", "decisao", "documento", "manifestacao",
    "oficio", "peticao", "processo", "sentenca",
}
UNKNOWN_FOLDER = "00_ARQUIVOS_NAO_ORGANIZADOS_AUTOMATICAMENTE"
CLIENTS_FOLDER = "01_CLIENTES"
WORD_FOLDER = "02_ARQUIVOS_DO_WORD"
ProgressCallback = Callable[[str], None]


@dataclass
class OrganizationSummary:
    scanned: int = 0
    moved: int = 0
    pdfs_analyzed: int = 0
    identified: int = 0
    unknown: int = 0
    signatures_moved: int = 0
    words_moved: int = 0
    skipped: int = 0
    errors: int = 0
    messages: list[str] | None = None
    file_statuses: list[str] | None = None
    diagnostics: list[str] | None = None

    def __post_init__(self) -> None:
        if self.messages is None:
            self.messages = []
        if self.file_statuses is None:
            self.file_statuses = []
        if self.diagnostics is None:
            self.diagnostics = []

    def as_dict(self) -> dict[str, int]:
        return {
            "scanned": self.scanned,
            "moved": self.moved,
            "pdfs_analyzed": self.pdfs_analyzed,
            "identified": self.identified,
            "unknown": self.unknown,
            "signatures_moved": self.signatures_moved,
            "words_moved": self.words_moved,
            "skipped": self.skipped,
            "errors": self.errors,
        }


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_accents.casefold()).split())


def _tokens(value: str) -> set[str]:
    return {token for token in _normalize(value).split() if len(token) >= 3}


def _attorney_names() -> list[str]:
    configured = os.getenv("ADVOGADO_PADRAO", "")
    return [name.strip() for name in configured.split(",") if name.strip()]


def _is_excluded_name(value: str, excluded_names: list[str]) -> bool:
    value_tokens = _tokens(value)
    if not value_tokens:
        return False
    return any(
        excluded_tokens and excluded_tokens.issubset(value_tokens)
        for excluded_tokens in (_tokens(name) for name in excluded_names)
    )


def _extract_client_names(text: str) -> list[str]:
    """Extract complete names from common identity-document labels."""
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    names: list[str] = []
    labels = (
        "nome civil",
        "nome completo",
        "nome do titular",
        "titular",
        "cliente",
        "beneficiario",
        "beneficiário",
        "autor",
        "autora",
        "reu",
        "réu",
        "requerente",
        "requerido",
        "requerida",
    )
    for index, line in enumerate(lines):
        normalized_line = _normalize(line)
        for label in labels:
            normalized_label = _normalize(label)
            candidates = []
            if normalized_line == normalized_label:
                candidates = lines[index + 1 : index + 5]
            elif normalized_line.startswith(f"{normalized_label}:"):
                candidates = [line.split(":", 1)[1].strip()]
            if not candidates:
                continue
            for candidate in candidates:
                if _looks_like_person_name(candidate):
                    names.append(candidate)
                    break
    return list(dict.fromkeys(names))


def _extract_role_names(text: str) -> list[str]:
    """Extract names associated with legal roles such as author and defendant."""
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    roles = {"autor", "autora", "reu", "r u", "requerente", "requerido", "requerida"}
    names: list[str] = []
    for line in lines:
        if ":" in line:
            role, candidate = line.split(":", 1)
            if _normalize(role) in roles and _looks_like_person_name(candidate):
                names.append(candidate.strip())
                continue
        match = re.match(r"^(?P<name>.+?)\s*\(\s*(?P<role>[^)]+)\s*\)$", line)
        if match and _normalize(match.group("role")) in roles:
            candidate = match.group("name").strip()
            if _looks_like_person_name(candidate):
                names.append(candidate)
                continue
        match = re.match(r"^(?P<name>.+?)\s+(?P<role>[A-Za-zÀ-ÿ]+)$", line)
        if match and _normalize(match.group("role")) in roles:
            candidate = match.group("name").strip()
            if _looks_like_person_name(candidate):
                names.append(candidate)
    return list(dict.fromkeys(names))


def _looks_like_person_name(value: str) -> bool:
    tokens = _tokens(value)
    if not 2 <= len(tokens) <= 8 or any(char.isdigit() for char in value):
        return False
    ignored = {
        "carteira", "trabalho", "digital", "data", "emissao", "dados",
        "pessoais", "nome", "civil", "cpf", "cliente", "titular",
    }
    if tokens.intersection(ignored):
        return False
    return len(tokens) >= 1


def _safe_client_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    cleaned = re.sub(r"[^A-Za-z0-9 ]+", " ", without_accents).strip()
    return re.sub(r"\s+", " ", cleaned).upper()[:100]


def _client_folders(root: Path) -> list[Path]:
    clients = root / CLIENTS_FOLDER
    if not clients.is_dir():
        return []
    return sorted((path for path in clients.iterdir() if path.is_dir() and not path.name.startswith("00_")),
                  key=lambda path: path.name.casefold())


def _filename_token_match_score(filename_token: str, client_token: str) -> int:
    if filename_token == client_token:
        return 30
    if len(filename_token) < 4 or len(client_token) < 4:
        return 0
    if SequenceMatcher(None, filename_token, client_token).ratio() >= 0.8:
        return 18
    return 0


def _client_from_filename(
    path: Path,
    clients: list[Path],
    excluded_names: list[str],
) -> Path | None:
    filename_tokens = _tokens(path.stem)
    if not filename_tokens:
        return None

    candidates: list[tuple[int, int, Path]] = []
    for client in clients:
        if _is_excluded_name(client.name, excluded_names):
            continue
        client_tokens = _tokens(client.name)
        token_scores = [
            max(
                (_filename_token_match_score(filename_token, client_token)
                 for filename_token in filename_tokens),
                default=0,
            )
            for client_token in client_tokens
        ]
        matched_scores = [score for score in token_scores if score]
        if not matched_scores:
            continue
        if (
            len(matched_scores) == 1
            and matched_scores[0] == 30
            and any(
                len(token) >= 4
                and token not in GENERIC_FILENAME_TOKENS
                and token not in client_tokens
                for token in filename_tokens
            )
        ):
            continue
        candidates.append((sum(matched_scores), len(matched_scores), client))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], -item[1], item[2].name.casefold()))
    best = candidates[0]
    if len(candidates) > 1 and best[:2] == candidates[1][:2]:
        return None
    return best[2]


def _folder_for_client_name(
    path: Path,
    clients: list[Path],
    client_name: str,
    excluded_names: list[str],
) -> Path | None:
    if not _looks_like_person_name(client_name) or _is_excluded_name(client_name, excluded_names):
        return None

    normalized_name = _normalize(client_name)
    name_tokens = _tokens(client_name)
    exact_matches = [
        client
        for client in clients
        if _normalize(client.name) == normalized_name
    ]
    if exact_matches:
        return exact_matches[0]

    related_matches = [
        client
        for client in clients
        if name_tokens and name_tokens.issubset(_tokens(client.name))
    ]
    if len(related_matches) == 1:
        return related_matches[0]
    if related_matches:
        return None

    client_root = path.parent / CLIENTS_FOLDER
    client_root.mkdir(parents=True, exist_ok=True)
    new_folder = client_root / _safe_client_name(client_name)
    if not new_folder.name:
        return None
    new_folder.mkdir(parents=True, exist_ok=True)
    return new_folder


def _name_from_document_matching_filename(
    path: Path,
    extracted: ExtractionResult,
    excluded_names: list[str],
) -> str | None:
    filename_tokens = _tokens(path.stem)
    if not filename_tokens:
        return None

    candidates: list[tuple[int, int, str]] = []
    names = _extract_client_names(extracted.text) + _extract_role_names(extracted.text)
    for name in dict.fromkeys(names):
        if not _looks_like_person_name(name) or _is_excluded_name(name, excluded_names):
            continue
        name_tokens = _tokens(name)
        scores = [
            max(
                (
                    _filename_token_match_score(name_token, filename_token)
                    for filename_token in filename_tokens
                ),
                default=0,
            )
            for name_token in name_tokens
        ]
        matched_scores = [score for score in scores if score]
        if not matched_scores:
            continue
        candidates.append((sum(matched_scores), len(matched_scores), name))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], -item[1], item[2].casefold()))
    if len(candidates) > 1 and candidates[0][:2] == candidates[1][:2]:
        return None
    return candidates[0][2]


def _name_from_candidates_matching_filename(
    path: Path,
    names: list[str],
    excluded_names: list[str],
) -> str | None:
    filename_tokens = _tokens(path.stem)
    candidates: list[tuple[int, int, str]] = []
    for name in dict.fromkeys(names):
        if not _looks_like_person_name(name) or _is_excluded_name(name, excluded_names):
            continue
        name_tokens = _tokens(name)
        scores = [
            max(
                (
                    _filename_token_match_score(name_token, filename_token)
                    for filename_token in filename_tokens
                ),
                default=0,
            )
            for name_token in name_tokens
        ]
        matched_scores = [score for score in scores if score]
        if matched_scores:
            candidates.append((sum(matched_scores), len(matched_scores), name))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], -item[1], item[2].casefold()))
    if len(candidates) > 1 and candidates[0][:2] == candidates[1][:2]:
        return None
    return candidates[0][2]


def _identify_client(
    path: Path,
    extracted: ExtractionResult,
    clients: list[Path],
    ai_name: str | None = None,
    ai_names: list[str] | None = None,
    excluded_names: list[str] | None = None,
) -> Path | None:
    excluded_names = excluded_names or []
    ai_filename_name = _name_from_candidates_matching_filename(
        path,
        ai_names or [],
        excluded_names,
    )
    if ai_filename_name is not None:
        ai_client = _folder_for_client_name(path, clients, ai_filename_name, excluded_names)
        if ai_client is not None:
            return ai_client

    document_name = _name_from_document_matching_filename(path, extracted, excluded_names)
    if document_name is not None:
        document_client = _folder_for_client_name(
            path,
            clients,
            document_name,
            excluded_names,
        )
        if document_client is not None:
            return document_client

    if ai_name:
        ai_client = _folder_for_client_name(path, clients, ai_name, excluded_names)
        if ai_client is not None:
            return ai_client

    filename_client = _client_from_filename(path, clients, excluded_names)
    if filename_client is not None:
        return filename_client

    filename_tokens = _tokens(path.stem)
    candidate_names = _extract_client_names(extracted.text) + _extract_role_names(extracted.text)
    if ai_name:
        candidate_names.insert(0, ai_name)
    normalized_filename = _normalize(path.stem)
    candidate_scores: list[tuple[int, str]] = []
    for name in dict.fromkeys(candidate_names):
        if not _looks_like_person_name(name) or _is_excluded_name(name, excluded_names):
            continue
        name_tokens = _tokens(name)
        overlap = name_tokens & filename_tokens
        if not overlap:
            continue
        score = len(overlap) * 20
        if ai_name and _normalize(name) == _normalize(ai_name):
            score += 30
        if _normalize(name) in normalized_filename:
            score += 50
        if len(overlap) == len(name_tokens):
            score += 20
        candidate_scores.append((score, name))

    if not candidate_scores:
        return None
    candidate_scores.sort(key=lambda item: (-item[0], -len(_tokens(item[1])), item[1].casefold()))
    if len(candidate_scores) > 1 and candidate_scores[0][0] == candidate_scores[1][0]:
        return None
    selected_name = candidate_scores[0][1]
    selected_tokens = _tokens(selected_name)

    folder_candidates: list[tuple[int, Path]] = []
    for client in clients:
        client_tokens = _tokens(client.name)
        normalized_client = _normalize(client.name)
        if not client_tokens:
            continue
        overlap = client_tokens & selected_tokens
        if not overlap:
            continue
        if len(overlap) == 1 and len(selected_tokens) >= 3:
            continue
        score = len(overlap) * 20
        if normalized_client == _normalize(selected_name):
            score += 100
        elif client_tokens.issubset(selected_tokens):
            score += 40
        folder_candidates.append((score, client))
    if folder_candidates:
        folder_candidates.sort(key=lambda item: (-item[0], item[1].name.casefold()))
        if len(folder_candidates) > 1 and folder_candidates[0][0] == folder_candidates[1][0]:
            return None
        return folder_candidates[0][1]

    client_root = path.parent / CLIENTS_FOLDER
    client_root.mkdir(parents=True, exist_ok=True)
    new_folder = client_root / _safe_client_name(selected_name)
    if not new_folder.name:
        return None
    new_folder.mkdir(parents=True, exist_ok=True)
    return new_folder


def _ai_client_name(
    ollama_client,
    text: str,
    filename: str,
    clients: list[Path],
    excluded_names: list[str],
) -> list[str]:
    if ollama_client is None or not text.strip():
        return []
    parties = ollama_client.identify_client_name(
        text,
        filename,
        [client.name for client in clients],
        excluded_names,
    )
    return [party["name"] for party in parties]


def _stable(path: Path) -> bool:
    try:
        first = path.stat()
        if first.st_size == 0:
            return False
        time.sleep(0.2)
        second = path.stat()
    except OSError:
        return False
    return first.st_size == second.st_size and first.st_mtime_ns == second.st_mtime_ns


def _unique_destination(destination: Path) -> Path:
    if not destination.exists():
        return destination
    return destination.with_name(f"{destination.stem}_duplicado{destination.suffix}")


def _move(source: Path, destination: Path) -> Path:
    destination = _unique_destination(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    return destination


def _signature_key(path: Path) -> str:
    name = path.name
    for suffix in SIGNATURE_SUFFIXES:
        if name.casefold().endswith(suffix):
            name = name[: -len(suffix)]
            break
    if name.casefold().endswith(PDF_SUFFIX):
        name = name[: -len(PDF_SUFFIX)]
    return re.sub(r"[^a-z0-9]", "", _normalize(name))


def organize_documents(
    root: Path | str,
    database: Path | str | None = None,
    progress: ProgressCallback | None = None,
    use_ocr: bool = True,
    ollama_client=None,
) -> OrganizationSummary:
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        raise ValueError(f"A pasta de documentos não existe: {root_path}")

    summary = OrganizationSummary()
    log_database = database or CettiDatabase().path
    run_id = new_run_id()

    def report(message: str) -> None:
        append_log(log_database, run_id, message)
        if progress is not None:
            progress(message)

    clients = _client_folders(root_path)
    excluded_names = _attorney_names()
    if excluded_names:
        report(f"Advogado(s) excluído(s) da identificação de cliente: {', '.join(excluded_names)}")
    top_level = sorted((path for path in root_path.iterdir() if path.is_file()), key=lambda path: path.name.casefold())
    pdf_destinations: dict[str, Path] = {}
    supported_suffixes = {PDF_SUFFIX, *SIGNATURE_SUFFIXES, *WORD_SUFFIXES}
    top_level = sorted(
        (
            path for path in root_path.iterdir()
            if path.is_file() and path.suffix.casefold() in supported_suffixes
        ),
        key=lambda path: path.name.casefold(),
    )

    report(f"Encontrados {len(top_level)} arquivo(s) compatíveis na pasta de entrada.")

    def finish_file(path: Path, message: str) -> None:
        status = f"{path.name}: {message}"
        summary.file_statuses.append(status)
        report(status)

    for path in top_level:
        summary.scanned += 1
        report(f"Validando arquivo {summary.scanned}/{len(top_level)}: {path.name}")
        if not _stable(path):
            summary.skipped += 1
            finish_file(path, "aguardando estabilidade; mantido na entrada")
            continue
        suffix = path.suffix.casefold()
        try:
            if suffix in WORD_SUFFIXES:
                destination = _move(path, root_path / WORD_FOLDER / path.name)
                summary.moved += 1
                summary.words_moved += 1
                finish_file(path, f"Word movido para {destination}")
                continue
            if suffix == PDF_SUFFIX:
                report(f"Analisando arquivo: {path.name}")
                extracted = extract_pdf(
                    path,
                    use_ocr=use_ocr,
                    ocr_backend="auto",
                    ollama_client=ollama_client,
                )
                summary.pdfs_analyzed += 1
                method_labels = {
                    "native": "PyMuPDF (texto nativo)",
                    "tesseract": "pytesseract/Tesseract",
                    "glm-ocr": "Ollama glm-ocr",
                }
                methods = ", ".join(
                    method_labels.get(method, method)
                    for method in extracted.methods
                )
                diagnostic = f"{path.name}: extração={methods}"
                summary.diagnostics.append(diagnostic)
                append_log(log_database, run_id, diagnostic)
                if excluded_names:
                    diagnostic = (
                        f"{path.name}: nomes de advogado excluídos="
                        + ", ".join(excluded_names)
                    )
                    summary.diagnostics.append(diagnostic)
                    append_log(log_database, run_id, diagnostic)
                report(f"Métodos usados em {path.name}: {methods}")
                ai_names: list[str] = []
                if ollama_client is not None:
                    try:
                        ai_names = _ai_client_name(
                            ollama_client,
                            extracted.text,
                            path.name,
                            clients,
                            excluded_names,
                        )
                        blocked_names = [
                            name for name in ai_names
                            if _is_excluded_name(name, excluded_names)
                        ]
                        ai_names = [
                            name for name in ai_names
                            if not _is_excluded_name(name, excluded_names)
                        ]
                        diagnostic = (
                            f"{path.name}: Qwen/modelo={ollama_client.config.text_model}; "
                            f"partes retornadas={', '.join(ai_names) or '(nenhuma)'}"
                            + (
                                "; partes de advogado rejeitadas: " + ", ".join(blocked_names)
                                if blocked_names
                                else ""
                            )
                        )
                        summary.diagnostics.append(diagnostic)
                        append_log(log_database, run_id, diagnostic)
                    except Exception as error:
                        diagnostic = (
                            f"{path.name}: Qwen/modelo={ollama_client.config.text_model}; erro={error}"
                        )
                        summary.diagnostics.append(diagnostic)
                        append_log(log_database, run_id, diagnostic)
                        report(f"Qwen não conseguiu interpretar {path.name}: {error}")
                else:
                    diagnostic = (
                        f"{path.name}: Qwen/Ollama não usado (cliente Ollama indisponível ou opção desmarcada)"
                    )
                    summary.diagnostics.append(diagnostic)
                    append_log(log_database, run_id, diagnostic)
                client = _identify_client(
                    path,
                    extracted,
                    clients,
                    ai_names=ai_names,
                    excluded_names=excluded_names,
                )
                extracted_names = _extract_client_names(extracted.text) + _extract_role_names(extracted.text)
                if extracted_names:
                    report(f"Nome extraído do documento: {extracted_names[0]}")
                destination_folder = client or root_path / UNKNOWN_FOLDER
                destination = _move(path, destination_folder / path.name)
                pdf_destinations[_signature_key(path)] = destination
                summary.moved += 1
                if client:
                    summary.identified += 1
                    finish_file(path, f"cliente {client.name} identificado; movido para {destination}")
                else:
                    summary.unknown += 1
                    finish_file(path, f"cliente não identificado; movido para {destination}")
                if ollama_client is not None and ollama_client.audit_log:
                    diagnostic = (
                        f"{path.name}: prompts Ollama:\n"
                        + "\n---\n".join(ollama_client.audit_log)
                    )
                    summary.diagnostics.append(diagnostic)
                    append_log(log_database, run_id, diagnostic)
                    ollama_client.audit_log.clear()
                continue
            if suffix in SIGNATURE_SUFFIXES:
                summary.skipped += 1
                finish_file(path, "assinatura aguardando o PDF correspondente")
                continue
        except Exception as error:
            summary.errors += 1
            message = f"Falha em {path.name}: {error}"
            summary.messages.append(message)
            append_log(log_database, run_id, message)
            finish_file(path, message)

    for path in sorted((item for item in root_path.iterdir() if item.is_file()), key=lambda item: item.name.casefold()):
        if path.suffix.casefold() not in SIGNATURE_SUFFIXES:
            continue
        destination_pdf = pdf_destinations.get(_signature_key(path))
        if destination_pdf is None:
            summary.skipped += 1
            finish_file(path, "assinatura sem PDF processado; mantida na entrada")
            continue
        try:
            destination_folder = (
                destination_pdf.parent
                if destination_pdf.parent.name == UNKNOWN_FOLDER
                else destination_pdf.parent / "Documentos Assinados"
            )
            destination = _move(path, destination_folder / path.name)
            summary.moved += 1
            summary.signatures_moved += 1
            finish_file(path, f"assinatura arquivada em {destination}")
        except Exception as error:
            summary.errors += 1
            message = f"Falha na assinatura {path.name}: {error}"
            summary.messages.append(message)
            append_log(log_database, run_id, message)
            finish_file(path, message)

    report("Atualizando o índice SQLite...")
    index_documents(root_path, database)
    report("Varredura e organização concluídas.")
    return summary
