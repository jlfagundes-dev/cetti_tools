from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4


def log_path(database: Path | str) -> Path:
    return Path(database).expanduser().resolve().parent / "logs" / "cetti_organizacao.log"


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]


def append_log(database: Path | str, run_id: str, message: str) -> None:
    destination = log_path(database)
    destination.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] [{run_id}] {message}\n")


def read_log(database: Path | str, limit: int = 200) -> str:
    destination = log_path(database)
    if not destination.is_file():
        return ""
    lines = destination.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[-limit:])
