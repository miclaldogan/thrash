"""Process registry: which projects exist, their alias, state and path.

The alias is the only name ever displayed. The real path lives in registry.json
(local, user-level) and is never printed by the CLI.
"""

from __future__ import annotations

import json
import os
import re
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

from .config import Config
from .privacy import ScanPolicy, absolute


class RegistryError(Exception):
    pass


class State(str, Enum):
    RUNNING = "RUNNING"
    READY = "READY"
    SLEEPING = "SLEEPING"
    ZOMBIE = "ZOMBIE"  # derived by the scheduler, never stored
    TERMINATED = "TERMINATED"


class Process(BaseModel):
    pid: int
    alias: str
    path: str
    state: State = State.READY
    registered_at: float
    running_since: float | None = None
    last_suspended: float | None = None
    terminated_at: float | None = None

    @property
    def pid_str(self) -> str:
        return f"{self.pid:03d}"


_ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9._-]+", "-", name.strip().lower()).strip("-.")
    return s or "project"


class Registry:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.next_pid = 1
        self.processes: list[Process] = []
        self.load()

    # --- persistence ----------------------------------------------------
    def load(self) -> None:
        p = self.cfg.registry_path
        if not p.exists():
            return
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise RegistryError(f"registry corrupt: {p} ({e})") from e
        self.next_pid = raw.get("next_pid", 1)
        self.processes = [Process(**x) for x in raw.get("processes", [])]

    def save(self) -> None:
        self.cfg.ensure_dirs()
        data = {
            "version": 1,
            "next_pid": self.next_pid,
            "processes": [p.model_dump(mode="json") for p in self.processes],
        }
        tmp = self.cfg.registry_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, self.cfg.registry_path)  # atomic: a crash never half-writes

    # --- queries --------------------------------------------------------
    def all(self, include_terminated: bool = False) -> list[Process]:
        policy = ScanPolicy(self.cfg.excluded_roots)
        return [p for p in self.processes if not policy.excluded(Path(p.path))
                and (include_terminated or p.state != State.TERMINATED)]

    def running(self) -> Process | None:
        return next((p for p in self.all() if p.state == State.RUNNING), None)

    def by_path(self, path: str | Path) -> Process | None:
        real = absolute(Path(path))
        return next(
            (p for p in self.processes if p.state != State.TERMINATED and absolute(Path(p.path)) == real),
            None,
        )

    def resolve(self, ref: str, include_terminated: bool = False) -> Process:
        policy = ScanPolicy(self.cfg.excluded_roots)
        pool = [p for p in self.all(include_terminated) if policy.allows(Path(p.path))]
        key = ref.strip().lower()
        for p in pool:
            if p.alias == key:
                return p
        if key.isdigit():
            for p in pool:
                if p.pid == int(key):
                    return p
        matches = [p for p in pool if p.alias.startswith(key)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise RegistryError(f"ambiguous process {ref!r}: " + ", ".join(m.alias for m in matches))
        raise RegistryError(f"no such process: {ref}")

    # --- mutations ------------------------------------------------------
    def register(self, alias: str, path: str | Path, now: float, state: State = State.READY) -> Process:
        try:
            ScanPolicy(self.cfg.excluded_roots).require_root(Path(path))
        except ValueError as exc:
            raise RegistryError(str(exc)) from exc
        alias = alias.strip().lower()
        if not _ALIAS_RE.match(alias):
            raise RegistryError(f"invalid alias {alias!r} (use letters, digits, . _ -)")
        if any(p.alias == alias and p.state != State.TERMINATED for p in self.processes):
            raise RegistryError(f"alias already in use: {alias}")
        if self.by_path(path):
            raise RegistryError(f"path already registered as {self.by_path(path).alias}")
        proc = Process(
            pid=self.next_pid, alias=alias, path=str(absolute(Path(path))), state=State.READY, registered_at=now
        )
        self.next_pid += 1
        self.processes.append(proc)
        if state == State.RUNNING:
            self.set_running(proc, now)
        self.save()
        return proc

    def set_running(self, proc: Process, now: float) -> None:
        """Invariant: at most one RUNNING process."""
        for other in self.processes:
            if other.pid != proc.pid and other.state == State.RUNNING:
                other.state = State.READY
                other.running_since = None
        proc.state = State.RUNNING
        proc.running_since = now
        self.save()

    def set_state(self, proc: Process, state: State, now: float) -> None:
        if state == State.RUNNING:
            self.set_running(proc, now)
            return
        if state == State.ZOMBIE:
            raise RegistryError("ZOMBIE is derived, not assignable")
        proc.state = state
        proc.running_since = None
        if state == State.SLEEPING:
            proc.last_suspended = now
        if state == State.TERMINATED:
            proc.terminated_at = now
        self.save()

    def revive(self, proc: Process, path: str | Path) -> None:
        try:
            ScanPolicy(self.cfg.excluded_roots).require_root(Path(path))
        except ValueError as exc:
            raise RegistryError(str(exc)) from exc
        proc.path = str(absolute(Path(path)))
        proc.state = State.READY
        proc.terminated_at = None
        self.save()
