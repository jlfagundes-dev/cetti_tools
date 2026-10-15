from __future__ import annotations

import base64
import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_OLLAMA_LOCK = threading.Lock()


class LocalAIError(RuntimeError):
    pass


class OllamaUnavailable(LocalAIError):
    pass


@dataclass(frozen=True)
class EvidenceValue:
    value: str | None
    page: int | None


@dataclass(frozen=True)
class DocumentInterpretation:
    client: EvidenceValue
    document_type: EvidenceValue
    process_number: EvidenceValue
    document_date: EvidenceValue


@dataclass(frozen=True)
class OllamaConfig:
    base_url: str = "http://127.0.0.1:11434"
    text_model: str = "qwen3:4b"
    ocr_model: str = "glm-ocr"
    timeout: float = 30.0

    @classmethod
    def from_environment(cls) -> "OllamaConfig":
        return cls(
            base_url=os.getenv("CETTI_OLLAMA_URL", cls.base_url),
            text_model=os.getenv("CETTI_TEXT_MODEL", cls.text_model),
            ocr_model=os.getenv("CETTI_OCR_MODEL", cls.ocr_model),
            timeout=float(os.getenv("CETTI_OLLAMA_TIMEOUT", cls.timeout)),
        )


def _ensure_local_url(value: str) -> str:
    parsed = urllib.parse.urlparse(value.rstrip("/"))
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("A integracao Ollama aceita somente um endpoint local de loopback.")
    return value.rstrip("/")


class OllamaClient:
    def __init__(self, config: OllamaConfig | None = None):
        self.config = config or OllamaConfig.from_environment()
        self.base_url = _ensure_local_url(self.config.base_url)

    def is_available(self) -> bool:
        try:
            self._request("GET", "/api/tags", None)
            return True
        except (OSError, LocalAIError):
            return False

    def _request(self, method: str, endpoint: str, payload: dict[str, Any] | None) -> dict[str, Any]:
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{endpoint}", data=body, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            raise OllamaUnavailable(f"Ollama local indisponivel: {error}") from error
        if not isinstance(result, dict):
            raise LocalAIError("Resposta invalida do Ollama.")
        return result

    def generate(
        self,
        prompt: str,
        model: str | None = None,
        images: list[bytes] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model or self.config.text_model,
            "prompt": prompt,
            "stream": False,
        }
        if images:
            payload["images"] = [base64.b64encode(image).decode("ascii") for image in images]
        with _OLLAMA_LOCK:
            response = self._request("POST", "/api/generate", payload)
        text = response.get("response")
        if not isinstance(text, str):
            raise LocalAIError("Ollama nao retornou texto interpretavel.")
        return text

    def interpret_document(self, text: str, page_count: int) -> DocumentInterpretation:
        if page_count < 1:
            raise ValueError("page_count deve ser positivo.")
        prompt = (
            "Extraia dados do texto juridico abaixo. Retorne somente JSON valido com as chaves "
            "client, document_type, process_number e document_date. Cada valor deve ser um objeto "
            "com value e page. Use null para dados ausentes; nunca invente dados. page deve ser "
            f"um numero entre 1 e {page_count} ou null.\n\nTEXTO:\n{text}"
        )
        raw = self.generate(prompt, self.config.text_model)
        return validate_interpretation(raw, page_count)

    def ocr_image(self, image: bytes) -> str:
        return self.generate(
            "Transcreva somente o texto visivel da imagem. Nao invente texto.",
            self.config.ocr_model,
            [image],
        )


def _parse_json_response(raw: str) -> dict[str, Any]:
    cleaned = raw.strip().replace("```json", "").replace("```", "").strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise LocalAIError("A resposta do modelo nao e JSON valido.") from error
    if not isinstance(value, dict):
        raise LocalAIError("A resposta do modelo deve ser um objeto JSON.")
    return value


def _evidence(value: Any, page_count: int) -> EvidenceValue:
    if not isinstance(value, dict) or set(value) - {"value", "page"}:
        raise LocalAIError("Cada campo extraido deve conter somente value e page.")
    extracted = value.get("value")
    page = value.get("page")
    if extracted is not None and not isinstance(extracted, str):
        raise LocalAIError("O valor extraido deve ser texto ou null.")
    if page is not None and (not isinstance(page, int) or isinstance(page, bool) or not 1 <= page <= page_count):
        raise LocalAIError("A pagina informada pelo modelo e invalida.")
    if extracted is None and page is not None:
        raise LocalAIError("Dado ausente nao pode possuir pagina de origem.")
    return EvidenceValue(extracted.strip() if extracted else None, page)


def validate_interpretation(raw: str, page_count: int) -> DocumentInterpretation:
    value = _parse_json_response(raw)
    required = {"client", "document_type", "process_number", "document_date"}
    if set(value) != required:
        raise LocalAIError("A resposta nao possui exatamente o esquema esperado.")
    return DocumentInterpretation(
        client=_evidence(value["client"], page_count),
        document_type=_evidence(value["document_type"], page_count),
        process_number=_evidence(value["process_number"], page_count),
        document_date=_evidence(value["document_date"], page_count),
    )
