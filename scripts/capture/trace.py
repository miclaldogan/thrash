"""Render actual sanitized Sentry envelopes. This is NOT a hosted Sentry screenshot."""
import argparse
import html
import json
from pathlib import Path
from render import png,font


def render(source,destination):
    data=json.loads(source.read_text());fresh=data['results'][0]['traces'][0]
    cached=data['results'][0]['cached_traces'][0]
    rows=[]
    for event,title in ((fresh,'FIRST RESTORATION'),(cached,'SAVED IMAGE / NO INFERENCE')):
        rows.append((title,event['timestamp']-event['start_timestamp'],0,True))
        for span in sorted(event['spans'],key=lambda s:s['start_timestamp']):
            rows.append((span['description'],span['data'].get('duration_ms',0)/1000,
                         max(0,span['start_timestamp']-event['start_timestamp']),False))
    family,_=font();width=1320;height=240+len(rows)*37
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
         '<rect width="100%" height="100%" fill="#090b0b"/>',
         f'<g font-family="{family}, monospace" font-size="23" fill="#ddd7c9">',
         '<text x="45" y="55">PAGE FAULT / SENTRY ENVELOPE</text>',
         '<text x="45" y="91" fill="#858580">Local transport capture · measured durations · not a hosted dashboard</text>']
    scale=540/(fresh['timestamp']-fresh['start_timestamp'])
    for i,(name,seconds,offset,root) in enumerate(rows):
        y=150+i*37;color='#90c7c5' if 'gemma' in name else '#858580'
        out.append(f'<text x="{45 if root else 65}" y="{y}">{html.escape(name)}</text>')
        out.append(f'<text x="625" y="{y}" text-anchor="end" fill="{color}">{seconds*1000:.3f} ms</text>')
        out.append(f'<rect x="{690+offset*scale:.2f}" y="{y-16}" width="{max(2,seconds*scale):.2f}" height="13" fill="{color}"/>')
    out += [f'<text x="45" y="{height-45}" fill="#858580">No prompts. No completions. No project identities. SDK payloads captured offline.</text>','</g></svg>']
    destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text('\n'.join(out));png(destination,destination.with_suffix('.png'))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=Path('docs/eval/results.json'))
    p.add_argument('--output',type=Path,default=Path('docs/media/08-sentry-trace.svg'))
    args=p.parse_args();render(args.source,args.output)
