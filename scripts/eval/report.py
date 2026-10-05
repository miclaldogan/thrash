"""Build the honest evaluation report from measured results and an output-bound review."""
import hashlib
import json
from pathlib import Path
import statistics

root=Path(__file__).resolve().parents[2]
d=json.loads((root/'docs/eval/results.json').read_text())
review=json.loads((root/'docs/eval/review.json').read_text())
assert review['outputs_sha256']==hashlib.sha256(json.dumps([r['output'] for r in d['results']],sort_keys=True).encode()).hexdigest(), 'Outputs changed: repeat the semantic review'
model_spans=[next(s for s in r['traces'][0]['spans'] if s['description']=='thrash.gemma.resume') for r in d['results']]
text=f'''# Gemma process-image evaluation

Eight hand-authored synthetic repositories, one notes file each; actual local **{d['model']}**, no fine-tuning and no cloud judge. Run date: 2026-10-05. This is a small field-coverage check, not a general model benchmark.

The second run took **{d['runtime_seconds']:.3f} seconds**. Median inference (HTTP span) was **{statistics.median(s['data']['inference_ms'] for s in model_spans)/1000:.3f} s**; median complete fresh restoration was **{d['median_restoration_seconds']:.3f} s**. Median restoration from the resulting saved image was **{statistics.median(r['cached_seconds'] for r in d['results'])*1000:.3f} ms**, without another model call.

| Metric | Result | Interpretation |
|---|---:|---|
| Schema validity | {d['schema_valid']}/8 | Pydantic accepted all outputs; does not prove semantic correctness |
| Current-task coverage | {d['keyword_checks']['task']}/8 | Predetermined task terms present in program counter |
| Next-action coverage | {d['keyword_checks']['next']}/8 | One output dropped the requested rebuild step |
| Completed-work coverage | {d['keyword_checks']['done']}/8 | Five of seven recorded completions; the no-completion case correctly empty |
| Decision-field accuracy | {d['keyword_checks']['decision']}/8 | Only the no-decision case passed; **0/7 recorded decisions extracted** |
| Decision-reason accuracy | {d['keyword_checks']['reason']}/8 | Two absent reasons correctly blank; **0/6 recorded reasons extracted** |
| Unresolved-work coverage | {d['keyword_checks']['open']}/8 | Predetermined question terms present |
| Unsupported factual claims flagged | {len(review['unsupported_claims'])} | Manual comparison of saved outputs against ground truth |
| Additional misplaced-state field | {len(review['other_semantic_errors'])} | Pending work represented as last useful state |

## Per-scenario results

✓ means the predeclared keyword/empty-field check passed. Absence cases are included in the denominators above, not counted as successful positive extraction.

| Scenario | Task | Completed | Decision | Reason | Open | Next | Restore s |
|---|---|---|---|---|---|---|---:|
'''
for r in d['results']:
    text+='| '+r['scenario']+' | '+' | '.join('✓' if r['checks'][k] else '—' for k in ('task','done','decision','reason','open','next'))+f" | {r['seconds']:.3f} |\n"
text+='''
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
'''
(root/'docs/gemma-eval.md').write_text(text)
