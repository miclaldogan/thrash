"""Thin client for a local Ollama server. Nothing here talks to the internet."""

from __future__ import annotations

import time
import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit

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


def local_url(cfg: Config) -> str:
    """Only a loopback server; ignore proxies and avoid resolving arbitrary hosts."""
    try:
        url = urlsplit(cfg.ollama_url)
        host = url.hostname
        if host == "localhost":
            host = "127.0.0.1"
        if url.scheme not in ("http", "https") or not host or not ipaddress.ip_address(host).is_loopback:
            raise ValueError
        if url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
            raise ValueError
        port = url.port or (443 if url.scheme == "https" else 80)
        address = f"[{host}]" if ":" in host else host
        if "cloud" in cfg.model.lower():
            raise ValueError
        return f"{url.scheme}://{address}:{port}"
    except ValueError as exc:
        raise ModelError("Only local Ollama on a loopback address and local models are allowed") from exc


def _same_model(wanted: str, have: str) -> bool:
    if wanted == have:
        return True
    return ":" not in wanted and have == f"{wanted}:latest"


def check_ready(cfg: Config, client: httpx.Client | None = None) -> None:
    url = local_url(cfg)
    own = client is None
    client = client or httpx.Client(timeout=5.0, trust_env=False)
    try:
        r = client.get(f"{url}/api/tags")
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
    url = local_url(cfg)
    own = client is None
    client = client or httpx.Client(timeout=cfg.request_timeout, trust_env=False)
    payload = {
        "model": cfg.model,
        "stream": False,
        "format": schema or "json",
        "options": {"temperature": 0.1, "num_ctx": cfg.num_ctx},
        "messages": [{"role": "system", "content": system}, *messages],
    }
    t0 = time.monotonic()
    try:
        r = client.post(f"{url}/api/chat", json=payload)
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
