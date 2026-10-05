# Submission assets

Recommended demo font: **Iosevka Term**, installed locally from the existing font archive. No font binary is copied into this repository. The app runs with ordinary monospace fonts. Captures reference local Iosevka and fall back to monospace; exported PNGs/GIFs need no font installation.

Public demos use simulated project histories and anonymized aliases. Prior real-project verification was read-only and private; no real project content, paths, notes or commits appear in these assets. The final hero views omit demo watermarks, but their provenance is not hidden here, in README, or in the article notes.

## Picks

- **README hero:** [page-fault.gif](media/page-fault.gif). It moves from the scheduler cursor through PC/registers/stack to the canonical human resume report and one NEXT EXECUTION.
- **DEV article lead:** [02-page-fault.png](media/02-page-fault.png). It answers what finished, why the decision was made, where execution stopped, what changed and what comes next. Follow it with the normal scope to explain the OS metaphor.
- **Strongest trace:** first fresh restoration versus the resulting saved-image return. The model call dominates the former; it is absent in the latter. [Local envelope preview](media/08-sentry-trace.png), **not a hosted Sentry screenshot**.
- **Most meaningful evaluation finding:** schema-valid JSON can still omit every recorded decision. Task reconstruction passed 8/8 and next-step coverage 7/8; positive decision extraction was 0/7. [Full evidence](gemma-eval.md).

## GIFs

All are 1320 × 1112 px, 8 fps, optimized indexed-color GIFs. Capture source is a 120-column × 40-row Textual terminal. Hold times are edited presentation timing, not inference latency.

| File | Duration | Size |
|---|---:|---:|
| [page-fault.gif](media/page-fault.gif) | 8.01 s | 166 KiB |
| [irq.gif](media/irq.gif) | 6.01 s | 227 KiB |
| [thrashing.gif](media/thrashing.gif) | 7.01 s | 213 KiB |
| [swap-recovery.gif](media/swap-recovery.gif) | 6.51 s | 287 KiB |

## Screenshots

Each has a PNG for embedding and an SVG source. The trace preview is 1320 × 758 px; UI captures are 1320 × 1112 px.

| Name | Subject |
|---|---|
| [01-normal](media/01-normal.png) | Dispatch trace, scar, resident frames, core and scheduler cursor |
| [02-page-fault](media/02-page-fault.png) | Canonical restoration report; single NEXT EXECUTION |
| [03-irq](media/03-irq.png) | Capture without dispatching away from the current process |
| [04-thrashing](media/04-thrashing.png) | Recorded switch pressure and scheduler-driven echoes |
| [05-swap-recovery](media/05-swap-recovery.png) | Suspended allocation below SWAP HORIZON after a simulated quiet window |
| [06-kernel-panic](media/06-kernel-panic.png) | Sparse, recoverable panic |
| [07-scheduler-scar](media/07-scheduler-scar.png) | Actual simulated event history from yesterday and today |
| [08-sentry-trace](media/08-sentry-trace.png) | Measured local SDK envelope preview; hosted capture pending |

The normal and scar specimens intentionally show the same state: the actual history is already visible in the normal scope. The preview retains nesting and real durations; it does not fabricate a Gemma call on the cached path or a drift stage before an image exists.

## Reproduce

```sh
pip install -e ".[dev,sentry]"
python scripts/capture/run.py
python scripts/capture/trace.py
python -m pytest -q
```

Install `rsvg-convert`, `ffmpeg`, fontconfig and Iosevka locally if desired. No downloaded font, browser, recorder service or cloud renderer is required. `run.py` uses temporary repositories and fixture images; it never scans real projects. `trace.py` reads the already-sanitized evaluation envelopes. For actual Gemma evaluation commands, see [gemma-eval.md](gemma-eval.md).

## Visual audit

Removed the SYNTHETIC title/scenario labels from hero flows, the extra final PAGE FAULT key rail, and the generic two-cell scrollbar width. Final full-size screenshots need no visible scrollbar. Narrow views retain a one-cell functional scrollbar. The command rail stays dim; no complex idle fading was added. The panic now ends “scheduler is alive. useful work isn't.”

PC, registers and stack give way to the human report; NEXT EXECUTION remains pinned exactly once. Screenshots have been inspected for clipping, wrapping, duplicate instructions and focus brightness. Font glyph widths are used in SVG geometry rather than swapping a family name into mismatched Fira Code metrics. SVGs contain no remote font URLs or embedded font binaries.

The IRQ field's caret and flat Queue/Cancel buttons remain recognizable form controls. They are custom-styled Textual Input/Button widgets; the scheduler has no full-row blue highlight or default Footer. Keeping a familiar text caret helps keyboard usability.

## Verification and remaining limits

**153 tests pass**, including all 128 existing tests. The added checks exercise the actual Sentry SDK with a mocked transport: default off, flag zero, missing/invalid DSN, absent SDK, private path/name/content rejection, ambient scope stripping, allowed metrics, actual token counts, nested restoration, original exception preservation, and broken transport isolation. Public SVG checks reject local paths, remote font loading and hero watermarks and enforce one NEXT EXECUTION.

Two real eight-scenario Gemma runs were completed in a loopback-only namespace. They are independent of the offline unit suite. No private corpus was revisited in this phase.

Sentry's hosted Agent Tracing recognition, ingestion and dashboard screenshot still require a configured DSN and project access. The current local preview is an honest intermediate artifact. Actual model quality is imperfect; decision omissions and unsupported claims are published in the evaluation rather than concealed. Friend feedback remains uncollected. No article, challenge submission or Git push was performed.

README order now puts the PAGE FAULT hero first, then the story and scope screenshot, restoration explanation, IRQ GIF, thrashing/recovery GIFs, Gemma/Sentry rationale, privacy and finally installation.
