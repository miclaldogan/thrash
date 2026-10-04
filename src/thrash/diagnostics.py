"""Explainable scheduler signals, shared by the CLI and full-screen monitor."""
from dataclasses import dataclass, field
from .registry import State
from .scheduler import evaluate_thrashing
from .interrupts import InterruptQueue


@dataclass
class Starvation:
    starved: bool = False
    waiting_hours: float = 0
    other_dispatches: int = 0
    execution_seconds: float = 0


def starvation(proc, events, cfg, now):
    if proc.state != State.READY:
        return Starvation()
    since = proc.ready_since if proc.ready_since is not None else proc.registered_at
    recent = [e for e in events if since <= e['ts'] <= now]
    others = sum(e.get('type') == 'switch' and e.get('to_project') != proc.alias for e in recent)
    runtime = sum(max(0, min(e['ts'] - since, e.get('session_seconds') or 0))
                  for e in recent if e.get('ended_project') == proc.alias)
    hours = max(0, now-since)/3600
    return Starvation(hours >= cfg.starvation_hours and others >= cfg.starvation_switches
                      and runtime < cfg.starvation_execution_min*60, hours, others, runtime)


@dataclass
class Diagnostics:
    mode: str
    report: object
    pending_irqs: int
    stale_images: int
    starved: dict = field(default_factory=dict)
    candidates: list[str] = field(default_factory=list)
    out_of_mind: bool = False
    reasons: list[str] = field(default_factory=list)


def diagnose(kernel):
    cfg, now = kernel.cfg, kernel.clock()
    procs, events = kernel.reg.all(), kernel.tel.read()
    report = evaluate_thrashing(events, kernel.active_count(), cfg, now)
    pending = sum(not i.acknowledged for i in InterruptQueue(cfg).read())
    stale = 0
    for p in procs:
        if p.state not in (State.READY, State.RUNNING):
            continue
        cf = kernel.load_context(p)
        stale += cf is None or now-cf.image.meta.created_at >= cfg.stale_hours*3600
    panic = (report.active >= cfg.panic_active and report.switches >= cfg.panic_switches
             and pending >= cfg.panic_irqs and stale >= cfg.panic_stale)
    mode = 'PANIC' if panic else {'NOMINAL':'NORMAL', 'STRAINED':'PRESSURE', 'THRASHING':'THRASHING'}[report.state]
    reasons = list(report.fired)
    if panic:
        reasons += [f'{pending} pending interrupts', f'{stale} stale or missing active images']
    candidates = sorted((p for p in procs if p.state == State.READY),
                        key=lambda p: p.ready_since if p.ready_since is not None else p.registered_at)
    return Diagnostics(mode, report, pending, stale,
                       {p.alias: starvation(p, events, cfg, now) for p in procs},
                       [p.alias for p in candidates], report.active >= cfg.oom_active, reasons)
