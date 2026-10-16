from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from cetti_config import load_project_environment
from cetti_db import CettiDatabase

load_project_environment()

IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".cetti",
    "node_modules",
}
IGNORED_SUFFIXES = {".tmp", ".part", ".partial", ".crdownload"}
CLIENT_ROOTS = {"01_CLIENTES", "CLIENTES", "01_NAO_PROTOCOLADO", "02_PROTOCOLADO"}


@dataclass(frozen=True)
class IndexConfig:
    root: Path
    database: Path


@dataclass
class IndexSummary:
    scanned: int = 0
    new: int = 0
    modified: int = 0
    unchanged: int = 0
    renamed: int = 0
    removed: int = 0
    ignored: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "scanned": self.scanned,
            "new": self.new,
            "modified": self.modified,
            "unchanged": self.unchanged,
            "renamed": self.renamed,
            "removed": self.removed,
            "ignored": self.ignored,
        }


def default_root() -> Path:
    configured = os.getenv("CETTI_ROOT")
    if configured:
        return Path(configured).expanduser()
    for name in ("Documents", "Documentos"):
        candidate = Path.home() / name
        if candidate.exists():
            return candidate
    return Path.home() / "Documents"


def resolve_config(root: Path | str | None = None, database: Path | str | None = None) -> IndexConfig:
    root_path = Path(root).expanduser() if root else default_root()
    database_path = Path(database).expanduser() if database else CettiDatabase().path
    root_path = root_path.resolve()
    database_path = database_path.resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise ValueError(f"A raiz de documentos nao existe ou nao e uma pasta: {root_path}")
    if database_path == root_path or root_path in database_path.parents:
        raise ValueError("O banco SQLite deve ficar fora da raiz de documentos.")
    return IndexConfig(root_path, database_path)


def iter_files(root: Path, database: Path, summary: IndexSummary) -> Iterator[Path]:
    pending = [root]
    while pending:
        current = pending.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            summary.ignored += 1
            continue
        for entry in entries:
            path = Path(entry.path)
            if entry.is_symlink():
                summary.ignored += 1
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    if entry.name.casefold() in {name.casefold() for name in IGNORED_DIRECTORIES}:
                        summary.ignored += 1
                    else:
                        pending.append(path)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    summary.ignored += 1
                    continue
            except OSError:
                summary.ignored += 1
                continue
            if entry.name.startswith("~$") or path.suffix.casefold() in IGNORED_SUFFIXES:
                summary.ignored += 1
                continue
            try:
                if path.resolve() == database:
                    summary.ignored += 1
                    continue
            except OSError:
                summary.ignored += 1
                continue
            yield path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def document_context(root: Path, path: Path) -> tuple[str | None, str | None]:
    parts = path.relative_to(root).parts
    if len(parts) < 2 or parts[0].casefold() not in {item.casefold() for item in CLIENT_ROOTS}:
        return None, None
    client_name = parts[1]
    document_type = parts[2] if len(parts) >= 4 else None
    return client_name, document_type


def document_data(root: Path, path: Path, digest: str) -> dict[str, object]:
    stat = path.stat()
    relative_path = path.relative_to(root).as_posix()
    client_name, document_type = document_context(root, path)
    return {
        "relative_path": relative_path,
        "file_name": path.name,
        "extension": path.suffix.casefold(),
        "document_type": document_type,
        "client_name": client_name,
        "size_bytes": stat.st_size,
        "modified_ns": stat.st_mtime_ns,
        "sha256": digest,
    }


def index_documents(
    root: Path | str | None = None,
    database: Path | str | None = None,
) -> IndexSummary:
    config = resolve_config(root, database)
    summary = IndexSummary()
    with CettiDatabase(config.database) as db:
        seen_paths: set[str] = set()
        for path in iter_files(config.root, config.database, summary):
            try:
                relative_path = path.relative_to(config.root).as_posix()
                existing = db.find_by_path(relative_path)
                stat = path.stat()
                if (
                    existing is not None
                    and existing["status"] == "active"
                    and existing["size_bytes"] == stat.st_size
                    and existing["modified_ns"] == stat.st_mtime_ns
                ):
                    seen_paths.add(relative_path)
                    summary.scanned += 1
                    summary.unchanged += 1
                    continue
                data = document_data(config.root, path, sha256_file(path))
                if existing is None:
                    matches = db.find_active_by_hash(data["sha256"])
                    if len(matches) == 1:
                        db.rename_document(int(matches[0]["id"]), data)
                        db.record_operation("rename", data["relative_path"], {"from": matches[0]["relative_path"]})
                        summary.renamed += 1
                    else:
                        action = db.upsert_document(data)
                        summary.new += action == "new"
                        summary.modified += action == "modified"
                else:
                    action = db.upsert_document(data)
                    summary.new += action == "new"
                    summary.modified += action in {"modified", "restored"}
                seen_paths.add(relative_path)
                summary.scanned += 1
            except (FileNotFoundError, PermissionError, OSError):
                summary.ignored += 1
        summary.removed = db.mark_removed(seen_paths)
        if summary.removed:
            db.record_operation("remove", details={"count": summary.removed})
        db.record_operation("index", details=summary.as_dict())
        db.commit()
    return summary


if __name__ == "__main__":
    result = index_documents()
    print(result.as_dict())
