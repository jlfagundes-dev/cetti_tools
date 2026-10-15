from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cetti_extracao import ExtractionUnavailable, extract_pdf
from cetti_ia_local import (
    LocalAIError,
    OllamaClient,
    OllamaConfig,
    validate_interpretation,
)


class Etapa6Tests(unittest.TestCase):
    def _create_pdf(self, path: Path, text: str = "") -> None:
        import pymupdf

        document = pymupdf.open()
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
        document.save(path)
        document.close()

    def test_texto_nativo_nao_chama_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "nativo.pdf"
            self._create_pdf(path, "Texto nativo")
            with patch("cetti_extracao._ocr_page_tesseract") as ocr:
                result = extract_pdf(path)
            ocr.assert_not_called()
            self.assertEqual(result.pages[0].method, "native")
            self.assertFalse(result.review_required)

    def test_tesseract_e_padrao_e_glm_faz_fallback_com_baixa_confianca(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "escaneado.pdf"
            self._create_pdf(path)
            client = object()
            with patch("cetti_extracao._ocr_page_tesseract", return_value=("texto fraco", 40.0)), patch(
                "cetti_extracao._ocr_page_glm", return_value="texto glm"
            ) as glm:
                result = extract_pdf(path, ollama_client=client)
            glm.assert_called_once()
            self.assertEqual(result.pages[0].method, "glm-ocr")
            self.assertEqual(result.pages[0].text, "texto glm")
            self.assertTrue(result.review_required)

    def test_tesseract_com_confianca_suficiente_nao_chama_glm(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "escaneado.pdf"
            self._create_pdf(path)
            with patch("cetti_extracao._ocr_page_tesseract", return_value=("texto bom", 85.0)), patch(
                "cetti_extracao._ocr_page_glm"
            ) as glm:
                result = extract_pdf(path, ollama_client=object())
            glm.assert_not_called()
            self.assertEqual(result.pages[0].method, "tesseract")
            self.assertFalse(result.review_required)

    def test_extracao_informa_dependencia_ausente_sem_fingir_resultado(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "arquivo.pdf"
            path.write_bytes(b"nao e um pdf")
            with patch("cetti_extracao._load_pymupdf", side_effect=ExtractionUnavailable("ausente")):
                with self.assertRaises(ExtractionUnavailable):
                    extract_pdf(path)

    def test_validacao_preserva_valor_e_pagina_de_origem(self) -> None:
        payload = {
            "client": {"value": "Maria Silva", "page": 1},
            "document_type": {"value": "Peticao", "page": 2},
            "process_number": {"value": None, "page": None},
            "document_date": {"value": "2026-10-15", "page": 1},
        }
        result = validate_interpretation(json.dumps(payload), 2)
        self.assertEqual(result.client.value, "Maria Silva")
        self.assertEqual(result.document_type.page, 2)
        self.assertIsNone(result.process_number.value)

    def test_resposta_invalida_ou_pagina_fora_do_pdf_e_rejeitada(self) -> None:
        incomplete = {"client": {"value": "Maria", "page": 1}}
        with self.assertRaises(LocalAIError):
            validate_interpretation(json.dumps(incomplete), 1)

        payload = {
            "client": {"value": "Maria", "page": 2},
            "document_type": {"value": None, "page": None},
            "process_number": {"value": None, "page": None},
            "document_date": {"value": None, "page": None},
        }
        with self.assertRaises(LocalAIError):
            validate_interpretation(json.dumps(payload), 1)

    def test_ollama_recusa_endpoint_externo_e_nao_baixa_modelos(self) -> None:
        with self.assertRaises(ValueError):
            OllamaClient(OllamaConfig(base_url="https://api.externa.example"))
        client = OllamaClient(OllamaConfig(base_url="http://127.0.0.1:11434"))
        with patch.object(client, "_request", side_effect=OSError("offline")):
            self.assertFalse(client.is_available())


if __name__ == "__main__":
    unittest.main()
