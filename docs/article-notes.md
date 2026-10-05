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
- Registry, image, swap and core files use atomic replacement; the event log is append-only JSONL. Malformed/torn event lines are skipped. No database.

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
- At the end of Prompt 1, shell integration, export formats, richer drift and animations were not built. Prompt 2 adds the TUI and pressure/paging effects; the first three remain out of scope.

## Foundation audit follow-up
- Added synthetic regressions for secrets in TODOs/commit subjects, ignored-file symlinks, linked ignore files, excluded roots, tracked/nested `.gitignore` rules, and public path masking.
- File scanning prunes excluded/ignored directories and skips symlinks. Working-tree checks compare only allowed files against Git index metadata; they do not invoke `git status` to read sensitive tracked files indirectly.
- Rescanning a paged-out project previously left an older swap image that restoration preferred. Restoration now chooses the newest valid copy.
- Decisions without usable source paths are marked inferred, including older images loaded from disk.
- LOAD sessions are clipped to the advertised 24-hour window. A session beginning before the window no longer inflates its share.
- The first implementation's commit granularity remains a historical limitation; history was not rewritten to imply otherwise.
- Follow-up offline verification ran demos A–E with a temporary local Gemma server in a Linux network namespace whose only interface was `lo`. All scenes completed without model errors. The laptop's Wi-Fi was left alone; describe this as network-isolated verification, not a physical Wi-Fi-off demonstration. See `foundation-verification.md`.

## Friend's feedback
> **PLACEHOLDER: add real feedback here after she has tried it. Nothing in this repository claims a reaction.**

## Prompt 2 story outline (notes, not a finished article)

1. **The human bug.** Use the supplied mental-tabs story without inventing a conversation or medical explanation.
2. **The task-manager joke.** More planners can become more things to remember. Keep it brief.
3. **Recognition.** The repeated cost is reconstructing context. Explain OS thrashing, then make the limits of the analogy explicit.
4. **The reveal.** “She didn’t need another planner. She needed a kernel.” Show the useful PAGE FAULT before showing any glitch effect.
5. **Actual state.** Completed work, the reason behind a decision, the stopping point, changed files, unresolved work and one concrete next step. Point to evidence and honest blanks.
6. **A thought interrupts.** Capture an IRQ while preserving the running process. It is not another project until explicitly admitted.
7. **The screen tells the truth.** Visual echoes derive from recorded switching and pressure. Simulated demonstration history is disclosed in the documentation.
8. **Starvation and residue.** A long READY wait is insufficient without other dispatches. A zombie needs inactivity plus unfinished residue. Neither is a judgment about the person.
9. **Admission and recovery.** OUT OF MIND asks for a deliberate choice. PANIC has four gates and keeps recovery controls available. Suspending preserves context.
10. **Local AI.** Gemma reconstructs semantic state; code owns times, counts, diffs and thresholds. No cloud inference.
11. **What failed.** Include the real extraction and UI findings in `prompt2-verification.md`, alongside the earlier privacy fixes. Avoid claiming tests prove semantic truth.
12. **Feedback.** Leave the existing placeholder until the friend actually uses it. Do not fabricate relief, quotes or results.
13. **Ending candidate.** The project is not about making someone execute more tasks. It is about returning without rebuilding the whole room in their head.

### Copy candidates supplied with the concept

- “My laptop has a scheduler. My friend didn't.”
- “1 human. 1 core. Too many processes.”
- “The screen isn't glitching because I wanted a cool terminal aesthetic. It is glitching because she switched projects eleven times in four hours.” Use the latter only beside real telemetry showing eleven switches; the shipped synthetic panic scene has twenty-two.
- “Context restoration.”

### What to leave out

No streak, focus score, deadline list, reward loop or automatic priority ranking. A feature that only renames a planner item with an OS noun does not belong. IRQs persist without dispatch, suspension preserves recoverable state, and core dumps restore a terminated process; those are observable behaviors.

### Implementation research

- László Szabó (`lezli01`), [The Terminal Should Show the Work, Not Own It](https://dev.to/lezli01/the-terminal-should-show-the-work-not-own-it-ihk), plus its durable-state discussion: keep CLI and TUI as clients of saved state. THRASH retains the existing local kernel rather than adding a daemon.
- Nazarii Ahapevych, [Textual markup failure](https://dev.to/nazarii-ahapevych/typecname-crashed-my-textual-tui-why-escaping-user-text-isnt-enough-3gp0): dynamic content is rendered as literal Rich Text, with a bracket-shaped input regression test.
- Official [Textual workers](https://textual.textualize.io/guide/workers/) and [testing](https://textual.textualize.io/guide/testing/) documentation informed worker messages and headless keyboard tests.


## Prompt 4 evidence and public-data provenance

Public demos use simulated project histories and anonymized aliases. THRASH was additionally verified against real local projects in read-only mode, but those contents were never committed or used in public assets. Recommended demo font: Iosevka Term; local font files are not distributed. Hero screenshots omit fixture labels; their provenance is explicit here, in README and in the demo script.

Lead with `docs/media/page-fault.gif` and `docs/media/02-page-fault.png`. Those are hand-authored process images, not evidence of model accuracy. Use [Gemma evaluation](gemma-eval.md) for the actual model scores and failure examples, and [Sentry notes](sentry-notes.md) for the measured latency breakdown. Do not call the local envelope preview a hosted Sentry screenshot. Hosted verification remains pending access.

The scheduler is ordinary Python. The part that remembers why you were there is Gemma.

THRASH traces my friend's context switches. Sentry traces THRASH's.

Challenge 78, [Hacktoberfest Weekend: Build for a Friend](https://dev.to/events/78), runs October 2 at 02:00 UTC to October 5 at 06:59 UTC, 2026. The public rules list Best Use of Gemma and Best Use of Sentry Agent Tracing; writing quality carries the highest weight. Required tag: `hf26challenge`. The entry must explain the real intended recipient, why open/local matters, link code and demo, and use the announcement's submission template. No entry has been published by this work. Friend feedback remains the honest placeholder above.

### Observability research

[Nainik Mehta, LLM Observability: Trace Cost, Sampling & Privacy](https://dev.to/nainikmehta/llm-observability-trace-cost-sampling-privacy-7gp) argues for structured counts and filtering before persistence. Comments add that an empty dashboard may mean dropped telemetry, not health. THRASH therefore distinguishes local envelope capture from confirmed backend receipt and captures no prompt excerpts or hashes. [DevOps Daily's trace-context discussion](https://dev.to/devopsdaily/your-trace-dies-the-moment-the-pipeline-shells-out-5g7a) highlights inherited baggage as a trust boundary; THRASH uses a private SDK scope and rebuilds outgoing events. No comments were present on that second article. SDK behavior was checked against official Sentry documentation, not copied from community examples.
