"""The process image: the minimum mental context needed to resume a project.

The model proposes; this module validates. Nothing malformed is ever stored.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


class ImageError(Exception):
    """Model output could not be turned into a valid process image."""


class ProgramCounter(BaseModel):
    task: str = ""
    confidence: float = 0.0

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp(cls, v: Any) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.0


class Decision(BaseModel):
    text: str = Field(description="A recorded choice, constraint, rejection, approval or intentional deferral; not a task, proposal or open question.")
    source: str = Field(default="", description="Supporting file path from FILE LIST.")
    explicit: bool = Field(default=True, description="True when the choice is recorded in the evidence, including faithful paraphrases.")
    reason: str = Field(default="", description="Why this choice was made, only if recorded; otherwise an empty string.")

    @model_validator(mode="after")
    def require_source(self) -> "Decision":
        if not self.source.strip():
            self.explicit = False
        return self


class CompletedWork(BaseModel):
    text: str = Field(description="Work explicitly recorded as finished, verified or working; never a plan.")
    source: str = Field(default="", description="Supporting file path from FILE LIST.")
    explicit: bool = Field(default=False, description="True for a recorded completion, even when paraphrased.")

    @model_validator(mode="after")
    def require_source(self) -> "CompletedWork":
        if not self.source.strip():
            self.explicit = False
        return self


def _strs(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v] if v.strip() else []
    return [str(x).strip() for x in v if str(x).strip()]


class ModelOutput(BaseModel):
    """What the model is asked to return (also used as the JSON schema)."""

    program_counter: ProgramCounter
    registers: dict[str, str] = Field(default_factory=dict)
    stack: list[str] = Field(default_factory=list)
    open_handles: list[str] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list, description="All explicitly recorded decisions. Empty only when no decision is supported.")
    unresolved: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    next_action: str = ""
    last_useful_state: str = Field(default="", description="Finished working state supported by evidence. Empty if nothing finished; never the pending task.")
    evidence: list[str] = Field(default_factory=list)
    summary: str = ""
    completed: list[CompletedWork] = Field(default_factory=list, description="Recorded finished work, not proposed or ongoing work.")
    purpose: str = ""
    failures: list[str] = Field(default_factory=list)
    resurrection_hint: str = Field(default="", description="A recorded condition for returning after termination; empty if absent. Do not invent one from ordinary pending tasks.")

    @field_validator("completed", mode="before")
    @classmethod
    def _completed(cls, v: Any) -> list[Any]:
        if isinstance(v, str):
            v = [v]
        return [{"text": item, "explicit": False} if isinstance(item, str) else item for item in (v or [])]

    @field_validator("summary", mode="before")
    @classmethod
    def _summary(cls, v: Any) -> str:
        return " ".join(str(x) for x in v) if isinstance(v, list) else (v or "")

    @field_validator("registers", mode="before")
    @classmethod
    def _registers(cls, v: Any) -> dict[str, str]:
        if v is None:
            return {}
        if isinstance(v, list):  # small models like [{"name":..,"value":..}]
            out = {}
            for item in v:
                if isinstance(item, dict):
                    k = item.get("name") or item.get("key") or item.get("register")
                    if k:
                        out[str(k)] = str(item.get("value", item.get("status", "")))
            return out
        if isinstance(v, dict):
            return {str(k): str(val) for k, val in v.items()}
        raise ValueError("registers must be an object")

    @field_validator("stack", "open_handles", "unresolved", "blockers", "evidence", "failures", mode="before")
    @classmethod
    def _lists(cls, v: Any) -> list[str]:
        return _strs(v)

    @field_validator("decisions", mode="before")
    @classmethod
    def _decisions(cls, v: Any) -> list[Any]:
        if v is None:
            return []
        out = []
        for d in v:
            out.append({"text": d} if isinstance(d, str) else d)
        return out

    @field_validator("program_counter", mode="before")
    @classmethod
    def _pc(cls, v: Any) -> Any:
        return {"task": v} if isinstance(v, str) else v


class ImageMeta(BaseModel):
    created_at: float
    model: str
    extract_seconds: float = 0.0
    ctx_units: int = 0  # ESTIMATE: serialized size / 4 ~= tokens
    todo_count: int = 0  # deterministic: TODO/FIXME/unchecked-box lines
    dropped_paths: int = 0  # model-cited paths that do not exist (rejected)
    redactions: int = 0
    head: str | None = None
    context_version: int = 1  # older saved images remain readable without migration


class ProcessImage(ModelOutput):
    project: str
    meta: ImageMeta


class Fingerprint(BaseModel):
    """Deterministic repo state at snapshot time; the baseline for drift."""

    head: str | None = None
    branch: str | None = None
    taken_at: float
    dirty: list[str] = Field(default_factory=list)
    files: dict[str, float] = Field(default_factory=dict)  # relpath -> mtime

    def same_state_as(self, other: "Fingerprint") -> bool:
        return self.head == other.head and sorted(self.dirty) == sorted(other.dirty) and self.files == other.files


class ContextFile(BaseModel):
    version: int = 1
    alias: str
    saved_at: float
    image: ProcessImage
    fingerprint: Fingerprint

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def read(cls, path: Path) -> "ContextFile | None":
        if not path.exists():
            return None
        try:
            return cls.model_validate_json(path.read_text(encoding="utf-8"))
        except (ValidationError, ValueError):
            return None  # a damaged page is treated as a missing page


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def parse_model_json(raw: str) -> ModelOutput:
    """Strict-ish parse: tolerate code fences / chatter around ONE json object, nothing else."""
    text = raw.strip()
    if not text:
        raise ImageError("model returned empty output")
    if m := _FENCE.search(text):
        text = m.group(1).strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ImageError("model output contains no JSON object")
        text = text[start : end + 1]
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise ImageError(f"model output is not valid JSON: {e}") from e
    if not isinstance(obj, dict):
        raise ImageError("model output JSON is not an object")
    try:
        out = ModelOutput.model_validate(obj)
    except ValidationError as e:
        raise ImageError(f"model output failed schema validation: {e.error_count()} error(s): {e.errors()[0]['loc']}") from e
    if not out.program_counter.task.strip() and not out.next_action.strip():
        raise ImageError("model output has neither a program counter nor a next action")
    return out


def estimate_units(image_json: str) -> int:
    return max(1, len(image_json) // 4)
