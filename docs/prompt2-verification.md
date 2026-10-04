# Prompt 2 verification

Prompt 2 builds on the accepted 91-test foundation. Its scope is useful restoration first, then the terminal kernel and creative layer. No real-project corpus was needed for these additions. All new fixtures and public captures are synthetic.

## Shipped behavior

| Area | Result |
|---|---|
| Resume | One typed report for switch, wake, status and TUI: work summary, completions, decisions/reasons, stopping point, files, changes, unresolved work, blockers, evidence and next instruction |
| Compatibility | Older images/registries load with defaults; absent completions/reasons are explicit blanks; original CLI behavior remains except deliberate extreme-pressure admission |
| TUI | Process table, WSS estimate, reconstruction count, image age, selected instruction, dispatch history, memory map, IRQ queue, scrollable reports and core inspection |
| IRQs | Atomic redacted queue; capture does not dispatch; optional local advisory routing; acknowledgment; input during a busy TUI worker is retained |
| Starvation | READY wait + competing dispatches + little recorded execution; no warning from folder age alone |
| Zombies | Existing idle-plus-residue rule preserved; evidence shown; no invented cross-project or psychological explanation |
| Admission | OUT OF MIND at configurable active threshold; force, suspend, queue or cancel; never auto-kill |
| Modes | Existing scheduler signals drive NORMAL/PRESSURE/THRASHING; four conjunctive gates add PANIC |
| Effects | Labeled echoes of real dispatches, memory redraw traces, paging trace, pressure colors, gradual recovery, reduced motion |
| Demo | Nine labeled synthetic scenes in temporary isolated state; no Gemma required; CLI transcript and interactive N-to-advance flow |
| Core semantics | Purpose, completed/unfinished work, decisions/reasons, failures, intention and recorded return condition survive serialization |

## Tests and installation

- **117 tests pass**, including all accepted foundation tests. Tests use temporary synthetic repositories and mocked inference; no internet or Gemma required.
- Textual keyboard tests cover restore, literal bracket text, IRQ capture, suspend, wake, acknowledgment, cancellation and confirmation of termination, core inspection, and IRQ entry during a deliberately slow worker.
- CLI checks cover no-argument noninteractive help, empty IRQ rejection, queue acknowledgment, OUT OF MIND without mutation, suspend-before-admission, semantic refresh and demo isolation.
- A clean environment installed version **0.2.0** from the package; `--version` and `--help` succeeded.
- An installed-build pseudo-terminal smoke test opened the synthetic demo, advanced to PAGE FAULT, opened and submitted an IRQ, and exited normally with status 0 and no traceback.
- Synthetic SVGs were inspected at 120×40 and 80×24. Narrow terminals now give the process table full width. PANIC recovery copy wraps without being clipped.
- The sandbox blocks a local asyncio thread-wakeup primitive: even a minimal `asyncio.to_thread` script hung there on shutdown. TUI tests passed with that local restriction relaxed. This was not worked around by adding sleeps to the application.

## Live local Gemma check

The new extraction schema was exercised on a temporary synthetic project using **gemma3:4b**, with THRASH and a temporary Ollama server in a Linux network namespace whose only interface was `lo`. Model weights were mounted read-only. No model download, cloud service, real-project data or physical Wi-Fi toggle was involved.

The first response passed validation but omitted part of the newly requested restoration content. The generation schema previously required only the program counter. New generation now explicitly requires every restoration field and nested decision/completion field; empty values remain valid when evidence is absent. Legacy disk schemas remain backward-compatible.

The rerun produced:

- a work summary and one completed item;
- the rig-validation decision and its recorded reason;
- a stopping point and unresolved shoulder-deformation question;
- one immediate instruction: “Validate the shoulder's deformation during a 45-degree turn.”
- deterministic LOW drift after a note changed.

The completed item remained labeled **inferred**, as the model emitted it that way. The system did not upgrade the claim's certainty. The model returned no blockers. These are actual model choices, not fixture assertions about quality.

Extraction took **84.33 seconds** in this single isolated run. Do not present the old 3.6–5.6 second smaller-image timing as a benchmark for the new schema. Existing-image restoration makes no model call unless a reconstruction is necessary. Optional IRQ routing returned **unclear** and kept the capture. That result does not demonstrate accurate routing across multiple projects.

Evidence: [actual report](examples/resume-gemma.txt), [machine-readable summary](examples/resume-gemma-verification.json), [rendered report](examples/resume-gemma.svg). The 71-hour snapshot age was simulated and is labeled in the capture.

## Reproduce the public visuals

```bash
thrash demo --script
python demo/capture_tui.py
```

`capture_tui.py` creates fixture-only SVGs under `docs/examples/`. It does not regenerate the separately labeled live-Gemma evidence.

- [Normal kernel](examples/kernel-normal.svg)
- [Full PAGE FAULT fixture](examples/resume-fixture.svg)
- [PANIC](examples/kernel-panic.svg)
- [Recovery](examples/kernel-recovery.svg)
- [Working sets paged to swap](examples/kernel-memory.svg)

The best product image is PAGE FAULT with completed work, a decision reason and a concrete next instruction. The best wide terminal image is PANIC with STARVED/ZOMBIE evidence and recovery controls. The strongest fifteen seconds are restore → understand why → capture an IRQ without switching; see [demo-script.md](demo-script.md).

## Deliberate limits

- No shell integration, exports, semantic contradiction engine, daemon, automatic prioritization, deadline planner or background surveillance was added.
- Visual corruption is confined to labeled traces and pressure styling. Authoritative process rows are not duplicated or displaced. This keeps the warning readable and prevents effects from becoming fake metrics.
- PANIC is an advisory; there is no forced recovery or automatic killing. A deliberate choice to continue remains possible.
- A restored next instruction is saved context; drift can make it stale. The UI labels this and offers refresh instead of silently inventing a replacement.
- Source existence is checked; source existence does not prove a model statement is true. Decision reasons and completions still need human review.
- The heuristic thresholds remain unvalidated defaults. READY timestamps are precise only for transitions recorded by the new version; legacy state falls back to registration time.
- Multiple simultaneous CLI/TUI writers are not transactionally coordinated. In-app operations are serialized; avoid concurrent mutations from separate processes.
- IRQ routing is optional and shallow (text + public aliases). There is no interactive routing approval workflow in the TUI; use `irq --route` for a suggestion.
- A busy TUI operation must finish before normal Q exit. IRQs entered during it are visibly pending in the interface until persisted; an abrupt process kill can lose those pending keystrokes.
- Only Linux has been tested. No real friend feedback has been invented.

## Incremental history

The accepted foundation was checkpointed before Prompt 2. Separate commits then added canonical resume reports, durable IRQs, derived diagnostics, explicit admission, the TUI, visual pressure/demo, and verification-driven fixes. Tests passed before each implementation commit. No public push was performed as part of this work.
