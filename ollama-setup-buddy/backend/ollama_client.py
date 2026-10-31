"""Tiny client for the helper model (Gemma through a local Ollama server)."""
from __future__ import annotations

import json
import re

import requests

from .config import HELPER_MODEL, HELPER_TIMEOUT, OLLAMA_URL


class HelperUnavailable(Exception):
    """Raised when the helper model cannot answer. Callers fall back to rules."""


def status() -> dict:
    """Report whether the helper Ollama server and model are reachable."""
    base = {"online": False, "model": HELPER_MODEL, "model_ready": False}
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        r.raise_for_status()
        names = [m.get("name", "") for m in r.json().get("models", [])]
    except (requests.RequestException, ValueError):
        return base
    ready = any(n == HELPER_MODEL or n == f"{HELPER_MODEL}:latest" for n in names)
    return {"online": True, "model": HELPER_MODEL, "model_ready": ready}


def _parse_json(text: str) -> dict:
    try:
        data = json.loads(text)
    except ValueError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise HelperUnavailable("model did not return JSON")
        try:
            data = json.loads(match.group(0))
        except ValueError as exc:
            raise HelperUnavailable("model returned broken JSON") from exc
    if not isinstance(data, dict):
        raise HelperUnavailable("model returned unexpected JSON")
    return data


def chat_json(system: str, user: str) -> dict:
    """Ask the helper model for a JSON answer. Raises HelperUnavailable on any failure."""
    payload = {
        "model": HELPER_MODEL,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {"temperature": 0.2, "num_predict": 500},
    }
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=HELPER_TIMEOUT)
        r.raise_for_status()
        content = r.json()["message"]["content"]
    except (requests.RequestException, KeyError, ValueError, TypeError) as exc:
        raise HelperUnavailable(str(exc)) from exc
    return _parse_json(content)
