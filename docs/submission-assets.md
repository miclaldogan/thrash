# Submission assets

Recommended demo font: **Fira Code**, available as an installed local font. No font binary is copied into this repository. The app runs with ordinary monospace fonts. Captures reference local Fira Code and fall back to monospace; exported PNGs/GIFs need no font installation.

Public demos use simulated project histories and anonymized aliases. Prior real-project verification was read-only and private; no real project content, paths, notes or commits appear in these assets. The final hero views omit demo watermarks, but their provenance is not hidden here, in README, or in the article notes.

## Picks

- **README hero:** [page-fault.gif](media/page-fault.gif). It moves from the scheduler cursor through PC/registers/stack to the canonical human resume report and one NEXT EXECUTION.
- **Strongest static / DEV article lead:** [04-thrashing.png](media/04-thrashing.png). Dispatch collisions, the current core and page frames make the scheduler visible immediately. Follow with [02-page-fault.png](media/02-page-fault.png) to demonstrate useful restoration. PAGE FAULT remains the README hero GIF.
- **Strongest trace:** first fresh restoration versus the resulting saved-image return. The model call dominates the former; it is absent in the latter. [Local envelope preview](media/08-sentry-trace.png), **not a hosted Sentry screenshot**.
- **Most meaningful evaluation finding:** positive decision coverage improved from 0/7 to 7/7 on unchanged cases; six choices retain valid explicit sources. All recorded next steps and completions pass their coverage checks. Two unsupported summary assertions remain. [Full evidence](gemma-eval.md).

## GIFs

All are 1320 × 906 px, 8 fps, optimized indexed-color GIFs. Capture source is a 120-column × 40-row Textual terminal. Hold times are edited presentation timing, not inference latency.

| File | Duration | Size |
|---|---:|---:|
| [page-fault.gif](media/page-fault.gif) | 8.01 s | 140 KiB |
| [irq.gif](media/irq.gif) | 6.01 s | 195 KiB |
| [thrashing.gif](media/thrashing.gif) | 7.01 s | 196 KiB |
| [swap-recovery.gif](media/swap-recovery.gif) | 6.51 s | 202 KiB |

## Screenshots

Each has a PNG for embedding and an SVG source. The trace preview is 1320 × 758 px; UI captures are 1320 × 906 px.

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

Install `rsvg-convert`, `ffmpeg`, fontconfig and Fira Code locally if desired. No downloaded font, browser, recorder service or cloud renderer is required. `run.py` uses temporary repositories and fixture images; it never scans real projects. `trace.py` reads the already-sanitized evaluation envelopes. For actual Gemma evaluation commands, see [gemma-eval.md](gemma-eval.md).

## Visual audit

Removed the SYNTHETIC title/scenario labels from hero flows, the extra final PAGE FAULT key rail, and the generic two-cell scrollbar width. Final full-size screenshots need no visible scrollbar. Narrow views retain a one-cell functional scrollbar. The command rail stays dim; no complex idle fading was added. The panic now ends “scheduler is alive. useful work isn't.”

PC, registers and stack give way to the human report; NEXT EXECUTION remains pinned exactly once. Screenshots have been inspected for clipping, wrapping, duplicate instructions and focus brightness. SVG geometry uses the measured Fira Code advance (1200/1950 em), preserving alignment across semantic color boundaries. SVGs contain no remote font URLs or embedded font binaries.

The IRQ field's caret and flat Queue/Cancel buttons remain recognizable form controls. They are custom-styled Textual Input/Button widgets; the scheduler has no full-row blue highlight or default Footer. Keeping a familiar text caret helps keyboard usability.

## Verification and remaining limits

**159 tests pass**, including all 128 existing tests. The added checks exercise the actual Sentry SDK with a mocked transport: default off, flag zero, missing/invalid DSN, absent SDK, private path/name/content rejection, ambient scope stripping, allowed metrics, actual token counts, nested restoration, original exception preservation, and broken transport isolation. Public SVG checks reject local paths, remote font loading and hero watermarks and enforce one NEXT EXECUTION.

The Prompt 4 baseline runs and three Prompt 5 eight-scenario trials were completed in a loopback-only namespace. The selected revision and rejected trial are identified in the evaluation. They are independent of the offline unit suite. No private corpus was revisited in this phase.

Hosted Sentry verification was not performed: no DSN/project access was available. The local preview is explicitly labeled and this does not block release. Actual model quality is imperfect; the before/after decision results, missing source, and unsupported claims are disclosed in the evaluation. Friend feedback remains uncollected. No article, challenge submission or Git push was performed.

[Final release gate](release-gate.md) records the clean install, offline smoke, real Gemma runs and publication checks.

README order now puts the PAGE FAULT hero first, then the story and scope screenshot, restoration explanation, IRQ GIF, thrashing/recovery GIFs, Gemma/Sentry rationale, privacy and finally installation.
