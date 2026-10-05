# THRASH / human kernel scope

Final submission media supersedes the historical specimens below: [Prompt 4 gallery](submission-assets.md).

Prompt 3 changes presentation, not the product model. The scheduler, thresholds, registry, privacy boundaries, extraction and canonical resume schema are unchanged.

## Removed

- The left process-table / right detail-card dashboard.
- Column headers, grid chrome, zebra stripes and full-row blue selection.
- The default Textual footer and command palette.
- Generic memory progress bars, colored dashboard panels and busy PANIC composition.
- Color as decoration. Normal operation uses near-black, bone and graphite.

## The signature

**Dispatch trace.** The horizontal axis spans the configured scheduler window. Each letter represents an actual dispatch to that process. `×` means two or more dispatches occupy one display cell; it does not increase the event count. `↑` marks an IRQ, `!` a reconstruction, and `◆` both. Gaps before any known execution use dots. Solid connecting segments indicate known dispatch continuity, not proof that a person worked continuously.

**Scheduler scar.** A separate dim trace uses recorded dispatches from 48–24 hours before the current time. Its scale is explicitly different from the current scheduler window. No history means a plainly labeled empty scar. No fabricated “yesterday.”

**Resident frames.** Every runnable process occupies one allocation unit, drawn as sixteen frames. Budget = `THRASH_MAX_ACTIVE × 16`. Overflow remains above the horizon and is labeled. Sleeping processes occupy frames below the horizon. A paging trace occurs only after a successful suspension; the letter follows the process actually suspended, including recovery from PANIC. These are scheduler admission units, not RAM. WSS≈ctx remains the existing saved-image-character estimate and is labeled separately.

**Core.** Current execution alone receives phosphor cyan. Its saved PC, registers, stack and next instruction remain visible. The small-terminal composition retains the PC and leaves the complete report under C.

**Scheduler cursor.** `▶` is selection, `⋯` starvation, `†` zombie residue and `◇` sleeping. Selection takes precedence over a secondary state glyph; the state name remains readable. Textual's DataTable still supplies proven keyboard/scroll mechanics internally, but renders one custom rail without headers, grids, zebra rows, hover fill or selection background.

**IRQ rail.** Each visible tick represents a pending interrupt, capped at 24 ticks with the actual total beside it. Only pending items can animate; quiet operation is stable. Input keeps its existing durable-queue semantics.

## Event → visual mapping

| Actual signal | Presentation |
|---|---|
| Switch-rate signal | Red dispatch path; dim displaced copy of the same trace |
| Working-set pressure | One-cell deterministic shift of page frames |
| Stale active images | Labeled stale-image trace, using actual affected aliases |
| Reconstruction signal | Echo of the latest recorded reconstructed destinations |
| Pending interrupts under pressure | Moving rail ticks; actual count stays fixed |
| Successful suspend | Page-out trace crossing the swap horizon |
| PANIC gates | Sparse centered recovery screen; no dashboard behind it |
| Recovery from PANIC | Progressive repaint of trace, allocation and core |

There is no random-number source in the effects. M / `THRASH_REDUCED_MOTION=1` removes displacement and staged reveals. Essential text and semantic colors have tested contrast of at least 4.5:1 against the normal background; decorative scars are intentionally dimmer and never the sole source of essential information.

## PAGE FAULT

The pending screen reports that the kernel operation is in progress. It does not animate made-up I/O percentages. Once the kernel returns a canonical report, the presentation reveals PC, registers and stack, then replaces those machine details with the human account:

- YOU WERE HERE: work summary and completed items, with inference/source labels.
- YOU DECIDED: decisions, recorded reasons and evidence.
- YOU STOPPED AT: the saved execution point.
- WHILE YOU WERE GONE: deterministic changes and stale-assumption evidence.
- STILL OPEN: unresolved work and blockers.
- NEXT EXECUTION: the canonical single instruction, pinned above the command rail.

Space skips the reveal; Enter returns after the resolved presentation. The report waits for the reader rather than disappearing on a timer. Esc can return while the kernel continues its already-started operation. An unavailable image or failed operation never says FAULT RESOLVED.

## PANIC and recovery

A sparse, centered screen shows actual runnable, switch, IRQ and stale-image counts. The initial title is red, then returns to bone. “Coherent working set lost” is explicitly labeled a **recovery advisory**, not a measurement of cognition.

S opens a READY-alias prompt; I opens the existing interrupt queue; C continues deliberately. Continuing acknowledges the presentation for that PANIC episode, rather than repeatedly trapping the user in it. A return below the existing PANIC gates resets this presentation acknowledgment. No lifecycle or heuristic rule is changed.

## Synthetic gallery

All scenes use temporary synthetic repositories, fixture images, simulated time and explicit kernel operations. No real local project or model call is used. All public identities are synthetic aliases.

| Requested view | Capture |
|---|---|
| NORMAL | [Stable kernel scope](examples/scope/01-normal.svg) |
| PAGE FAULT | [Human restoration](examples/scope/02-page-fault.svg), [PC/registers/stack stage](examples/scope/02b-registers-stack.svg) |
| PRESSURE | [Full resident allocation](examples/scope/03-pressure.svg) |
| THRASHING | [Dense dispatch trace](examples/scope/04-thrashing.svg) |
| KERNEL PANIC | [Sparse recovery screen](examples/scope/05-kernel-panic.svg) |
| RECOVERY | [Rebuilding the scope](examples/scope/06-recovery.svg), [settled](examples/scope/06b-recovered.svg) |
| IRQ capture | [Preserve current execution](examples/scope/07-irq-capture.svg) |
| Scheduler scar / trace | [Actual synthetic yesterday and today](examples/scope/08-scheduler-scar.svg) |
| Swap horizon / migration | [Paging out](examples/scope/09-swap-migration.svg), [saved allocations below the horizon](examples/scope/09b-swap-horizon.svg) |
| Compact terminal | [80×24](examples/scope/10-compact.svg) |

Reproduce with:

```bash
python demo/capture_scope.py
```

The SVG exporter explicitly preserves whitespace; some SVG renderers otherwise collapse leading spaces and misrepresent the terminal geometry.

**Strongest screenshot:** THRASHING. The historical scar, present trace collisions, occupied page frames and running core explain the product with the brand name hidden.

**Strongest transition:** PAGE FAULT → recovered PC/registers/stack → human report → pinned next execution → return to the scope. PANIC's disappearance and progressive rebuilding is the contrasting recovery moment.

**Still conventional:** text entry and confirmation prompts remain familiar form controls, intentionally. They are restyled Input/Button widgets. The scrolling substrate and keyboard machinery remain Textual; the main visual composition does not expose its default dashboard or footer.

## Verification

- 128 tests pass, preserving all 117 pre-redesign tests.
- New coverage includes time-cell collisions and markers, real-history scars, frame migration, canonical report immutability and redaction, 80×24 resizing, glyph navigation, sparse PANIC suspension/IRQ controls, signal-specific effects, contrast, and honest unavailable-image presentation.
- Synthetic captures were visually inspected at 120×44 and 80×24.
- A real pseudo-terminal smoke test rendered the scope, opened PAGE FAULT, captured an IRQ, and exited with status 0 and no traceback.
- No new inference, discovery, scheduler, cloud, surveillance or project-management feature was added.

## Implementation research

Two focused community sources informed implementation hygiene, not the art direction. Neither had comments providing independent confirmation.

- [Terminal themes tuned for prose legibility](https://dev.to/palo_alto_ai/terminal-themes-tuned-for-prose-legibility-not-syntax-highlighting-g7e), by [palo_alto_ai](https://dev.to/palo_alto_ai), tags `cli`, `design`, `showdev`, `tooling`: distinguish subdued decorative marks from text that must remain readable. THRASH uses its own bone/graphite/semantic palette and tests essential-text contrast.
- [The Textual bracket-markup failure](https://dev.to/nazarii-ahapevych/typecname-crashed-my-textual-tui-why-escaping-user-text-isnt-enough-3gp0), by [Nazarii Ahapevych](https://dev.to/nazarii-ahapevych), tags `python`, `tui`, `terminal`, `debugging`: retain literal Text renderables for repository/model/IRQ strings. Existing bracket-input tests remain green.


## Release palette and typeface

Recommended demo font: **Fira Code**. It is a capture preference, never a bundled runtime dependency. Final public media is in [the release gallery](submission-assets.md).

| Role | Color | Meaning |
|---|---|---|
| Background | `#090b0b` | Near black; PAGE FAULT uses black |
| Body | `#ddd7c9` | Warm bone |
| Secondary | `#858580` | Graphite; sleeping/swap also stay neutral |
| Historical scar | `#515552` | Faint, supplemental history |
| Execution | `#90c7c5` | Current core, cursor identity, endpoint, current frames and next action |
| Decision | `#c5a373` | Preserved human intent |
| Reason | `#b29876` | Dim warm decision explanation |
| IRQ | `#d9b56e` | Interrupt arrival and pending ideas |
| Drift | `#c68b68` | Rust; stale instructions and changed evidence |
| Blocker / thrashing | `#e77870` | Signal red, localized; PANIC flashes then returns to bone |
| Zombie | `#a49386` | Desaturated warm residue |

Only the executing project receives the cyan identity/frame accent; projects do not have individual brand colors. NOW is bone in a stable kernel, red in THRASHING/PANIC, with a cyan current endpoint. IRQ markers are gold, reconstruction markers rust, and the scar/echo remain dim. Color supplements labels and symbols. The main semantic text colors pass a 4.5:1 contrast check; the faint scar is deliberately supplemental.

The scheduler's foreground-priority setting preserves semantic colors under keyboard selection. IRQ inputs have no default background tint and buttons have no inherited bold style. A caret, focus underline and flat form controls remain for usability. PANIC retains its sparse layout and unchanged recovery controls.
