# Final release gate — 2026-10-05

**READY TO PUSH: YES, after user review. Nothing has been pushed.** This is a local-first, fallible context-reconstruction tool, not a claim of perfect memory. The remaining semantic limitations below must accompany publication.

## Verification

| Gate | Result |
|---|---|
| Full suite | **159 passed**; all 153 prior tests retained, including all original 128 |
| Clean install | Fresh virtual environment, non-editable package build, dependency resolution/install from local cache; CLI help passed |
| No optional Sentry dependency | Clean install contained no `sentry_sdk`; normal operation succeeded |
| Default-off / explicit-off | Nine-scene demo run twice under a socket audit hook: **zero socket connections** with the flag absent and with `THRASH_SENTRY=0` |
| Local Gemma smoke/evaluation | Real `gemma3:4b` on all eight unchanged cases, in a namespace with only loopback; read-only installed weights and temporary synthetic repositories |
| Scripted demo | Installed `thrash demo --script` completed all scenes |
| Real terminal smoke | Installed TUI: demo → PAGE FAULT → IRQ capture → clean exit, no traceback |
| Privacy | Full suite includes ignored/excluded roots, symlinks, secret-like TODO/commit text, public paths and mocked Sentry transport checks |
| Public media | Seven final UI screenshot pairs and four GIFs regenerated with Fira Code; no hero watermarks, private paths, visible scrollbar artifacts or duplicate NEXT EXECUTION |
| Tracing | Actual SDK envelope capture verified locally; **hosted verification not performed**, no DSN/project access available; not a release blocker |
| Git / artifact audit | No real credentials/DSN, font binaries, private project paths/data, excluded names, runtime state, temporary capture frames or prompt files staged |
| Secret scan | No dedicated scanner installed; targeted tracked/staged-file pattern scan found no credential-shaped matches or real private paths |
| Publication | No push, tag, release upload, article publication or challenge submission performed |

The two existing untracked user prompt files remain untracked and untouched. `.venv`, bytecode and runtime fixtures remain ignored. The committed evaluation JSON contains intentional synthetic evidence and sanitized traces, not private runtime state.

Clean installation was performed with `uv pip install --offline` into a fresh temporary virtual environment, followed by installed-package CLI and demo checks. The full suite runs with `[dev,sentry]` and mocked model/Sentry transports; it requires no model or network. Real model evaluation is a separate, explicitly local verification.

## Evaluation gate

| Frozen metric | Before | Selected release revision |
|---|---:|---:|
| Valid schemas | 8/8 | 8/8 |
| Current-task keyword coverage | 8/8 | 7/8 |
| Next-action coverage | 7/8 | 8/8 |
| Completed-work coverage, including absence | 6/8 | 8/8 |
| Recorded decision coverage | 0/7 | 7/7 |
| Recorded reasons | 0/6 | 6/6 |
| Unsupported factual assertions flagged | 2 | 2 |

The task keyword miss is a faithful “audit uncited claims” paraphrase. Its score was not relaxed. Six of seven decisions retain a valid supporting path and explicit label; one has no valid source and is labeled inferred. A previously empty-completion case remains empty.

The two release assertions are both in the jaw-test summary: invented initial successful tests and an unwarranted claim of a failed turn test. The earlier calibration-completed claim is gone, but overall unsupported-assertion count has **not improved**. The summary remains fallible. One last-useful-state field is empty despite a completion being present elsewhere.

An extractive-summary experiment was **rejected** because it dropped four recorded completions, reintroduced a question-as-decision error and emitted a malformed resurrection hint. Its outputs remain committed. The selected run is an exact copy of the second revised run; the extraction code was restored to that revision and re-tested. The best isolated score from each run was not combined into a fictional result.

[Full before/after evaluation](gemma-eval.md) · [All trial outputs](eval/) · [Selected output-bound review](eval/review.json)

Frozen scenario SHA-256: `058619aaaa5b0a8761b4dcf423e49618838e43bf68c1852ff3f29ecd4f0fd0b4`. Both `scenarios.json` and the entire evaluation runner are byte-for-byte unchanged from Prompt 4. Prompt revisions used these development cases; this is not a held-out benchmark. Independent cases and human review remain future validation work, not claims of this release.

## Final visual identity

Recommended demo font: **Fira Code**. No font binaries are bundled or required at runtime. Capture geometry uses the font's measured 1200/1950-em advance. All UI media is 1320 × 906 px; GIFs are 6–8 seconds. The Sentry waterfall is a separately labeled local-envelope illustration.

Near-black + bone + graphite remain the base. Cyan identifies the current process, current frames and next execution; warm amber marks preserved intent; brighter gold marks interrupts; rust marks changed/stale evidence; red marks blockers and thrashing; swap stays neutral; zombie residue uses muted warm grey. Main semantic text colors meet the 4.5:1 contrast check. Dim historical traces are supplementary.

The cursor preserves foreground semantics, inputs have no inherited background tint and flat buttons have no inherited bold styling. Capture scripts pause periodic refresh/animation timers and drive actual kernel operations explicitly, avoiding inconsistent busy notices during rendering. Production timers and scheduler behavior are unchanged.

**Strongest screenshot:** [THRASHING](media/04-thrashing.png). **Strongest GIF and README hero:** [PAGE FAULT](media/page-fault.gif). PANIC remains a secondary sparse image. The only familiar generic elements are the intentionally usable text caret and flat form controls; no default Footer or blue table selection remains.

## Publication judgment

PAGE FAULT is useful because it exposes a canonical report with actual saved tasks, completion evidence, decisions/reasons, changed files, unresolved work and a next instruction. Fixture media demonstrates the flow; the real model evaluation establishes both improvements and limits. It remains necessary to review evidence and uncertain claims.

There is no blocking install, test, privacy or media issue identified. Hosted Sentry access is not a blocker under Prompt 5. **Do not publish claims of hallucination-free restoration, a held-out benchmark, verified hosted Agent Tracing, or real friend feedback.** Large-context performance, platform coverage beyond Linux and uncalibrated confidence remain limitations. The selected run's first restoration took about 91 seconds; warm fresh restorations were about 8–10 seconds, while saved-image returns remained milliseconds on these tiny cases.

The README opens with the product and PAGE FAULT, explains the friend/planner/OS story early, shows THRASHING, and explains local open-weight reconstruction before installation. Public demo provenance remains explicit. No new product mechanics were introduced.
