from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cetti_busca import parse_query, require_inside_root, search_documents
from cetti_db import CettiDatabase
from cetti_indexador import index_documents


class Etapa4Tests(unittest.TestCase):
    def _base_index(self, base: Path) -> tuple[Path, Path]:
        root = base / "Documentos"
        database = base / "estado" / "cetti.sqlite3"
        first = root / "01_CLIENTES" / "Maria Silva" / "Peticao" / "peticao-1234567.pdf"
        second = root / "01_CLIENTES" / "Maria Souza" / "Contrato" / "contrato.pdf"
        first.parent.mkdir(parents=True)
        second.parent.mkdir(parents=True)
        first.write_bytes(b"peticao")
        second.write_bytes(b"contrato")
        index_documents(root, database)
        with CettiDatabase(database) as db:
            db.conn.execute(
                "UPDATE documents SET process_number = ?, document_date = ? WHERE file_name = ?",
                ("1234567", "2026-10-15", first.name),
            )
            db.conn.commit()
        return root, database

    def test_interpreta_consulta_e_filtra_por_processo_e_mes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, database = self._base_index(Path(temporary))
            criteria = parse_query("Encontre a petição inicial do processo 1234567 em outubro de 2026")
            self.assertEqual(criteria.process_number, "1234567")
            self.assertEqual(criteria.month, 10)
            self.assertEqual(criteria.year, 2026)
            results = search_documents(criteria, root, database)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].file_name, "peticao-1234567.pdf")

    def test_clientes_semelhantes_sao_retornados_para_escolha(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, database = self._base_index(Path(temporary))
            results = search_documents("documentos da Maria", root, database)
            self.assertEqual(len(results), 2)
            self.assertEqual({result.client_name for result in results}, {"Maria Silva", "Maria Souza"})

    def test_caminho_fora_da_raiz_e_rejeitado(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "Documentos"
            root.mkdir()
            inside = root / "arquivo.pdf"
            inside.write_bytes(b"x")
            self.assertEqual(require_inside_root(inside, root), inside.resolve())
            with self.assertRaises(ValueError):
                require_inside_root(base / "fora.pdf", root)
            with self.assertRaises(ValueError):
                require_inside_root(root / ".." / "fora.pdf", root)


if __name__ == "__main__":
    unittest.main()
