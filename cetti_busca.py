from __future__ import annotations

import calendar
import os
import re
import subprocess
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from cetti_db import CettiDatabase, normalize_name

MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}
DOCUMENT_TYPES = {
    "peticao inicial": "peticao",
    "peticao": "peticao",
    "contrato": "contrato",
    "oficio": "oficio",
    "oficio": "oficio",
    "comprovante": "comprovante",
    "rg": "rg",
}
STOP_WORDS = {
    "a", "as", "ao", "aos", "com", "da", "das", "de", "do", "dos", "e",
    "em", "encontre", "localize", "mostre", "o", "os", "para", "por", "um",
    "uma", "documento", "documentos", "processo", "mes", "mês", "de", "ano",
}


@dataclass(frozen=True)
class SearchCriteria:
    terms: tuple[str, ...] = ()
    process_number: str | None = None
    document_type: str | None = None
    month: int | None = None
    year: int | None = None


@dataclass(frozen=True)
class SearchResult:
    document_id: int
    path: Path
    file_name: str
    client_name: str | None
    document_type: str | None
    process_number: str | None
    document_date: str | None
    score: int
    matched_page: int | None = None
    snippet: str | None = None
    match_source: str = "metadata"


def _without_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _clean_process_number(value: str) -> str:
    return re.sub(r"\D", "", value)


def parse_query(text: str) -> SearchCriteria:
    normalized = normalize_name(text)
    ascii_text = _without_accents(normalized)
    process_match = re.search(r"\b\d{5,}\b", ascii_text)
    process_number = process_match.group(0) if process_match else None
    year_match = re.search(r"\b(20\d{2})\b", ascii_text)
    year = int(year_match.group(1)) if year_match else None
    month = next((number for name, number in MONTHS.items() if name in ascii_text), None)

    document_type = None
    document_type_terms: set[str] = set()
    for label, value in DOCUMENT_TYPES.items():
        if _without_accents(label) in ascii_text:
            document_type = value
            document_type_terms = set(_without_accents(label).split())
            break

    terms = []
    for token in re.findall(r"[\w]+", ascii_text, flags=re.UNICODE):
        if token in STOP_WORDS or token.isdigit() or len(token) < 2:
            continue
        if token in document_type_terms:
            continue
        if token in MONTHS or (year and token == str(year)):
            continue
        terms.append(token)
    return SearchCriteria(tuple(dict.fromkeys(terms)), process_number, document_type, month, year)


def _date_matches(value: str | None, month: int | None, year: int | None) -> bool:
    if month is None and year is None:
        return True
    if not value:
        return False
    match = re.match(r"^(\d{4})-(\d{2})", value)
    if not match:
        return False
    return (year is None or int(match.group(1)) == year) and (month is None or int(match.group(2)) == month)


def search_documents(
    query: str | SearchCriteria,
    root: Path | str,
    database: Path | str | None = None,
) -> list[SearchResult]:
    criteria = parse_query(query) if isinstance(query, str) else query
    root_path = Path(root).expanduser().resolve()
    results: list[SearchResult] = []
    with CettiDatabase(database) as db:
        rows = db.conn.execute(
            """
            SELECT documents.*, clients.name AS client_name
            FROM documents
            LEFT JOIN clients ON clients.id = documents.client_id
            WHERE documents.status = ?
            """,
            ("active",),
        ).fetchall()
        content_matches: dict[int, tuple[set[str], int, str]] = {}
        if criteria.terms:
            for term in criteria.terms:
                safe_term = re.sub(r'["*]', " ", term).strip()
                if safe_term:
                    for match in db.search_document_text(f'"{safe_term}"*'):
                        document_id = int(match["document_id"])
                        matched_terms, page, snippet = content_matches.get(
                            document_id, (set(), int(match["page_number"]), str(match["text"]))
                        )
                        content_matches[document_id] = (
                            matched_terms | {term},
                            page,
                            snippet,
                        )
        content_threshold = max(1, (len(criteria.terms) + 1) // 2)
        active_names = {
            normalize_name(row["file_name"])
            for row in rows
            if "_duplicado" not in normalize_name(row["file_name"])
        }
        for row in rows:
            searchable = normalize_name(
                " ".join(
                    value or ""
                    for value in (
                        row["file_name"],
                        row["relative_path"],
                        row["client_name"],
                        row["document_type"],
                        row["process_number"],
                    )
                )
            )
            normalized_process = _clean_process_number(row["process_number"] or "")
            if criteria.process_number and criteria.process_number not in normalized_process:
                continue
            if criteria.document_type and not (
                criteria.document_type in normalize_name(row["document_type"] or "")
                or criteria.document_type in searchable
            ):
                continue
            if not _date_matches(row["document_date"], criteria.month, criteria.year):
                continue
            metadata_match = all(term in searchable for term in criteria.terms)
            content_data = content_matches.get(int(row["id"]))
            content_match = content_data is not None and len(content_data[0]) >= content_threshold
            if criteria.terms and not metadata_match and not content_match:
                continue
            score = sum(term in searchable for term in criteria.terms) * 10
            if content_match:
                score += len(content_data[0]) * 25
            filename_terms = sum(
                term in normalize_name(row["file_name"]) for term in criteria.terms
            )
            score += filename_terms * 40
            if row["relative_path"].casefold().startswith("01_clientes\\") or row[
                "relative_path"
            ].casefold().startswith("01_clientes/"):
                score += 20
            normalized_filename = normalize_name(row["file_name"])
            if "_duplicado" in normalized_filename:
                original_name = normalized_filename.replace("_duplicado", "")
                if original_name in active_names:
                    continue
                score -= 80
            if criteria.process_number:
                score += 30
            if criteria.document_type:
                score += 20
            if criteria.month or criteria.year:
                score += 15
            _, matched_page, snippet = content_data or (set(), None, None)
            sources = []
            if metadata_match and criteria.terms:
                sources.append("metadados")
            if content_match:
                sources.append("conteudo")
            results.append(
                SearchResult(
                    document_id=int(row["id"]),
                    path=root_path / Path(row["relative_path"]),
                    file_name=row["file_name"],
                    client_name=row["client_name"],
                    document_type=row["document_type"],
                    process_number=row["process_number"],
                    document_date=row["document_date"],
                    score=score,
                    matched_page=matched_page,
                    snippet=snippet,
                    match_source=" + ".join(sources) or "filtro",
                )
            )
    return sorted(results, key=lambda result: (-result.score, str(result.path).casefold()))


def require_inside_root(path: Path | str, root: Path | str) -> Path:
    root_path = Path(root).expanduser().resolve()
    candidate = Path(path).expanduser().resolve(strict=False)
    try:
        candidate.relative_to(root_path)
    except ValueError as error:
        raise ValueError("O caminho solicitado esta fora da raiz autorizada.") from error
    return candidate


def _launch(command: list[str]) -> None:
    subprocess.Popen(command, close_fds=True)


def open_document(path: Path | str, root: Path | str) -> Path:
    candidate = require_inside_root(path, root)
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    if os.name == "nt":
        _launch(["explorer.exe", str(candidate)])
    elif os.uname().sysname == "Darwin":
        _launch(["open", str(candidate)])
    else:
        _launch(["xdg-open", str(candidate)])
    return candidate


def open_containing_folder(path: Path | str, root: Path | str) -> Path:
    candidate = require_inside_root(path, root)
    folder = candidate if candidate.is_dir() else candidate.parent
    if os.name == "nt":
        _launch(["explorer.exe", str(folder)])
    elif os.uname().sysname == "Darwin":
        _launch(["open", str(folder)])
    else:
        _launch(["xdg-open", str(folder)])
    return folder


def select_in_explorer(path: Path | str, root: Path | str) -> Path:
    candidate = require_inside_root(path, root)
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    if os.name == "nt":
        _launch(["explorer.exe", "/select,", str(candidate)])
    else:
        open_containing_folder(candidate, root)
    return candidate
