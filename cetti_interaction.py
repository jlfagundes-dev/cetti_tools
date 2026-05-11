"""
Canal compartilhado entre o worker de IA e o Streamlit.

Usa um arquivo JSON simples para sinalizar quando o cliente de um documento
precisa ser informado pelo usuário no chat.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from uuid import uuid4


BASE_DIR = Path(__file__).parent
PENDING_FILE = BASE_DIR / "cetti_pending_request.json"


def criar_pedido_cliente(arquivo: str, advogado: str, tipo: str) -> str:
    pedido_id = str(uuid4())
    payload = {
        "id": pedido_id,
        "type": "client",
        "status": "pending",
        "arquivo": arquivo,
        "advogado": advogado,
        "tipo": tipo,
        "prompt": f"Qual é o cliente deste documento? Arquivo: {arquivo}",
        "response": "",
        "created_at": time.time(),
    }
    PENDING_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return pedido_id


def ler_pedido_pendente() -> dict | None:
    if not PENDING_FILE.exists():
        return None

    try:
        payload = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None

    if payload.get("status") not in {"pending", "answered"}:
        return None

    return payload


def responder_pedido(pedido_id: str, resposta: str) -> bool:
    pedido = ler_pedido_pendente()
    if not pedido or pedido.get("id") != pedido_id:
        return False

    pedido["status"] = "answered"
    pedido["response"] = resposta.strip()
    PENDING_FILE.write_text(json.dumps(pedido, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def aguardar_resposta(pedido_id: str, timeout: int = 900, intervalo: float = 1.0) -> str:
    fim = time.time() + timeout

    while time.time() < fim:
        pedido = ler_pedido_pendente()
        if pedido and pedido.get("id") == pedido_id and pedido.get("status") == "answered":
            resposta = str(pedido.get("response", "")).strip()
            if resposta:
                return resposta

        time.sleep(intervalo)

    raise TimeoutError("Tempo esgotado aguardando resposta do cliente no chat.")


def limpar_pedido(pedido_id: str | None = None) -> None:
    if not PENDING_FILE.exists():
        return

    if pedido_id is None:
        PENDING_FILE.unlink(missing_ok=True)
        return

    pedido = ler_pedido_pendente()
    if pedido and pedido.get("id") == pedido_id:
        PENDING_FILE.unlink(missing_ok=True)
