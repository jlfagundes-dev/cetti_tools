from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from cetti_db import CettiDatabase
from cetti_indexador import index_documents


class Etapa3Tests(unittest.TestCase):
    def test_cria_reabre_e_indexa_sem_mover_arquivos(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "Documentos com acentos"
            database = base / "estado" / "cetti.sqlite3"
            document = root / "01_CLIENTES" / "Jose da Silva" / "Peticao" / "peticao.pdf"
            document.parent.mkdir(parents=True)
            document.write_bytes(b"conteudo ficticio")
            original = document.read_bytes()

            first = index_documents(root, database)
            self.assertEqual(first.new, 1)
            self.assertEqual(first.removed, 0)
            self.assertTrue(document.exists())
            self.assertEqual(document.read_bytes(), original)

            with CettiDatabase(database) as db:
                self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 1)
                self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0], 1)
                self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0], 1)

            second = index_documents(root, database)
            self.assertEqual(second.new, 0)
            self.assertEqual(second.unchanged, 1)

    def test_detecta_modificacao_renomeacao_e_remocao(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "raiz"
            database = base / "db.sqlite3"
            original = root / "documento.txt"
            root.mkdir()
            original.write_text("um", encoding="utf-8")

            self.assertEqual(index_documents(root, database).new, 1)
            original.write_text("dois", encoding="utf-8")
            self.assertEqual(index_documents(root, database).modified, 1)

            renamed = root / "documento-renomeado.txt"
            original.rename(renamed)
            result = index_documents(root, database)
            self.assertEqual(result.renamed, 1)
            self.assertEqual(result.new, 0)

            renamed.unlink()
            result = index_documents(root, database)
            self.assertEqual(result.removed, 1)

            connection = sqlite3.connect(database)
            try:
                status = connection.execute(
                    "SELECT status FROM documents WHERE relative_path = ?",
                    ("documento-renomeado.txt",),
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(status, "removed")

    def test_rejeita_banco_dentro_da_raiz_de_documentos(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "arquivo.txt").write_text("teste", encoding="utf-8")
            with self.assertRaises(ValueError):
                index_documents(root, root / "cetti.sqlite3")


if __name__ == "__main__":
    unittest.main()
