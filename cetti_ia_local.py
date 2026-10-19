from __future__ import annotations

import base64
import contextlib
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cetti_config import load_project_environment


load_project_environment()


_OLLAMA_LOCK = threading.Lock()
_IDENTIFICATION_TEXT_LIMIT = 8_000


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
    timeout: float = 300.0
    availability_timeout: float = 15.0

    @classmethod
    def from_environment(cls) -> "OllamaConfig":
        return cls(
            base_url=os.getenv("CETTI_OLLAMA_URL", cls.base_url),
            text_model=os.getenv("CETTI_TEXT_MODEL", cls.text_model),
            ocr_model=os.getenv("CETTI_OCR_MODEL", cls.ocr_model),
            timeout=float(os.getenv("CETTI_OLLAMA_TIMEOUT", cls.timeout)),
            availability_timeout=float(
                os.getenv("CETTI_OLLAMA_STATUS_TIMEOUT", cls.availability_timeout)
            ),
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
        self.audit_log: list[str] = []

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
            timeout = (
                self.config.availability_timeout
                if endpoint == "/api/tags"
                else self.config.timeout
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
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
        json_response: bool = False,
        num_predict: int = 256,
    ) -> str:
        selected_model = model or self.config.text_model
        payload: dict[str, Any] = {
            "model": selected_model,
            "prompt": prompt,
            "stream": False,
        }
        if selected_model.casefold().startswith("qwen"):
            payload["think"] = False
            payload["options"] = {"num_predict": num_predict, "temperature": 0}
        if json_response:
            payload["format"] = "json"
        if images:
            payload["images"] = [base64.b64encode(image).decode("ascii") for image in images]
        audit_entry = (
            f"modelo={selected_model}; json={json_response}; imagens={len(images or [])}\n"
            f"prompt:\n{prompt}"
        )
        with _OLLAMA_LOCK:
            try:
                response = self._request("POST", "/api/generate", payload)
            except Exception as error:
                self.audit_log.append(f"{audit_entry}\nerro:\n{error}")
                raise
        text = response.get("response")
        if not isinstance(text, str):
            error = LocalAIError("Ollama nao retornou texto interpretavel.")
            self.audit_log.append(f"{audit_entry}\nerro:\n{error}")
            raise error
        self.audit_log.append(f"{audit_entry}\nresposta:\n{text}")
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
        raw = self.generate(prompt, self.config.text_model, json_response=True)
        return validate_interpretation(raw, page_count)

    def identify_client_name(
        self,
        text: str,
        filename: str,
        client_folders: list[str],
        excluded_names: list[str] | None = None,
    ) -> list[dict[str, str]]:
        document_excerpt = text[:_IDENTIFICATION_TEXT_LIMIT]
        excerpt_note = (
            f"(trecho inicial limitado a {_IDENTIFICATION_TEXT_LIMIT} caracteres; "
            "o restante do documento nao foi enviado ao Qwen)"
        )
        folders = "\n".join(f"- {folder}" for folder in client_folders) or "(nenhuma pasta criada)"
        excluded = "\n".join(f"- {name}" for name in (excluded_names or [])) or "(nenhum nome cadastrado)"
        prompt = (
            "Liste todas as partes identificadas neste documento juridico, com nome "
            "completo e papel processual. Nao escolha somente a parte autora: inclua "
            "autora, reu, empresas e demais partes encontradas. Retorne somente JSON "
            'valido no formato {"parties": [{"name": "...", "role": "..."}], '
            '"reason": "..."}; use uma lista vazia quando nao houver evidencia. '
            "Nao invente nomes e nao inclua advogado, juiz ou testemunha como parte. "
            "O sistema escolhera a parte correta comparando os nomes retornados com "
            "o nome do arquivo, que pode conter erro de digitacao. "
            "Os nomes abaixo sao advogados do escritorio e NUNCA podem ser clientes: "
            f"{excluded}. Escreva reason em no maximo 12 palavras.\n\n"
            f"NOME DO ARQUIVO:\n{filename}\n\n"
            f"PASTAS DE CLIENTES EXISTENTES:\n{folders}\n\n"
            f"TEXTO INICIAL EXTRAIDO DO DOCUMENTO {excerpt_note}:\n{document_excerpt}"
        )
        raw = self.generate(
            prompt,
            self.config.text_model,
            json_response=True,
            num_predict=128,
        )
        value = _parse_json_response(raw)
        if set(value) == {"client_name", "reason"}:
            client_name = value["client_name"]
            if client_name is not None and not isinstance(client_name, str):
                raise LocalAIError("client_name deve ser texto ou null.")
            return [{"name": client_name.strip(), "role": "parte"}] if client_name and client_name.strip() else []
        if set(value) != {"parties", "reason"}:
            raise LocalAIError("A resposta de identificacao das partes possui esquema invalido.")
        parties = value["parties"]
        if not isinstance(parties, list):
            raise LocalAIError("parties deve ser uma lista.")
        validated: list[dict[str, str]] = []
        for party in parties:
            if not isinstance(party, dict) or set(party) != {"name", "role"}:
                raise LocalAIError("Cada parte deve possuir nome e papel.")
            name = party["name"]
            role = party["role"]
            if not isinstance(name, str) or not name.strip():
                raise LocalAIError("O nome da parte deve ser texto não vazio.")
            if not isinstance(role, str) or not role.strip():
                raise LocalAIError("O papel da parte deve ser texto não vazio.")
            validated.append({"name": name.strip(), "role": role.strip()})
        return validated

    def ocr_image(self, image: bytes) -> str:
        return self.generate(
            "Transcreva somente o texto visivel da imagem. Nao invente texto.",
            self.config.ocr_model,
            [image],
        )


@contextlib.contextmanager
def temporary_ollama(
    client: OllamaClient | None = None,
    startup_timeout: float = 30.0,
    allow_unavailable: bool = False,
):
    """Use Ollama if running, otherwise start it and stop only that process.

    When ``allow_unavailable`` is true, yield ``None`` so callers can continue
    with their non-Ollama processing path.
    """
    ollama_client = client or OllamaClient()
    if ollama_client.is_available():
        yield ollama_client
        return

    executable = os.getenv("CETTI_OLLAMA_EXECUTABLE") or shutil.which("ollama")
    if not executable:
        if allow_unavailable:
            yield None
            return
        raise OllamaUnavailable(
            "Ollama nao esta disponivel e o executavel 'ollama' nao foi encontrado. "
            "Instale o Ollama ou configure CETTI_OLLAMA_EXECUTABLE."
        )

    process = subprocess.Popen(
        [executable, "serve"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    deadline = time.monotonic() + startup_timeout
    try:
        while time.monotonic() < deadline:
            if ollama_client.is_available():
                yield ollama_client
                return
            if process.poll() is not None:
                if allow_unavailable:
                    yield None
                    return
                raise OllamaUnavailable(
                    f"Ollama encerrou durante a inicializacao (codigo {process.returncode})."
                )
            time.sleep(0.5)
        if allow_unavailable:
            yield None
            return
        raise OllamaUnavailable(
            f"Ollama nao respondeu em {startup_timeout:.0f} segundos apos ser iniciado."
        )
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


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
