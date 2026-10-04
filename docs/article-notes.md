# Article notes (facts only)

## What it is
A terminal tool that treats projects as OS processes. On `switch`/`suspend`/`kill` it serializes a "process image" (program counter, registers, stack, decisions, unresolved, blockers, next action) from repository evidence using a local Gemma via Ollama. On return it restores the image and reports drift against the repository. `thrash top` shows the process table and a transparent thrashing heuristic.

## Architecture
See README. Key split: **deterministic code** does timestamps, counts, pressure, file discovery, git diffs, drift, zombie and thrashing detection; **the model** only turns repository text into a structured image.

## Implementation choices
- Zombie is a *derived* state (idle >= 14 days AND residue), never stored, so it cannot go stale.
- Registry enforces at most one RUNNING process in `set_running`, and tests cover it.
- If the repo is unchanged since the last image, `switch` reuses the image instead of calling the model. This makes switching back and forth cheap (restore ~0.01 s) and means model latency is paid only when something changed.
- Ollama `format` is given the JSON schema (structured outputs), and the reply is still validated with Pydantic. One repair attempt, then reject; the previous image survives.
- Model-cited paths are checked against the real, non-ignored file list; invented ones are dropped and counted (`dropped_paths`). One demo run showed "2 invalid path(s) rejected" for a project.
- Privacy: ignore rules and secret redaction are applied before text reaches the prompt. The prompt carries the alias, not the directory name.
- JSON/JSONL storage with atomic replace; no database.

## Measured latency (initial extraction, 5 tiny synthetic repos, one laptop, local Ollama; single runs, not benchmarks)
| Model | per-project extraction |
|---|---|
| gemma3:4b | 3.6 - 5.6 s |
| gemma4:e4b-it-qat | 15.5 - 37.2 s |
| gemma3:12b | 24.4 - 54.8 s |

Default is `gemma3:4b`. Restore from an existing image: ~0.01 s (no model call). Larger repos send up to ~14,000 characters of evidence (`context_chars`), so expect more on real projects. I did not measure quality differences between the models.

## Network
During a real `switch` with extraction, I logged every `socket.connect()` target: only `127.0.0.1:11434` and `::1:11434`. I did **not** physically turn Wi-Fi off, so "works with Wi-Fi disabled" is inferred from that, not demonstrated. With Ollama unreachable, `switch` still changes state and `top`/`ps` work; extraction prints `LOCAL MODEL UNAVAILABLE` (covered by tests).

## Notable failures / debugging discoveries
- **Dotfile bug.** I normalized paths with `str.lstrip("./")`, which strips *characters*, so `.env` became `env` and bypassed the ignore rules. A privacy test caught it before any commit; fixed with `removeprefix("./")`.
- **Prompt leakage.** The first prompt's field guide used `"engine": "undecided"` as an example. Gemma then reported `engine: undecided` as a register for an unrelated research project. Removing the concrete example fixed it. Lesson: examples in a small model's prompt are treated as evidence.
- **Fake clock vs real git.** A test with a fixed fake clock (year 2027) against repos with real commit times made everything a ZOMBIE. Tests now start the fake clock at the real current time.
- Small models sometimes label an inference as a decision; the `explicit` flag plus the source-path check is how that is surfaced (`(inferred)` in `status`).

## Limitations
See README "Limitations". In short: only sees what is in files and commits; thresholds are my defaults, unvalidated; drift is keyword overlap; Linux-only tested.

## Honest scope notes
- Commits were not as granular as planned for the first feature: the kernel (registry, images, switching, thrashing, privacy, CLI) went in as one commit.
- Not built: shell integration, export formats, richer drift, animations.

## Friend's feedback
> **PLACEHOLDER: add real feedback here after she has tried it. Nothing in this repository claims a reaction.**
