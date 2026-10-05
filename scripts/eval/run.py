"""Eight synthetic repositories; actual local inference, never a cloud judge.

Run with a local Ollama server. Scores are transparent keyword checks, NOT an
LLM quality benchmark. Review the saved synthetic outputs for unsupported claims.
"""
import argparse
import json
import os
from pathlib import Path
import statistics
import tempfile
import time

from thrash.config import Config
from thrash.scheduler import Kernel
from thrash import tracing

SCENARIOS = Path(__file__).with_name('scenarios.json')

def score(case, image):
    fields = {'task':image['program_counter']['task'], 'done':' '.join(x['text'] for x in image['completed']),
        'decision':' '.join(x['text'] for x in image['decisions']),
        'reason':' '.join(x['reason'] for x in image['decisions']),
        'open':' '.join(image['unresolved']), 'next':image['next_action']}
    return {k: (all(any(term in fields[k].lower() for term in alternatives.split('|'))
                    for alternatives in terms) if terms else not fields[k].strip())
            for k,terms in case['terms'].items()}


def run(destination, model='gemma3:4b', upload=False):
    from sentry_sdk.transport import Transport
    from sentry_sdk import Client
    envelopes=[]
    class Recorder(Transport):
        def capture_envelope(self,envelope):
            for item in envelope.items:
                if item.headers.get('type')=='transaction':envelopes.append(item.payload.json)
    # Always record the real SDK envelope locally; no network transport unless explicitly requested.
    sink=Client(dsn='https://public@example.invalid/1',transport=Recorder,
                default_integrations=False,auto_enabling_integrations=False,
                send_default_pii=False,send_client_reports=False,auto_session_tracking=False,
                before_send_transaction=tracing.scrub_transaction)
    live=tracing._get_client() if upload else None
    if upload and live is None:raise RuntimeError('Upload requires THRASH_SENTRY=1 and SENTRY_DSN')
    previous_get=tracing._get_client
    tracing._get_client=lambda:sink
    results=[];started=time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix='thrash-eval-') as tmp:
            for case in json.loads(SCENARIOS.read_text()):
                root=Path(tmp)/case['id'];root.mkdir()
                text=f"PURPOSE: Small personal experiment.\nCURRENT / STOPPED AT: {case['task']}\n"
                if case['done']:text+=f"FINISHED: {case['done']}\n"
                else:text+='Nothing has been completed. PLANNED ONLY: finish the booklet.\n'
                if case['decision']:text+=f"DECISION: {case['decision']}\n"
                else:text+='No decision has been made. PROPOSAL ONLY: change transport.\n'
                if case['reason']:text+=f"WHY: {case['reason']}\n"
                text+=f"UNRESOLVED: {case['open']}\nNEXT: {case['next']}\n"
                (root/'notes.md').write_text(text)
                cfg=Config(data_dir=Path(tmp)/('state-'+case['id']),model=model)
                kernel=Kernel(cfg)
                proc=kernel.reg.register(case['id'],root,time.time())
                before=len(envelopes);t0=time.perf_counter()
                report=kernel.restore(proc)
                elapsed=time.perf_counter()-t0
                result={'scenario':case['id'],'seconds':round(elapsed,3),'schema_valid':report.image is not None}
                if report.image:
                    output=report.image.model_dump(exclude={'meta','project'})
                    result.update(checks=score(case,output),output=output)
                else:result.update(error_kind=report.error_kind,checks={})
                result['traces']=envelopes[before:]
                before_cached=len(envelopes);cached_start=time.perf_counter()
                kernel.restore(proc, reconstruct=False)
                result['cached_seconds']=round(time.perf_counter()-cached_start,6)
                result['cached_traces']=envelopes[before_cached:]
                results.append(result)
                print(case['id'],result['schema_valid'],result.get('checks'),f'{elapsed:.2f}s',flush=True)
        if live:
            from sentry_sdk import Scope
            for event in envelopes:live.capture_event(event,scope=Scope())
            live.flush(timeout=10)
        summary={'model':model,'scenario_count':len(results),'runtime_seconds':round(time.perf_counter()-started,3),
                 'median_restoration_seconds':round(statistics.median(r['seconds'] for r in results),3),
                 'schema_valid':sum(r['schema_valid'] for r in results),
                 'keyword_checks':{k:sum(r['checks'].get(k,False) for r in results) for k in ('task','done','decision','reason','open','next')},
                 'uploaded':bool(live),'results':results}
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(json.dumps(summary,indent=2)+'\n')
    finally:
        tracing._get_client=previous_get;sink.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--model',default='gemma3:4b');p.add_argument('--upload',action='store_true')
    args=p.parse_args();run(args.output,args.model,args.upload)
