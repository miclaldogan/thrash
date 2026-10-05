"""Semantic extraction: repository evidence -> validated ProcessImage via local Gemma."""

from __future__ import annotations

import time
import json
from typing import Protocol

from . import prompts
from .tracing import span
from .config import Config
from .git_context import RepoContext
from .ollama_client import ModelError, chat_json
from .privacy import public_text
from .process_image import (
    ImageError,
    ImageMeta,
    ModelOutput,
    ProcessImage,
    estimate_units,
    parse_model_json,
)


class Extractor(Protocol):
    def __call__(self, alias: str, ctx: RepoContext, previous: ProcessImage | None, now: float) -> ProcessImage: ...


def sanitize(out: ModelOutput, allowed: set[str]) -> tuple[ModelOutput, int]:
    """Drop paths the model cited that do not exist in the allowed (non-ignored) file set."""
    dropped = 0

    def ok(p: str) -> bool:
        nonlocal dropped
        good = p.strip().removeprefix("./") in allowed
        dropped += 0 if good else 1
        return good

    out.open_handles = [p.strip().removeprefix("./") for p in out.open_handles if ok(p)]
    out.evidence = [p.strip().removeprefix("./") for p in out.evidence if ok(p)]
    for d in [*out.decisions, *out.completed]:
        d.source = d.source.strip().removeprefix("./")
        if not d.source or not ok(d.source):
            d.source = ""
            d.explicit = False  # a decision we cannot source is inference at best
    return out, dropped


def validate(text):
    with span("thrash.schema.validate") as data:
        try:
            result = parse_model_json(text)
        except ImageError:
            data["schema_valid"] = False
            raise
        data.update(schema_valid=True, decision_count=len(result.decisions),
                    completed_count=len(result.completed), unresolved_count=len(result.unresolved))
        return result


def ollama_extractor(cfg: Config) -> Extractor:
    schema = ModelOutput.model_json_schema()
    # Saved legacy images remain permissive; new generations must address every
    # restoration field explicitly (empty is valid when evidence is absent).
    schema["required"] = list(schema["properties"])
    for definition in schema.get("$defs", {}).values():
        if "properties" in definition:
            definition["required"] = list(definition["properties"])

    def run(alias: str, ctx: RepoContext, previous: ProcessImage | None, now: float) -> ProcessImage:
        with span("thrash.privacy.filter", context_file_count=len(ctx.allowed_paths)):
            user = public_text("OUTPUT SCHEMA (structure, not project evidence):\n" +
                               json.dumps(schema, separators=(",", ":")) + "\n\n" +
                               prompts.build_user_prompt(alias, ctx.render(), previous))
        messages = [{"role": "user", "content": user}]
        t0 = time.monotonic()
        reply = chat_json(cfg, prompts.SYSTEM, messages, schema)
        try:
            out = validate(reply.text)
        except ImageError as first:
            # one repair attempt, then give up loudly: never store a guess
            messages += [
                {"role": "assistant", "content": public_text(reply.text[:2000])},
                {"role": "user", "content": prompts.build_repair_prompt(str(first))},
            ]
            reply = chat_json(cfg, prompts.SYSTEM, messages, schema)
            out = validate(reply.text)  # raises ImageError
        out, dropped = sanitize(out, ctx.allowed_paths)
        image = ProcessImage(
            **out.model_dump(),
            project=alias,
            meta=ImageMeta(
                created_at=now,
                model=cfg.model,
                extract_seconds=round(time.monotonic() - t0, 2),
                todo_count=ctx.todo_count,
                dropped_paths=dropped,
                redactions=ctx.redactions,
                head=ctx.fingerprint.head,
                context_version=2,
            ),
        )
        image.meta.ctx_units = estimate_units(image.model_dump_json())
        return image

    return run


__all__ = ["Extractor", "ollama_extractor", "sanitize", "ModelError", "ImageError"]
