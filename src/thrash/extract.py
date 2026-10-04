"""Semantic extraction: repository evidence -> validated ProcessImage via local Gemma."""

from __future__ import annotations

import time
from typing import Protocol

from . import prompts
from .config import Config
from .git_context import RepoContext
from .ollama_client import ModelError, chat_json
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

    out.open_handles = [p.removeprefix("./") for p in out.open_handles if ok(p)]
    out.evidence = [p.removeprefix("./") for p in out.evidence if ok(p)]
    for d in out.decisions:
        if d.source and not ok(d.source):
            d.source = ""
            d.explicit = False  # a decision we cannot source is inference at best
    return out, dropped


def ollama_extractor(cfg: Config) -> Extractor:
    schema = ModelOutput.model_json_schema()

    def run(alias: str, ctx: RepoContext, previous: ProcessImage | None, now: float) -> ProcessImage:
        user = prompts.build_user_prompt(alias, ctx.render(), previous)
        messages = [{"role": "user", "content": user}]
        t0 = time.monotonic()
        reply = chat_json(cfg, prompts.SYSTEM, messages, schema)
        try:
            out = parse_model_json(reply.text)
        except ImageError as first:
            # one repair attempt, then give up loudly: never store a guess
            messages += [
                {"role": "assistant", "content": reply.text[:2000]},
                {"role": "user", "content": prompts.build_repair_prompt(str(first))},
            ]
            reply = chat_json(cfg, prompts.SYSTEM, messages, schema)
            out = parse_model_json(reply.text)  # raises ImageError
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
            ),
        )
        image.meta.ctx_units = estimate_units(image.model_dump_json())
        return image

    return run


__all__ = ["Extractor", "ollama_extractor", "sanitize", "ModelError", "ImageError"]
