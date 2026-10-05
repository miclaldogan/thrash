# Gemma process-image evaluation

Eight hand-authored synthetic repositories, one notes file each; actual local **gemma3:4b**, no fine-tuning and no cloud judge. Run date: 2026-10-05. This is a small field-coverage check, not a general model benchmark.

The second run took **123.404 seconds**. Median inference (HTTP span) was **6.386 s**; median complete fresh restoration was **6.462 s**. Median restoration from the resulting saved image was **1.982 ms**, without another model call.

| Metric | Result | Interpretation |
|---|---:|---|
| Schema validity | 8/8 | Pydantic accepted all outputs; does not prove semantic correctness |
| Current-task coverage | 8/8 | Predetermined task terms present in program counter |
| Next-action coverage | 7/8 | One output dropped the requested rebuild step |
| Completed-work coverage | 6/8 | Five of seven recorded completions; the no-completion case correctly empty |
| Decision-field accuracy | 1/8 | Only the no-decision case passed; **0/7 recorded decisions extracted** |
| Decision-reason accuracy | 2/8 | Two absent reasons correctly blank; **0/6 recorded reasons extracted** |
| Unresolved-work coverage | 8/8 | Predetermined question terms present |
| Unsupported factual claims flagged | 2 | Manual comparison of saved outputs against ground truth |
| Additional misplaced-state field | 1 | Pending work represented as last useful state |

## Per-scenario results

✓ means the predeclared keyword/empty-field check passed. Absence cases are included in the denominators above, not counted as successful positive extraction.

| Scenario | Task | Completed | Decision | Reason | Open | Next | Restore s |
|---|---|---|---|---|---|---|---:|
| game-alpha | ✓ | — | — | — | ✓ | ✓ | 80.397 |
| paper-crane | ✓ | ✓ | — | — | ✓ | ✓ | 6.425 |
| vision-lab | ✓ | ✓ | — | — | ✓ | ✓ | 6.507 |
| circuit-garden | ✓ | ✓ | — | — | ✓ | ✓ | 6.499 |
| film-study | ✓ | — | — | ✓ | ✓ | ✓ | 5.407 |
| signal-box | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 6.228 |
| ink-orbit | ✓ | ✓ | — | — | ✓ | ✓ | 5.382 |
| stone-bridge | ✓ | ✓ | — | — | ✓ | — | 6.536 |

## What failed

The model omitted every recorded decision even though every JSON property was schema-required. Empty arrays satisfy that schema. Two recorded completions were omitted from `completed` but survived in `last_useful_state`; four of the five returned completions were marked inferred despite explicit notes. The summary asserted a failed jaw test when the notes only said it had not passed, and described calibration as completed when only wiring had been verified. A pending margin test also appeared as `last_useful_state`.

The next-action miss kept “delete one test page” but omitted “rebuild the local index.” That is partial coverage, not an unrelated instruction. Confidence values of 0.8–0.95 did not reliably expose the omissions.

These are material limitations of the current extractor. The UI can present a complete canonical report, but the real model does not always supply all its fields. **Do not use the fixture hero GIF as proof of decision extraction quality.** No prompt or semantic architecture was changed to make this score look better.

## Reproduce

```sh
pip install -e ".[dev,sentry]"
# Local Ollama already has gemma3:4b installed:
python scripts/eval/run.py --output docs/eval/results.json
# Linux, bubblewrap: a separate network namespace containing only loopback:
python scripts/eval/isolated.py --output docs/eval/results.json
# Repeat the manual output review, update review.json, then:
python scripts/eval/report.py
```

The evaluation runner defaults to a mocked Sentry transport even if the caller has a DSN. `--upload` is a separate explicit choice and also requires `THRASH_SENTRY=1` and `SENTRY_DSN`; only sanitized envelopes are uploaded, never evaluation notes or outputs. The isolated runner cannot upload.

Ground truth and exact keyword alternatives: [scenarios.json](../scripts/eval/scenarios.json). Full synthetic model outputs and actual SDK envelopes: [results.json](eval/results.json). The initial run is preserved as [baseline.json](eval/baseline.json): 124.029 s total, the same field scores. [review.json](eval/review.json) records two unsupported assertions and one misplaced-state field, bound to a hash of the reviewed outputs.

Both runs used read-only installed weights and temporary repositories in a loopback-only namespace. First-call timings include model initialization and prompt evaluation. The seven subsequent calls reuse that server. These are single observations per scenario, not statistically robust latency estimates. Scoring checks chosen terms or required emptiness; paraphrases can cause false negatives, and matching words do not establish factual truth. Manual review is not exhaustive or independent human annotation.
