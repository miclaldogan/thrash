"""Build the frozen-corpus before/after report from measured runs and a bound review."""
import hashlib
import json
from pathlib import Path
import statistics

root=Path(__file__).resolve().parents[2]
d=json.loads((root/'docs/eval/results.json').read_text())
before=json.loads((root/'docs/eval/prompt4-results.json').read_text())
review=json.loads((root/'docs/eval/review.json').read_text())
assert review['outputs_sha256']==hashlib.sha256(json.dumps([r['output'] for r in d['results']],sort_keys=True).encode()).hexdigest(), 'Outputs changed: repeat the semantic review'
model_spans=[next(s for s in r['traces'][0]['spans'] if s['description']=='thrash.gemma.resume') for r in d['results']]
text=f'''# Gemma process-image evaluation: release gate

Eight unchanged, hand-authored synthetic repositories; actual local **{d['model']}**, no fine-tuning and no cloud judge. Run date: 2026-10-05. Ground truth, scenario selection and keyword scoring were **not changed** from Prompt 4. These development cases informed prompt revisions, so this is a regression check, **not a held-out generalization benchmark**.

| Frozen check | Before | After |
|---|---:|---:|
| Schema validity | {before['schema_valid']}/8 | {d['schema_valid']}/8 |
'''
for key,label in [('task','Current-task term coverage'),('next','Next-action term coverage'),('done','Completed-work coverage'),('decision','Decision coverage (includes one absence case)'),('reason','Reason coverage (includes two absence cases)'),('open','Unresolved-work coverage')]:
    text+=f"| {label} | {before['keyword_checks'][key]}/8 | {d['keyword_checks'][key]}/8 |\n"
text+=f'''
Final-run manual review: **{len(review['unsupported_claims'])} unsupported factual assertions flagged** (before: two). Additional semantic issues are recorded separately below. This review is not an independent human annotation or proof of zero other hallucinations.

Selected release-run runtime: **{d['runtime_seconds']:.3f} s**; median model HTTP span: **{statistics.median(s['data']['inference_ms'] for s in model_spans)/1000:.3f} s**; median complete fresh restore: **{d['median_restoration_seconds']:.3f} s**. Median saved-image restore: **{statistics.median(r['cached_seconds'] for r in d['results'])*1000:.3f} ms**, without another model call.

## Decision-extraction finding

All seven recorded decisions and all six recorded reasons were present after retrieval, ignore rules, redaction and final prompt assembly. None had been removed by privacy filtering. The old extraction produced empty decision arrays despite valid JSON. That isolated the failure to semantic generation, not missing evidence; it did not prove a single causal prompt defect.

The generic fix defines decisions as recorded choices, constraints, rejections, approvals or intentional deferrals; separates them from tasks, proposals and open questions; distinguishes explicit evidence from inferred preferences; and preserves a reason only when one is recorded. Pydantic field descriptions and the same output schema are now supplied in the prompt as well as Ollama's `format` argument, following [Ollama's guidance](https://docs.ollama.com/capabilities/structured-outputs). Saved-image compatibility, validation, one repair attempt and allowed-path filtering are unchanged. No scenario-specific answers or examples were added to the prompt.

The final review found {review['decision_summary']}

## Unsupported-assertion finding

Before, the summary described an unpassed test as a failed test and a pending calibration as completed. A later intermediate run additionally invented initial successful tests. An extractive-summary experiment requested verbatim evidence clauses; it was rejected because it harmed useful completed-work extraction and reintroduced a false decision. The selected release revision keeps the general tense/uncertainty guidance, without that extractive-summary constraint.

{review['assertion_summary']}

Other semantic findings:
'''
for finding in review['other_semantic_errors']:
    text+=f"- **{finding['scenario']} / {finding['field']}:** {finding['evidence']}\n"
if not review['other_semantic_errors']:text+='- No additional issue flagged in this bounded review.\n'
for finding in review['unsupported_claims']:
    text+=f"- **Unsupported: {finding['scenario']} / {finding['field']}:** {finding['claim']} — {finding['evidence']}\n"
text+='''
## Per-scenario frozen checks

✓ means the predeclared keyword/empty-field check passed. Matching terms do not prove truth; paraphrases can fail these checks. Absence cases remain in the denominators and are not treated as positive extraction.

| Scenario | Task | Completed | Decision | Reason | Open | Next | Restore s |
|---|---|---|---|---|---|---|---:|
'''
for r in d['results']:
    text+='| '+r['scenario']+' | '+' | '.join('✓' if r['checks'][k] else '—' for k in ('task','done','decision','reason','open','next'))+f" | {r['seconds']:.3f} |\n"
text+='''
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
'''
(root/'docs/gemma-eval.md').write_text(text)
