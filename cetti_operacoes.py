from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cetti_busca import require_inside_root
from cetti_db import CettiDatabase
from cetti_indexador import IndexSummary, index_documents


@dataclass(frozen=True)
class MoveResult:
    operation_id: str
    source: Path
    destination: Path
    index_summary: IndexSummary


class MoveRecoveryError(RuntimeError):
    pass


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _record(db_path: Path | str, operation: str, relative_path: str, details: dict[str, Any]) -> None:
    with CettiDatabase(db_path) as db:
        db.record_operation(operation, relative_path, details)
        db.commit()


def move_document(
    source: Path | str,
    destination: Path | str,
    root: Path | str,
    database: Path | str | None = None,
) -> MoveResult:
    root_path = Path(root).expanduser().resolve()
    source_path = require_inside_root(source, root_path)
    destination_path = require_inside_root(destination, root_path)
    if source_path == destination_path:
        raise ValueError("A origem e o destino da movimentacao devem ser diferentes.")
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if destination_path.exists():
        raise FileExistsError(f"O destino ja existe e nao sera sobrescrito: {destination_path}")

    database_path = CettiDatabase(database).path if database else CettiDatabase().path
    operation_id = uuid.uuid4().hex
    details = {
        "operation_id": operation_id,
        "source": _relative(source_path, root_path),
        "destination": _relative(destination_path, root_path),
    }
    _record(database_path, "move_started", details["source"], details)

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if destination_path.exists():
            raise FileExistsError(f"O destino ja existe e nao sera sobrescrito: {destination_path}")
        shutil.move(str(source_path), str(destination_path))
    except Exception as error:
        _record(database_path, "move_failed", details["source"], {**details, "error": str(error)})
        raise

    try:
        summary = index_documents(root_path, database_path)
    except Exception as error:
        try:
            if destination_path.exists() and not source_path.exists():
                source_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination_path), str(source_path))
            index_documents(root_path, database_path)
        except Exception as recovery_error:
            raise MoveRecoveryError(
                "A atualizacao do indice falhou e o rollback da movimentacao tambem falhou."
            ) from recovery_error
        _record(database_path, "move_rolled_back", details["source"], {**details, "error": str(error)})
        raise

    _record(database_path, "move_completed", details["destination"], {**details, "summary": summary.as_dict()})
    return MoveResult(operation_id, source_path, destination_path, summary)


def recover_move(
    source: Path | str,
    destination: Path | str,
    root: Path | str,
    database: Path | str | None = None,
) -> IndexSummary:
    root_path = Path(root).expanduser().resolve()
    source_path = require_inside_root(source, root_path)
    destination_path = require_inside_root(destination, root_path)
    if source_path.exists() and destination_path.exists():
        raise MoveRecoveryError("A origem e o destino existem; a recuperacao exige revisao humana.")
    summary = index_documents(root_path, database)
    database_path = CettiDatabase(database).path if database else CettiDatabase().path
    state = "source" if source_path.exists() else "destination" if destination_path.exists() else "neither"
    _record(
        database_path,
        "move_recovered",
        _relative(destination_path if destination_path.exists() else source_path, root_path),
        {"source": _relative(source_path, root_path), "destination": _relative(destination_path, root_path), "state": state},
    )
    return summary
