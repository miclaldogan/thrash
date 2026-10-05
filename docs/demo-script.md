# Nine scenes: a human kernel

Run `thrash demo`. Public screenshots use anonymized simulated projects. Hero screens intentionally omit test-harness labels; this document records their provenance. Real-project verification was performed locally in read-only mode and was never committed. Press N for the next scene; close reports with Esc. Run `thrash demo --script` for a deterministic transcript. No model or real project is used by this scenario. Temporary state is removed on normal exit.

1. **Clean kernel.** Three READY processes; NORMAL. Show the table and the saved next instruction. Tab opens the working memory map.
2. **PAGE FAULT.** N switches to game-alpha after 71 simulated hours. Read completed work, the rig decision and its recorded reason, the stopping point, changed notes, unresolved turn test and the next instruction. This is the product demonstration; give it time.
3. **IRQ.** Esc, N. “Try a procedural walk cycle” is queued while game-alpha remains RUNNING. Tab twice shows the queue. In a live demonstration, I captures another thought without switching.
4. **Thrashing.** N records eight synthetic switches with short simulated sessions. The same deterministic scheduler that drives `top` now drives the warning and dispatch echoes.
5. **Starvation.** N advances simulated time and dispatches other projects. Select paper-crane. Its waiting interval, competing dispatches and zero recorded execution explain the warning.
6. **Zombie.** N adds film-study with twenty simulated idle days and unfinished residue. Select it to see the evidence. No emotional state is inferred.
7. **OUT OF MIND.** N adds two synthetic processes, bringing active count to six. Explain the admission choices: suspend a READY process, queue the idea, or deliberately force admission. Nothing is killed automatically.
8. **PANIC.** N creates a clearly synthetic high-switch history and IRQ backlog while multiple images are stale. All four gates are met. The recovery instructions and controls remain usable.
9. **Recovery.** N suspends READY processes, acknowledges demo IRQs, and explicitly advances through a quiet window. NORMAL returns. Tab shows the saved working sets in SWAP. Q exits and removes the isolated scenario.

## Strongest 15 seconds

Start on scene 1. N opens the 71-hour PAGE FAULT. Show “Camera follow prototype runs,” then the decision and **why**, then the stopped turn-pose test and NEXT INSTRUCTION. Esc, I, type a short thought, Enter: the idea is captured and the same project is still running.

The useful return is the reveal. PANIC is the second shot, not the opening pitch.

## Screenshots

- Best product screenshot: the full PAGE FAULT report, especially completed work + decision reason + next instruction.
- Best wide TUI screenshot: scene 8 with PANIC, paper-crane STARVED, film-study ZOMBIE, and the recovery choices.
- Best recovery comparison: scene 9’s memory map after paging work to SWAP.

For **real inference**, `demo/run_demo.sh` uses Gemma on synthetic Git repos. That is a separate verification path; do not describe fixture-mode results as live model output. See `prompt2-verification.md` for the actual new-schema run.


## Reproducible submission captures

```sh
.venv/bin/python scripts/capture/run.py
```

Requires local `rsvg-convert`, `ffmpeg`, fontconfig and the normal development dependencies. Recommended demo font: Iosevka Term. The capture script references an installed font family, falls back to monospace, and never copies font files. Terminal profile: 120 columns × 40 rows, near-black background, Iosevka Term regular, no terminal chrome. SVGs use local fonts only; PNGs/GIFs preserve the measured glyph layout without requiring readers to install a font.

Public assets are rendered from actual Textual states and actual kernel operations against temporary, hand-authored fixtures. The script advances DemoClock: 71-hour staleness, yesterday's scar, rapid switches and the recovery quiet window are simulated. GIF hold times are presentation edits, **not measured inference latency**. The recovery animation includes a four-hour quiet-window advance; suspension alone does not erase historical switches. IRQ capture asserts that the RUNNING project did not change.

The four GIFs isolate restoration, interrupt capture, thrashing and recovery. The script also generates seven numbered screenshot pairs (SVG/PNG). Real inference results live separately in `docs/eval/`, with their ground truth in `scripts/eval/scenarios.json`.
