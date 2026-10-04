"""Append-only local event log (events.jsonl).

Only events THRASH itself performs are recorded: no keystrokes, no browser history,
no global process scanning.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Telemetry:
    def __init__(self, path: Path):
        self.path = path

    def record(self, type_: str, ts: float, **fields: Any) -> dict[str, Any]:
        event = {
            "ts": ts,
            "at": datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds"),
            "type": type_,
            **fields,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a torn line must never break the monitor
        return out

    def switches(self) -> list[dict[str, Any]]:
        return [e for e in self.read() if e.get("type") == "switch"]
