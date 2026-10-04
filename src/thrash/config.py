"""Configuration: plain environment variables, no config file."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


def default_data_dir() -> Path:
    if env := os.environ.get("THRASH_HOME"):
        return Path(env).expanduser()
    if xdg := os.environ.get("XDG_DATA_HOME"):
        return Path(xdg).expanduser() / "thrash"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "thrash"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "thrash"
    return Path.home() / ".local" / "share" / "thrash"


def _num(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        raise SystemExit(f"{name}={raw!r} is not a number")


@dataclass
class Config:
    data_dir: Path = field(default_factory=default_data_dir)
    model: str = "gemma3:4b"
    ollama_url: str = "http://localhost:11434"
    num_ctx: int = 8192
    request_timeout: float = 600.0
    context_chars: int = 14000  # budget of repository text sent to the model

    # scheduler heuristic thresholds
    window_hours: float = 4.0
    switch_limit: int = 6
    median_session_min: float = 20.0
    recon_limit: int = 3
    max_active: int = 4
    signals_required: int = 2
    stale_hours: float = 24.0
    zombie_days: float = 14.0

    @classmethod
    def from_env(cls) -> "Config":
        d = cls()
        d.model = os.environ.get("THRASH_MODEL", d.model)
        d.ollama_url = os.environ.get("THRASH_OLLAMA_URL", d.ollama_url).rstrip("/")
        d.num_ctx = int(_num("THRASH_NUM_CTX", d.num_ctx))
        d.window_hours = _num("THRASH_WINDOW_HOURS", d.window_hours)
        d.switch_limit = int(_num("THRASH_SWITCH_LIMIT", d.switch_limit))
        d.median_session_min = _num("THRASH_MEDIAN_SESSION_MIN", d.median_session_min)
        d.recon_limit = int(_num("THRASH_RECON_LIMIT", d.recon_limit))
        d.max_active = int(_num("THRASH_MAX_ACTIVE", d.max_active))
        d.signals_required = int(_num("THRASH_SIGNALS_REQUIRED", d.signals_required))
        d.stale_hours = _num("THRASH_STALE_HOURS", d.stale_hours)
        d.zombie_days = _num("THRASH_ZOMBIE_DAYS", d.zombie_days)
        return d

    # --- storage layout -------------------------------------------------
    @property
    def registry_path(self) -> Path:
        return self.data_dir / "registry.json"

    @property
    def events_path(self) -> Path:
        return self.data_dir / "events.jsonl"

    @property
    def processes_dir(self) -> Path:
        return self.data_dir / "processes"

    @property
    def swap_dir(self) -> Path:
        return self.data_dir / "swap"

    @property
    def graveyard_dir(self) -> Path:
        return self.data_dir / "graveyard"

    @property
    def global_ignore_path(self) -> Path:
        return self.data_dir / "thrashignore"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.processes_dir, self.swap_dir, self.graveyard_dir):
            d.mkdir(parents=True, exist_ok=True)


def tilde(path: Path | str) -> str:
    """Shorten the home directory for display."""
    p = str(path)
    home = str(Path.home())
    return "~" + p[len(home):] if p.startswith(home) else p
