"""Pure visual language for the human kernel. Every mark has a measured source."""
from __future__ import annotations
from dataclasses import dataclass
from string import ascii_uppercase, ascii_lowercase, digits
from rich.text import Text
from .registry import State
from . import ui

BONE = '#ddd7c9'
GRAPHITE = '#858580'
FAINT = '#515552'
CYAN = '#90c7c5'
AMBER = '#d2ac70'
RUST = '#cf986e'
RED = '#e77870'
BACKGROUND = '#090b0b'
FRAMES_PER_UNIT = 16


def tokens(view):
    names = [r['proc'].alias for r in view.rows]
    for e in view.events:
        for key in ('from_project', 'to_project'):
            if e.get(key) and e[key] not in names:
                names.append(e[key])
    alphabet = ascii_uppercase + ascii_lowercase + digits
    return {name: alphabet[i] if i < len(alphabet) else '?' for i, name in enumerate(names)}


@dataclass(frozen=True)
class Trace:
    line: str
    marks: str
    dispatches: int
    irqs: int
    faults: int
    collisions: int


def trace(events, start, end, width, code):
    """Fixed time axis; × means multiple dispatches in a cell, never extra events."""
    width = max(1, width)
    switches = sorted((e for e in events if e.get('type') == 'switch' and start <= e['ts'] < end), key=lambda e:e['ts'])
    cells = [[] for _ in range(width)]
    markers = [set() for _ in range(width)]
    def col(ts):
        return min(width-1, max(0, int((ts-start)/max(1,end-start)*width)))
    for e in switches:
        cells[col(e['ts'])].append(code.get(e.get('to_project'), '?'))
    irq_count = fault_count = 0
    for e in events:
        if not start <= e['ts'] < end:
            continue
        if e.get('type') == 'irq':
            markers[col(e['ts'])].add('↑')
            irq_count += 1
        if e.get('type') in ('switch', 'wake') and e.get('reconstructed'):
            markers[col(e['ts'])].add('!')
            fault_count += 1
    known = any(e.get('type') == 'switch' and e['ts'] < start for e in events)
    line = []
    for cell in cells:
        if cell:
            known = True
            line.append(cell[0] if len(cell) == 1 else '×')
        else:
            line.append('─' if known else '·')
    marks = ''.join('◆' if len(m)>1 else next(iter(m)) if m else ' ' for m in markers)
    return Trace(''.join(line), marks, len(switches), irq_count, fault_count,
                 sum(len(c)>1 for c in cells))


def dispatch_text(view, width=100, phase=0, motion=False, compact=False):
    code = tokens(view)
    span = view.diagnostics.report.window_hours*3600
    # Include events at precisely now while preserving half-open windows.
    current = trace(view.events, view.now-span, view.now+.001, max(16,width-15), code)
    scar = trace(view.events, view.now-48*3600, view.now-24*3600, max(16,width-15), code)
    out = Text('01   DISPATCH TRACE', style=BONE)
    out.append(f'   {current.dispatches}/{span/3600:g}h · scar −48..−24h\n' if compact else
               f'     {current.dispatches} dispatches / {span/3600:g}h · scar −48h..−24h\n', style=GRAPHITE)
    out.append('     SCAR  ', style=FAINT)
    out.append(scar.line if scar.dispatches else 'no recorded dispatches in this interval', style=FAINT)
    out.append('\n', style=FAINT)
    out.append('     NOW   ', style=GRAPHITE)
    out.append(current.line+'▶\n', style=RED if 'switch rate' in view.diagnostics.report.fired else BONE)
    out.append('           '+current.marks+'\n', style=AMBER)
    if not compact:
        out.append('           ↑ IRQ   ! reconstruction   ◆ both   × multiple dispatches / cell\n', style=GRAPHITE)
    if motion and 'switch rate' in view.diagnostics.report.fired:
        out.append('     ECHO  '+' '* (phase%2)+current.line[:max(1,width-17)]+'\n', style=FAINT)
    out.rstrip()
    return out


def allocations(view):
    resident, swapped, retired = [], [], []
    for row in view.rows:
        p = row['proc']
        if p.state in (State.RUNNING, State.READY): resident.append(p.alias)
        elif p.state == State.SLEEPING: swapped.append(p.alias)
        else: retired.append(p.alias)
    return resident, swapped, retired


def page_text(view, width=100, phase=0, motion=False, migration=None, compact=False):
    code = tokens(view)
    resident, swapped, retired = allocations(view)
    report = view.diagnostics.report
    # Pressure uses the same active/limit ratio as the scheduler; zero limit means no allocation cap.
    capacity = max(0, view.capacity)
    slots = max(capacity, len(resident)) * FRAMES_PER_UNIT
    cols = 32 if width >= 50 else 16
    glyphs = ''.join(code[a]*FRAMES_PER_UNIT for a in resident).ljust(slots, '·')
    out = Text('02   RESIDENT WORKING SET', style=BONE)
    out.append(f'     {len(resident)}/{capacity} scheduler units', style=GRAPHITE)
    if len(resident)>capacity: out.append(f'  +{len(resident)-capacity} OVERFLOW', style=RED)
    out.append('\n')
    jitter = ' ' if motion and 'working-set pressure' in report.fired and phase%2 else ''
    def blocks(chars):
        return ' '.join(chars[i:i+4] for i in range(0,len(chars),4))
    for i in range(0,max(1,len(glyphs)),cols):
        prefix = '   + ' if i >= capacity*FRAMES_PER_UNIT and capacity else '     '
        out.append(prefix+jitter+blocks(glyphs[i:i+cols])+'\n', style=RED if prefix=='   + ' else BONE)
    if not glyphs: out.append('     no runnable allocation\n', style=GRAPHITE)
    if migration:
        alias,ticks = migration
        out.append('     '+code.get(alias,'?')+' '+('│' if ticks>2 else '↓')+' PAGE OUT · saved working set\n', style=CYAN)
    horizon = '─'*max(4,min(30,(width-24)//2))
    out.append(f'     {horizon} SWAP HORIZON {horizon}\n', style=GRAPHITE)
    if swapped:
        swap = ''.join(code[a]*FRAMES_PER_UNIT for a in swapped)
        for i in range(0,len(swap),cols):
            out.append('     ░ '+blocks(swap[i:i+cols])+' ░\n', style=GRAPHITE)
    else: out.append('     ░ no paged-out processes ░\n', style=FAINT)
    out.append('     16 frames = 1 scheduler unit · allocation, NOT RAM\n', style=GRAPHITE)
    if not compact:
        out.append('     '+ui.safe(' · '.join(f'{code[a]} {a}' for a in resident+swapped))+'\n', style=GRAPHITE)
    for a in retired:
        row = next(r for r in view.rows if r['proc'].alias == a)
        out.append(f"     {code[a]} {a} · {'CORE' if row.get('core_saved') else 'RETIRED'}\n", style=FAINT)
    out.rstrip()
    return out


def core_text(view, selected=None, compact=False, width=100):
    row = next((r for r in view.rows if r['proc'].state == State.RUNNING), None)
    code = tokens(view)
    out = Text('03   CORE / 0', style=BONE)
    if row is None:
        out.append('     IDLE · select a process and dispatch with Enter\n', style=GRAPHITE)
        if selected:
            out.append(f'     PROBE {code.get(selected,"?")} / {ui.safe(selected)} · C reads saved context\n', style=GRAPHITE)
        return out
    p = row['proc']
    out.append(f'     ● {code[p.alias]} / {ui.safe(p.alias)}  RUNNING\n', style=CYAN)
    cf = view.images.get(p.alias)
    if not cf:
        out.append('     PC └ no image loaded · R requests local reconstruction\n', style=GRAPHITE)
        return out
    img = cf.image
    out.append('     PC └ '+ui.safe(img.program_counter.task or 'Not recorded.')+'\n', style=BONE)
    if compact:
        lines=out.split('\n')
        for line in lines: line.truncate(width, overflow='ellipsis')
        out=Text('\n').join(lines)
        out.rstrip()
        return out
    registers = '   '.join(f'R{i} {key}={value}' for i,(key,value) in enumerate(img.registers.items()))
    out.append('     '+ui.safe(registers or 'Registers not recorded.')+'\n', style=GRAPHITE)
    out.append('     STACK '+ui.safe(' → '.join(img.stack) or 'Not recorded.')+'\n', style=GRAPHITE)
    out.append('     NEXT  '+ui.safe(img.next_action or 'Not recorded.')+'\n', style=CYAN)
    if view.now-img.meta.created_at >= getattr(view,'stale_hours',24)*3600:
        out.append('     SAVED INSTRUCTION MAY BE STALE · C checks drift\n',style=RUST)
    out.rstrip()
    return out


def scheduler_line(view, row, selected):
    p = row['proc']
    wait = view.diagnostics.starved.get(p.alias)
    state = 'STARVED' if wait and wait.starved else row['state'].value
    symbol = '▶' if selected else '†' if row['state'] == State.ZOMBIE else '◇' if p.state==State.SLEEPING else '⋯' if state=='STARVED' else ' '
    code = tokens(view)[p.alias]
    out = Text(f'{symbol} {p.pid_str} {code}  {p.alias:<19} {state:<10}', style=CYAN if p.state==State.RUNNING else BONE if selected else GRAPHITE)
    out.append(f"  WSS≈{row['ctx'] or 0}ctx", style=GRAPHITE)
    cf = view.images.get(p.alias)
    if cf:
        out.append(f'  {ui.fmt_age(view.now-cf.image.meta.created_at)}', style=GRAPHITE)
    else: out.append('  unloaded', style=AMBER)
    if wait and wait.starved: out.append(f'  {wait.other_dispatches} others dispatched', style=AMBER)
    if row['state'] == State.ZOMBIE: out.append(f"  {row['inactive_days']:.0f}d idle / {row['residue']} residue", style=RUST)
    return out


def irq_text(irqs, phase=0, motion=False):
    pending = [i for i in irqs if not i.acknowledged]
    out = Text('IRQ  ', style=AMBER if pending else GRAPHITE)
    marks = ''.join('│' if motion and (j+phase)%4==0 else '┆' for j,_ in enumerate(pending[:24]))
    out.append(marks or '─', style=AMBER if pending else FAINT)
    out.append(f'  {len(pending)} pending', style=AMBER if pending else GRAPHITE)
    if pending: out.append('  '+ui.safe(pending[0].text)[:70], style=GRAPHITE)
    return out


def restoration_text(report, stage=4):
    """A staged presentation of the canonical report, not staged/fake I/O."""
    out = Text()
    def heading(t): out.append(t+'\n',style=GRAPHITE)
    def line(t,style=BONE): out.append(ui.safe(t)+'\n',style=style)
    if not report.available:
        heading('CONTEXT UNAVAILABLE')
        line('No process image was recovered. R in the kernel retries local extraction.')
        return out
    if 0<=stage<3:
        heading('PROGRAM COUNTER / restored')
        line('PC └ '+(report.last_execution_point or 'Not recorded.'),CYAN)
    if 1<=stage<3:
        heading('\nREGISTERS / restored')
        for i,(key,value) in enumerate(report.registers.items()): line(f'R{i} {key} ··· {value}')
        if not report.registers: line('Not recorded.',GRAPHITE)
    if stage==2:
        heading('\nSTACK / restored')
        for i,task in enumerate(report.stack): line(('└ ' if i==len(report.stack)-1 else '├ ')+task)
        if not report.stack: line('Not recorded.',GRAPHITE)
    if stage>=3:
        heading('\nYOU WERE HERE')
        line(report.what_happened or 'Work summary not recorded.')
        for item in report.completed:
            line('✓ '+item.text+(' [inferred]' if not item.explicit else ''))
            if item.source: line('  evidence: '+item.source,GRAPHITE)
        if not report.completed: line('No completed work recorded.',GRAPHITE)
        heading('\nYOU DECIDED')
        for d in report.decisions:
            line(d.text+(' [inferred]' if not d.explicit else ''))
            line('  why: '+(d.reason or 'Reason not recorded.'))
            if d.source: line('  evidence: '+d.source,GRAPHITE)
        if not report.decisions: line('Not recorded.',GRAPHITE)
        heading('\nYOU STOPPED AT')
        line(report.last_execution_point or 'Not recorded.')
        heading('\nWHILE YOU WERE GONE')
        changes=report.changes_since_snapshot
        line(f'{changes.new_commits} new commits · {len(changes.files)} changed files')
        for f in changes.files: line('  '+f,RUST)
        for c in changes.commit_subjects: line('  commit: '+c,RUST)
        if changes.history_rewritten: line('Saved commit unavailable; history needs review.',RUST)
        for stale in report.possible_drift:
            line('ASSUMPTION MAY BE STALE: '+stale.saved,RUST)
            for evidence in stale.evidence: line('  evidence: '+evidence,GRAPHITE)
        heading('\nSTILL OPEN')
        for item in report.unresolved: line('○ '+item)
        for item in report.blockers: line('BLOCKER '+item,RUST)
        if not report.unresolved and not report.blockers: line('Nothing recorded.',GRAPHITE)
        heading('\nWORKING FILES')
        line(' · '.join(report.relevant_files) or 'Not recorded.',GRAPHITE)
    if stage>=4:
        heading('\nNEXT EXECUTION')
        line(report.next_action or 'Review the saved evidence and record one immediate next step.',CYAN)
        if report.drift_level!='NONE': line('Review drift before executing a saved instruction.',RUST)
        line('\nFAULT RESOLVED',GRAPHITE)
    return out
