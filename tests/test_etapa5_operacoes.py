from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cetti_busca import search_documents
from cetti_db import CettiDatabase
from cetti_indexador import index_documents
from cetti_operacoes import MoveRecoveryError, move_document, recover_move


class Etapa5Tests(unittest.TestCase):
    def _indexed_file(self, base: Path) -> tuple[Path, Path, Path]:
        root = base / "Documentos"
        database = base / "estado" / "cetti.sqlite3"
        source = root / "entrada" / "peticao.pdf"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"arquivo ficticio")
        index_documents(root, database)
        return root, database, source

    def test_move_atualiza_o_indice_sem_sobrescrever(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, database, source = self._indexed_file(Path(temporary))
            destination = root / "01_CLIENTES" / "Maria Silva" / "Peticao" / source.name
            result = move_document(source, destination, root, database)

            self.assertFalse(source.exists())
            self.assertTrue(destination.exists())
            indexed = search_documents("peticao", root, database)
            self.assertEqual(len(indexed), 1)
            self.assertEqual(indexed[0].path, destination.resolve())
            with CettiDatabase(database) as db:
                operations = [row[0] for row in db.conn.execute("SELECT operation FROM operations")]
            self.assertIn("move_completed", operations)

            destination.write_bytes(b"arquivo existente")
            second = root / "outro" / source.name
            second.parent.mkdir(parents=True)
            second.write_bytes(b"segunda origem")
            with self.assertRaises(FileExistsError):
                move_document(second, destination, root, database)
            self.assertEqual(destination.read_bytes(), b"arquivo existente")
            self.assertTrue(second.exists())

    def test_falha_no_indice_faz_rollback_do_arquivo(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, database, source = self._indexed_file(Path(temporary))
            destination = root / "destino" / source.name
            with patch("cetti_operacoes.index_documents", side_effect=RuntimeError("falha simulada")):
                with self.assertRaises(RuntimeError):
                    move_document(source, destination, root, database)
            self.assertTrue(source.exists())
            self.assertFalse(destination.exists())

    def test_recuperacao_reindexa_estado_sem_mover_arquivos(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, database, source = self._indexed_file(Path(temporary))
            destination = root / "destino" / source.name
            destination.parent.mkdir()
            source.rename(destination)
            summary = recover_move(source, destination, root, database)
            self.assertGreaterEqual(summary.scanned, 1)
            self.assertFalse(source.exists())
            self.assertTrue(destination.exists())

    def test_recuperacao_bloqueia_duas_copias(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, database, source = self._indexed_file(Path(temporary))
            destination = root / "destino" / source.name
            destination.parent.mkdir()
            destination.write_bytes(b"outra copia")
            with self.assertRaises(MoveRecoveryError):
                recover_move(source, destination, root, database)


if __name__ == "__main__":
    unittest.main()
