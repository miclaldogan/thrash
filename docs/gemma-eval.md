# Gemma process-image evaluation: release gate

Eight unchanged, hand-authored synthetic repositories; actual local **gemma3:4b**, no fine-tuning and no cloud judge. Run date: 2026-10-05. Ground truth, scenario selection and keyword scoring were **not changed** from Prompt 4. These development cases informed prompt revisions, so this is a regression check, **not a held-out generalization benchmark**.

| Frozen check | Before | After |
|---|---:|---:|
| Schema validity | 8/8 | 8/8 |
| Current-task term coverage | 8/8 | 7/8 |
| Next-action term coverage | 7/8 | 8/8 |
| Completed-work coverage | 6/8 | 8/8 |
| Decision coverage (includes one absence case) | 1/8 | 8/8 |
| Reason coverage (includes two absence cases) | 2/8 | 8/8 |
| Unresolved-work coverage | 8/8 | 8/8 |

Final-run manual review: **2 unsupported factual assertions flagged** (before: two). Additional semantic issues are recorded separately below. This review is not an independent human annotation or proof of zero other hallucinations.

Selected release-run runtime: **157.232 s**; median model HTTP span: **9.739 s**; median complete fresh restore: **9.822 s**. Median saved-image restore: **2.384 ms**, without another model call.

## Decision-extraction finding

All seven recorded decisions and all six recorded reasons were present after retrieval, ignore rules, redaction and final prompt assembly. None had been removed by privacy filtering. The old extraction produced empty decision arrays despite valid JSON. That isolated the failure to semantic generation, not missing evidence; it did not prove a single causal prompt defect.

The generic fix defines decisions as recorded choices, constraints, rejections, approvals or intentional deferrals; separates them from tasks, proposals and open questions; distinguishes explicit evidence from inferred preferences; and preserves a reason only when one is recorded. Pydantic field descriptions and the same output schema are now supplied in the prompt as well as Ollama's `format` argument, following [Ollama's guidance](https://docs.ollama.com/capabilities/structured-outputs). Saved-image compatibility, validation, one repair attempt and allowed-path filtering are unchanged. No scenario-specific answers or examples were added to the prompt.

The final review found all seven recorded choices and all six recorded reasons, with no extra decision in the no-decision case and no question-as-decision false positive. Six of seven choices have a valid notes.md source and explicit=true; circuit-garden has an empty source and is labeled inferred. Coverage is not the same as fully grounded extraction.

## Unsupported-assertion finding

Before, the summary described an unpassed test as a failed test and a pending calibration as completed. A later intermediate run additionally invented initial successful tests. An extractive-summary experiment requested verbatim evidence clauses; it was rejected because it harmed useful completed-work extraction and reintroduced a false decision. The selected release revision keeps the general tense/uncertainty guidance, without that extractive-summary constraint.

The calibration-completed assertion is gone, but game-alpha still describes an unpassed test as a failure and additionally invents initial successful tests. The unsupported-assertion count remains two, not zero. A third extractive-summary trial reduced invented prose but omitted four recorded completions, reintroduced a question-as-decision false positive and produced a malformed resurrection hint. That trial was rejected; its full outputs remain available. The more useful second revision is the release candidate, with these limitations disclosed.

Other semantic findings:
- **circuit-garden / decisions.source:** Recorded choice and reason are preserved, but no supporting source survived; the choice is labeled inferred. Pre-sanitization output was not retained, so the cause of source loss is not established.
- **film-study / last_useful_state:** Empty despite the rough-cut completion being correctly preserved in completed.
- **paper-crane / program_counter:** A faithful audit-uncited-claims paraphrase fails the frozen citation keyword; the raw 7/8 score is retained.
- **Unsupported: game-alpha / summary:** after it passed initial tests — No initial successful tests are recorded.
- **Unsupported: game-alpha / summary:** turn test failure — The rig has not passed the test; the evidence does not establish a performed failed test.

## Per-scenario frozen checks

✓ means the predeclared keyword/empty-field check passed. Matching terms do not prove truth; paraphrases can fail these checks. Absence cases remain in the denominators and are not treated as positive extraction.

| Scenario | Task | Completed | Decision | Reason | Open | Next | Restore s |
|---|---|---|---|---|---|---|---:|
| game-alpha | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 90.851 |
| paper-crane | — | ✓ | ✓ | ✓ | ✓ | ✓ | 9.899 |
| vision-lab | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10.157 |
| circuit-garden | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 9.827 |
| film-study | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 9.176 |
| signal-box | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 8.272 |
| ink-orbit | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 9.202 |
| stone-bridge | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 9.816 |

## All runs remain available

- [Initial Prompt 4 baseline](eval/baseline.json): 124.029 s, the initial 0/7 positive decision result.
- [Prompt 4 measured before-run](eval/prompt4-results.json) and [its review](eval/prompt4-review.json): repeated baseline with detailed timings.
- [First Prompt 5 attempt](eval/prompt5-initial.json): decisions recovered, but an open question was also emitted as a decision. Completed/task/next coverage remained imperfect.
- [Second Prompt 5 attempt](eval/prompt5-grounding.json): removed that question-as-decision false positive, but summaries still invented test outcomes and one decision lost its source.
- [Rejected extractive-summary trial](eval/prompt5-extractive-rejected.json): completed coverage fell to 4/8, a question again became a decision, and a resurrection hint contained stray JSON-like text.
- [Selected release run](eval/results.json) and [output-hash-bound review](eval/review.json): the second revision is retained for its better overall restoration quality. `results.json` is an exact copy of `prompt5-grounding.json`; the code was restored to that revision. All scenarios and rejected trial outputs remain available.

The original [scenario file](../scripts/eval/scenarios.json) and `score()` in [the runner](../scripts/eval/run.py) are unchanged. Current-task coverage can fall for a faithful paraphrase: “Audit the three uncited claims” lacks the frozen term “citation.” The raw score is retained rather than relaxing the grader.

## Reproduce

```sh
pip install -e ".[dev,sentry]"
# Requires already-installed local gemma3:4b weights and Ollama:
python scripts/eval/run.py --output docs/eval/results.json
# Linux bubblewrap, only loopback available and read-only weights:
python scripts/eval/isolated.py --output docs/eval/results.json
# Repeat the manual semantic review, update review.json, then:
python scripts/eval/report.py
```

The runner uses a mocked Sentry transport by default even if a DSN exists. `--upload` additionally requires `THRASH_SENTRY=1` and `SENTRY_DSN` and sends only sanitized envelopes, never source notes or model outputs. The isolated runner cannot upload. Hosted Sentry verification was not performed.

All real runs use temporary repositories and a fresh isolated server. First-call timing includes model loading and prompt evaluation; later calls reuse that server. Single observations on eight small cases do not establish production accuracy, generalization or robust latency estimates. Confidence is model-reported and uncalibrated. Hero GIFs use fixture images; they do not prove model quality.
