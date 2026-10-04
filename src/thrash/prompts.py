"""Prompt text. Kept apart from logic so it can be read, diffed and tuned on its own."""

from __future__ import annotations

from .process_image import ProcessImage

SYSTEM = """You are the context-serialization unit of a human process scheduler.
A person switches between many projects. Before they leave a project you write down the
MINIMUM mental context needed to resume it later, using only the repository evidence given.

Rules:
- Do not invent project facts. If the evidence does not say it, leave it out.
- Prefer repository evidence (notes, TODOs, recent commits) over guesses.
- Distinguish explicit decisions (written in a file or commit: explicit=true) from your own
  inference (explicit=false).
- Express uncertainty through program_counter.confidence (0.0 to 1.0). Use low confidence
  when the evidence is thin or contradictory.
- Cite file paths ONLY if they appear in the FILE LIST. Never invent paths.
- Keep every string short (under 120 characters). Lists: at most 8 items each.
- You are NOT responsible for timestamps, counts, file discovery or diffs.
- Return ONE JSON object and nothing else."""

FIELD_GUIDE = """Fill these fields:
- program_counter.task: the single task the person was most likely in the middle of.
- registers: short key/value map of important named state (e.g. "engine": "undecided").
- stack: ordered pending tasks, the immediate one first.
- open_handles: the files that matter most right now (paths from FILE LIST).
- decisions: active decisions, each with text, source (a path) and explicit.
- unresolved: open questions.
- blockers: things that actually block progress (empty if none).
- next_action: one concrete immediate next step, imperative mood.
- last_useful_state: the most recent thing that appears finished and working.
- evidence: paths that support the above."""


def build_user_prompt(alias: str, context: str, previous: ProcessImage | None) -> str:
    parts = [f"PROJECT ALIAS: {alias}", FIELD_GUIDE]
    if previous is not None:
        parts.append(
            "PREVIOUS SAVED IMAGE (may be stale; keep a decision only if the evidence still supports it):\n"
            f"program_counter: {previous.program_counter.task}\n"
            f"decisions: {[d.text for d in previous.decisions]}\n"
            f"unresolved: {previous.unresolved}"
        )
    parts.append("REPOSITORY EVIDENCE:\n" + context)
    return "\n\n".join(parts)


def build_repair_prompt(error: str) -> str:
    return (
        "Your previous reply was rejected: "
        f"{error}\nReturn ONLY one valid JSON object matching the schema, with no other text."
    )
