from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cetti_extracao import ExtractionResult, ExtractionUnavailable, PageText, extract_pdf
from cetti_ia_local import (
    LocalAIError,
    OllamaClient,
    OllamaConfig,
    validate_interpretation,
)
from cetti_organizacao import _identify_client, _is_excluded_name


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

    def test_qwen_desativa_raciocinio_e_limita_geracao(self) -> None:
        client = OllamaClient(OllamaConfig())
        with patch.object(
            client,
            "_request",
            return_value={"response": '{"client_name": null, "reason": "sem evidencia"}'},
        ) as request:
            result = client.generate(
                "Identifique o cliente.",
                model="qwen3:4b",
                json_response=True,
            )

        self.assertIn('"client_name"', result)
        payload = request.call_args.args[2]
        self.assertFalse(payload["think"])
        self.assertEqual(payload["options"], {"num_predict": 256, "temperature": 0})
        self.assertEqual(payload["format"], "json")

    def test_identificacao_limita_resposta_do_qwen(self) -> None:
        client = OllamaClient(OllamaConfig())
        with patch.object(
            client,
            "_request",
            return_value={"response": '{"client_name": null, "reason": "sem evidencia"}'},
        ) as request:
            client.identify_client_name("Texto inicial", "documento.pdf", [])

        self.assertEqual(request.call_args.args[2]["options"]["num_predict"], 128)

    def test_interpretacao_de_busca_valida_termos_e_limita_quantidade(self) -> None:
        client = OllamaClient(OllamaConfig())
        terms = [f"termo-{number}" for number in range(20)]
        response = json.dumps({"terms": terms, "explanation": "busca por documento"})
        with patch.object(
            client,
            "_request",
            return_value={"response": response},
        ):
            interpretation = client.interpret_search_query(
                "carteira de trabalho do Erasmo"
            )

        self.assertEqual(len(interpretation.terms), 12)
        self.assertEqual(interpretation.terms[0], "termo-0")
        self.assertEqual(interpretation.explanation, "busca por documento")

    def test_identificacao_retorna_todas_as_partes_com_papel(self) -> None:
        client = OllamaClient(OllamaConfig())
        with patch.object(
            client,
            "_request",
            return_value={
                "response": (
                    '{"parties": ['
                    '{"name": "Hevelly dos Santos Ruas", "role": "autora"},'
                    '{"name": "Eltech Montagem Eletrica LTDA", "role": "reu"}'
                    '], "reason": "partes encontradas"}'
                )
            },
        ):
            parties = client.identify_client_name("Texto", "Sentenca Eltch.pdf", [])

        self.assertEqual(
            parties,
            [
                {"name": "Hevelly dos Santos Ruas", "role": "autora"},
                {"name": "Eltech Montagem Eletrica LTDA", "role": "reu"},
            ],
        )

    def test_prompt_informa_advogado_que_nao_pode_ser_cliente(self) -> None:
        client = OllamaClient(OllamaConfig())
        with patch.object(
            client,
            "_request",
            return_value={"response": '{"client_name": null, "reason": "advogado"}'},
        ) as request:
            client.identify_client_name(
                "Texto do documento",
                "decisao.pdf",
                [],
                ["DR. GENELUCIO"],
            )

        self.assertIn("DR. GENELUCIO", request.call_args.args[2]["prompt"])
        self.assertIn("NUNCA podem ser clientes", request.call_args.args[2]["prompt"])

    def test_nome_completo_do_advogado_e_excluido(self) -> None:
        self.assertTrue(
            _is_excluded_name(
                "GENELUCIO FABIO ALVES CARNEIRO VIEIRA",
                ["DR. GENELUCIO"],
            )
        )

    def test_nome_do_arquivo_prioriza_sobrenome_ao_comparar_pastas(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            clients = [
                base / "João Paulo Pires",
                base / "João Arthur Siqueira Martins",
            ]
            path = base / "Manifestação - João Arthur.pdf"
            extracted = ExtractionResult(path, (PageText(1, "", "native"),))

            result = _identify_client(path, extracted, clients)

            self.assertEqual(result, clients[1])

    def test_nome_do_arquivo_tolera_erro_de_digitacao_na_pasta(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            client = base / "ELTECH MONTAGEM ELETRICA LTDA"
            path = base / "Sentença Eltch.pdf"
            extracted = ExtractionResult(path, (PageText(1, "", "native"),))

            result = _identify_client(path, extracted, [client])

            self.assertEqual(result, client)

    def test_nome_completo_da_ia_nao_cai_em_pasta_com_primeiro_nome_igual(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            existing_client = base / "JOAO PAULO PIRES"
            existing_client.mkdir()
            path = base / "Manifestação - João Arthur.pdf"
            extracted = ExtractionResult(path, (PageText(1, "", "native"),))

            result = _identify_client(
                path,
                extracted,
                [existing_client],
                ai_name="JOAO ARTHUR SIQUEIRA MARTINS",
            )

            self.assertEqual(result, base / "01_CLIENTES" / "JOAO ARTHUR SIQUEIRA MARTINS")
            self.assertTrue(result.is_dir())

    def test_nome_da_ia_cria_pasta_com_o_nome_identificado(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            existing_client = base / "ELTCH MONTAGEM ELETRICA LTDA"
            existing_client.mkdir()
            path = base / "Sentenca Eltch.pdf"
            extracted = ExtractionResult(path, (PageText(1, "", "native"),))

            result = _identify_client(
                path,
                extracted,
                [existing_client],
                ai_name="ELTECH MONTAGEM ELETRICA LTDA",
            )

            self.assertEqual(
                result,
                base / "01_CLIENTES" / "ELTECH MONTAGEM ELETRICA LTDA",
            )
            self.assertTrue(result.is_dir())

    def test_nome_da_parte_re_concorrige_ia_que_escolheu_a_parte_autora(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            path = base / "Sentenca Eltch.pdf"
            extracted = ExtractionResult(
                path,
                (
                    PageText(
                        1,
                        (
                            "AUTORA: HEVELLY DOS SANTOS RUAS\n"
                            "REU: ELTECH MONTAGEM ELETRICA LTDA"
                        ),
                        "native",
                    ),
                ),
            )

            result = _identify_client(
                path,
                extracted,
                [],
                ai_name="HEVELLY DOS SANTOS RUAS",
            )

            self.assertEqual(
                result,
                base / "01_CLIENTES" / "ELTECH MONTAGEM ELETRICA LTDA",
            )
            self.assertTrue(result.is_dir())

    def test_nome_extraido_cria_pasta_nova_em_vez_de_usar_primeiro_nome(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            existing_client = base / "JOAO PAULO PIRES"
            existing_client.mkdir()
            path = base / "Manifestação - João Arthur.pdf"
            extracted = ExtractionResult(
                path,
                (
                    PageText(
                        1,
                        "Nome completo:\nJOAO ARTHUR SIQUEIRA MARTINS",
                        "native",
                    ),
                ),
            )

            result = _identify_client(path, extracted, [existing_client])

            self.assertEqual(result, base / "01_CLIENTES" / "JOAO ARTHUR SIQUEIRA MARTINS")
            self.assertTrue(result.is_dir())

    def test_nome_de_arquivo_com_apenas_primeiro_nome_nao_escolhe_cliente_ambiguo(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            clients = [
                base / "JOAO PAULO PIRES",
                base / "JOAO ARTHUR SIQUEIRA MARTINS",
            ]
            path = base / "Documento Joao.pdf"
            extracted = ExtractionResult(path, (PageText(1, "", "native"),))

            result = _identify_client(path, extracted, clients)

            self.assertIsNone(result)

    def test_disponibilidade_tem_timeout_separado(self) -> None:
        client = OllamaClient(
            OllamaConfig(timeout=60.0, availability_timeout=15.0)
        )
        with patch("cetti_ia_local.urllib.request.urlopen") as urlopen:
            response = urlopen.return_value.__enter__.return_value
            response.read.return_value = b'{"models": []}'
            client.is_available()

        self.assertEqual(urlopen.call_args.kwargs["timeout"], 15.0)

    def test_identificacao_envia_somente_trecho_inicial(self) -> None:
        client = OllamaClient(OllamaConfig())
        texto = "INICIO DO DOCUMENTO\n" + ("x" * 8_000) + "\nFIM DO DOCUMENTO"
        with patch.object(
            client,
            "_request",
            return_value={"response": '{"client_name": null, "reason": "sem evidencia"}'},
        ) as request:
            client.identify_client_name(texto, "documento.pdf", [])

        prompt = request.call_args.args[2]["prompt"]
        self.assertIn("INICIO DO DOCUMENTO", prompt)
        self.assertNotIn("FIM DO DOCUMENTO", prompt)
        self.assertIn("o restante do documento nao foi enviado ao Qwen", prompt)

    def test_diagnostico_registra_resposta_do_qwen(self) -> None:
        client = OllamaClient(OllamaConfig())
        with patch.object(
            client,
            "_request",
            return_value={"response": '{"client_name": "Erasmo", "reason": "arquivo"}'},
        ):
            client.generate("Identifique o cliente.", model="qwen3:4b", json_response=True)

        self.assertIn('resposta:\n{"client_name": "Erasmo", "reason": "arquivo"}', client.audit_log[0])

    def test_diagnostico_registra_erro_do_qwen(self) -> None:
        client = OllamaClient(OllamaConfig())
        with patch.object(
            client,
            "_request",
            side_effect=TimeoutError("timed out"),
        ), self.assertRaises(TimeoutError):
            client.generate("Identifique o cliente.", model="qwen3:4b")

        self.assertIn("erro:\ntimed out", client.audit_log[0])


if __name__ == "__main__":
    unittest.main()
