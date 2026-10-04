"""Thin client for a local Ollama server. Nothing here talks to the internet."""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from .config import Config


class ModelError(Exception):
    """Any condition under which semantic extraction cannot run."""


class OllamaUnavailable(ModelError):
    def __init__(self, url: str, detail: str = ""):
        self.url = url
        super().__init__(f"Ollama did not respond at {url}" + (f" ({detail})" if detail else ""))


class ModelMissing(ModelError):
    def __init__(self, model: str, installed: list[str]):
        self.model = model
        self.installed = installed
        super().__init__(f"model {model!r} is not installed in Ollama")


@dataclass
class Reply:
    text: str
    seconds: float


def _same_model(wanted: str, have: str) -> bool:
    if wanted == have:
        return True
    return ":" not in wanted and have == f"{wanted}:latest"


def check_ready(cfg: Config, client: httpx.Client | None = None) -> None:
    own = client is None
    client = client or httpx.Client(timeout=5.0)
    try:
        r = client.get(f"{cfg.ollama_url}/api/tags")
        r.raise_for_status()
        names = [m.get("name", "") for m in r.json().get("models", [])]
    except httpx.HTTPError as e:
        raise OllamaUnavailable(cfg.ollama_url, type(e).__name__) from e
    finally:
        if own:
            client.close()
    if not any(_same_model(cfg.model, n) for n in names):
        raise ModelMissing(cfg.model, names)


def chat_json(cfg: Config, system: str, messages: list[dict], schema: dict | None = None,
              client: httpx.Client | None = None) -> Reply:
    """One non-streaming chat call constrained to JSON (schema-constrained when given)."""
    own = client is None
    client = client or httpx.Client(timeout=cfg.request_timeout)
    payload = {
        "model": cfg.model,
        "stream": False,
        "format": schema or "json",
        "options": {"temperature": 0.1, "num_ctx": cfg.num_ctx},
        "messages": [{"role": "system", "content": system}, *messages],
    }
    t0 = time.monotonic()
    try:
        r = client.post(f"{cfg.ollama_url}/api/chat", json=payload)
        if r.status_code == 404:
            raise ModelMissing(cfg.model, [])
        r.raise_for_status()
        text = r.json()["message"]["content"]
    except httpx.TransportError as e:
        raise OllamaUnavailable(cfg.ollama_url, type(e).__name__) from e
    except (httpx.HTTPStatusError, KeyError, ValueError) as e:
        raise ModelError(f"unexpected Ollama response: {e}") from e
    finally:
        if own:
            client.close()
    return Reply(text=text, seconds=time.monotonic() - t0)
