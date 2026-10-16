from __future__ import annotations

import json
import os
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from cetti_config import load_project_environment


load_project_environment()

SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(normalized.casefold().split())


def default_database_path() -> Path:
    configured = os.getenv("CETTI_DB_PATH")
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.getenv("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "Cetti" / "Arquivista" / "cetti.sqlite3"


class CettiDatabase:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path).expanduser() if path else default_database_path()
        self.connection: sqlite3.Connection | None = None

    def __enter__(self) -> "CettiDatabase":
        self.open()
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    def open(self) -> sqlite3.Connection:
        if self.connection is not None:
            return self.connection
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 5000")
        self.initialize()
        return self.connection

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    @property
    def conn(self) -> sqlite3.Connection:
        return self.open()

    def initialize(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY,
                client_id INTEGER REFERENCES clients(id) ON UPDATE CASCADE ON DELETE SET NULL,
                relative_path TEXT NOT NULL UNIQUE,
                file_name TEXT NOT NULL,
                extension TEXT NOT NULL,
                document_type TEXT,
                process_number TEXT,
                document_date TEXT,
                size_bytes INTEGER NOT NULL,
                modified_ns INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                first_seen_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                removed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS operations (
                id INTEGER PRIMARY KEY,
                operation TEXT NOT NULL,
                relative_path TEXT,
                details TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_clients_normalized_name
                ON clients(normalized_name);
            CREATE INDEX IF NOT EXISTS idx_documents_client_id
                ON documents(client_id);
            CREATE INDEX IF NOT EXISTS idx_documents_status
                ON documents(status);
            CREATE INDEX IF NOT EXISTS idx_documents_sha256
                ON documents(sha256);
            CREATE INDEX IF NOT EXISTS idx_documents_type
                ON documents(document_type);
            CREATE INDEX IF NOT EXISTS idx_documents_process_number
                ON documents(process_number);
            """
        )
        row = self.conn.execute(
            "SELECT value FROM schema_meta WHERE key = ?", ("schema_version",)
        ).fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO schema_meta(key, value) VALUES(?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )
        elif int(row["value"]) > SCHEMA_VERSION:
            raise RuntimeError("O banco foi criado por uma versão mais nova do Arquivista.")
        self.conn.commit()

    def record_operation(
        self,
        operation: str,
        relative_path: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO operations(operation, relative_path, details, created_at) VALUES(?, ?, ?, ?)",
            (operation, relative_path, json.dumps(details or {}, ensure_ascii=False), utc_now()),
        )

    def get_or_create_client(self, name: str) -> int:
        clean_name = name.strip()
        normalized = normalize_name(clean_name)
        row = self.conn.execute(
            "SELECT id FROM clients WHERE name = ? AND normalized_name = ?",
            (clean_name, normalized),
        ).fetchone()
        if row is not None:
            return int(row["id"])
        now = utc_now()
        cursor = self.conn.execute(
            "INSERT INTO clients(name, normalized_name, created_at, updated_at) VALUES(?, ?, ?, ?)",
            (clean_name, normalized, now, now),
        )
        return int(cursor.lastrowid)

    def find_clients(self, term: str) -> list[sqlite3.Row]:
        pattern = f"%{normalize_name(term)}%"
        return list(
            self.conn.execute(
                "SELECT id, name, normalized_name FROM clients WHERE normalized_name LIKE ? ORDER BY name",
                (pattern,),
            )
        )

    def find_by_path(self, relative_path: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM documents WHERE relative_path = ?", (relative_path,)
        ).fetchone()

    def find_active_by_hash(self, sha256: str) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM documents WHERE sha256 = ? AND status = 'active' ORDER BY id",
                (sha256,),
            )
        )

    def upsert_document(self, data: dict[str, Any]) -> str:
        now = utc_now()
        existing = self.find_by_path(data["relative_path"])
        client_id = None
        if data.get("client_name"):
            client_id = self.get_or_create_client(data["client_name"])

        values = (
            client_id,
            data["relative_path"],
            data["file_name"],
            data["extension"],
            data.get("document_type"),
            data.get("process_number"),
            data.get("document_date"),
            data["size_bytes"],
            data["modified_ns"],
            data["sha256"],
            now,
        )
        if existing is None:
            self.conn.execute(
                """
                INSERT INTO documents(
                    client_id, relative_path, file_name, extension, document_type,
                    process_number, document_date, size_bytes, modified_ns, sha256,
                    status, first_seen_at, updated_at, removed_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, NULL)
                """,
                (*values, now),
            )
            return "new"

        changed = any(
            existing[key] != value
            for key, value in {
                "client_id": client_id,
                "file_name": data["file_name"],
                "extension": data["extension"],
                "document_type": data.get("document_type"),
                "process_number": data.get("process_number"),
                "document_date": data.get("document_date"),
                "size_bytes": data["size_bytes"],
                "modified_ns": data["modified_ns"],
                "sha256": data["sha256"],
                "status": "active",
            }.items()
        )
        if changed:
            self.conn.execute(
                """
                UPDATE documents SET client_id = ?, file_name = ?, extension = ?,
                    document_type = ?, process_number = ?, document_date = ?,
                    size_bytes = ?, modified_ns = ?, sha256 = ?, status = 'active',
                    updated_at = ?, removed_at = NULL WHERE id = ?
                """,
                (
                    client_id,
                    data["file_name"],
                    data["extension"],
                    data.get("document_type"),
                    data.get("process_number"),
                    data.get("document_date"),
                    data["size_bytes"],
                    data["modified_ns"],
                    data["sha256"],
                    now,
                    existing["id"],
                ),
            )
            return "modified" if existing["status"] == "active" else "restored"
        return "unchanged"

    def rename_document(self, document_id: int, data: dict[str, Any]) -> None:
        client_id = None
        if data.get("client_name"):
            client_id = self.get_or_create_client(data["client_name"])
        self.conn.execute(
            """
            UPDATE documents SET client_id = ?, relative_path = ?, file_name = ?,
                extension = ?, document_type = ?, size_bytes = ?, modified_ns = ?,
                sha256 = ?, status = 'active', updated_at = ?, removed_at = NULL
            WHERE id = ?
            """,
            (
                client_id,
                data["relative_path"],
                data["file_name"],
                data["extension"],
                data.get("document_type"),
                data["size_bytes"],
                data["modified_ns"],
                data["sha256"],
                utc_now(),
                document_id,
            ),
        )

    def mark_removed(self, seen_paths: Iterable[str]) -> int:
        seen = set(seen_paths)
        active = self.conn.execute(
            "SELECT id, relative_path FROM documents WHERE status = 'active'"
        ).fetchall()
        removed = 0
        now = utc_now()
        for row in active:
            if row["relative_path"] not in seen:
                self.conn.execute(
                    "UPDATE documents SET status = 'removed', removed_at = ?, updated_at = ? WHERE id = ?",
                    (now, now, row["id"]),
                )
                removed += 1
        return removed

    def commit(self) -> None:
        self.conn.commit()
