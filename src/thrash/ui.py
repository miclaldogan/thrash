"""Terminal rendering. Terse, technical, slightly ominous. No emoji."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from rich.console import Console
from rich.markup import escape as e
from rich.table import Table

from . import KERNEL_VERSION
from .config import tilde
from .drift import DriftReport
from .process_image import ProcessImage
from .registry import Process, State

console = Console(highlight=False)
err_console = Console(stderr=True, highlight=False)

STATE_STYLE = {
    State.RUNNING: "bold green", State.READY: "cyan", State.SLEEPING: "blue",
    State.ZOMBIE: "bold red", State.TERMINATED: "dim",
}


def bar(pct: int = 100, width: int = 20) -> str:
    full = round(width * pct / 100)
    return "█" * full + "░" * (width - full) + f" {pct}%"


def fmt_age(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    s = int(seconds)
    if s < 90:
        return f"{s} sec"
    if s < 5400:
        return f"{round(s / 60)} min"
    if s < 4 * 86400:
        return f"{round(s / 3600)} hours"
    return f"{round(s / 86400)} days"


def banner(sub: str | None = None) -> None:
    console.print(f"[bold]THRASH HUMAN KERNEL {KERNEL_VERSION}[/bold]" + (f"\n{sub}" if sub else ""))


def fail(msg: str) -> None:
    err_console.print(f"[bold red]error:[/bold red] {e(msg)}")


@contextmanager
def working(label: str):
    """Spinner while real work runs; a full bar only once it has actually finished."""
    with console.status(label, spinner="line"):
        yield
    console.print(f"{label}\n[green]{bar(100)}[/green]")


def state_cell(s: State) -> str:
    return f"[{STATE_STYLE[s]}]{s.value}[/]"


# --- model availability ----------------------------------------------------
def model_unavailable(detail: str, kind: str | None = None) -> None:
    if kind == "invalid":
        console.print(f"\n[bold yellow]MODEL OUTPUT REJECTED[/bold yellow]\n\n{e(detail)}\n\n"
                      "Nothing malformed was stored. Previous image (if any) kept.")
    elif kind == "empty":
        console.print(f"\n[yellow]EXTRACTION SKIPPED[/yellow]  {e(detail)}")
    else:
        console.print(f"\n[bold yellow]LOCAL MODEL UNAVAILABLE[/bold yellow]\n\n{e(detail)}.\n\n"
                      "Process telemetry is still available.\nContext extraction is paused.")


# --- image counters --------------------------------------------------------
def _n(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def image_counts(img: ProcessImage) -> str:
    return "\n".join([
        _n(len(img.decisions), "decision"), _n(len(img.open_handles), "active file"),
        _n(len(img.unresolved), "unresolved question"), _n(len(img.blockers), "blocker"),
    ])


# --- status ------------------------------------------------------------------
def dotted(key: str, val: str, width: int = 24) -> str:
    return f"{e(key)} {'.' * max(2, width - len(key))} {e(val)}"


def render_status(proc: Process, img: ProcessImage | None, state: State) -> None:
    console.print(f"[bold]PID {proc.pid_str}  {e(proc.alias)}  {state_cell(state)}[/bold]\n")
    if img is None:
        console.print("no process image. run [bold]thrash switch[/bold] / [bold]thrash init[/bold] with the local model up.")
        return
    conf = img.program_counter.confidence
    console.print("[bold]PROGRAM COUNTER[/bold]")
    console.print(f"{e(img.program_counter.task)}  [dim](model-reported confidence {conf:.2f})[/dim]\n")
    if img.registers:
        console.print("[bold]REGISTERS[/bold]")
        for k, v in img.registers.items():
            console.print(dotted(k, v))
        console.print()
    if img.stack:
        console.print("[bold]STACK[/bold]")
        for i, t in enumerate(img.stack, 1):
            console.print(f"{i}. {e(t)}")
        console.print()
    if img.open_handles:
        console.print("[bold]OPEN HANDLES[/bold]")
        for h in img.open_handles:
            console.print(e(h))
        console.print()
    if img.decisions:
        console.print("[bold]DECISIONS[/bold]")
        for d in img.decisions:
            tag = "" if d.explicit else " [dim](inferred)[/dim]"
            src = f"  [dim]<- {e(d.source)}[/dim]" if d.source else ""
            console.print(f"- {e(d.text)}{tag}{src}")
        console.print()
    for title, items in (("UNRESOLVED", img.unresolved), ("BLOCKERS", img.blockers)):
        if items:
            console.print(f"[bold]{title}[/bold]")
            for t in items:
                console.print(f"- {e(t)}")
            console.print()
    console.print("[bold]NEXT ACTION[/bold]")
    console.print(e(img.next_action or img.program_counter.task))
    m = img.meta
    console.print(f"\n[dim]image: model {e(m.model)} · ~{m.ctx_units}u (estimate) · "
                  f"extract {m.extract_seconds}s · {m.dropped_paths} invalid path(s) rejected · "
                  f"{m.redactions} redaction(s)[/dim]")


# --- page fault / restore ---------------------------------------------------
def render_page_fault(proc: Process, img: ProcessImage | None, age_s: float | None, drift: DriftReport,
                      scanned: bool, error: str | None, error_kind: str | None, since_word: str = "suspend") -> None:
    console.print("\n[bold magenta]PAGE FAULT[/bold magenta]\n")
    console.print(f"Restoring process {proc.pid_str}...\n")
    if img is None:
        console.print("no saved image for this process.")
        if error:
            model_unavailable(error, error_kind)
        return
    conf = img.program_counter.confidence
    console.print(f"PC  -> {e(img.program_counter.task)}  [dim](conf {conf:.2f})[/dim]")
    for i, (k, v) in enumerate(list(img.registers.items())[:6]):
        console.print(f"R{i}  -> {e(k)}: {e(v)}")
    console.print("\n[bold]STACK RESTORED[/bold]" + (f"  [dim]({len(img.stack)} frames)[/dim]" if img.stack else ""))
    if scanned:
        console.print("\nno prior page: context reconstructed from repository.")
        if error:
            model_unavailable(error, error_kind)
    else:
        console.print(f"\nProcess image is {fmt_age(age_s)} old.")
        render_drift(drift, since_word)
    console.print(f"\n[bold]NEXT INSTRUCTION:[/bold]\n{e(img.next_action or img.program_counter.task)}")


def render_drift(drift: DriftReport, since_word: str = "suspend") -> None:
    if drift.level == "NONE":
        console.print(f"\nNo drift since {since_word}.")
        return
    style = {"LOW": "yellow", "MODERATE": "yellow", "HIGH": "bold red"}[drift.level]
    console.print(f"\n[{style}]POSSIBLE DRIFT ({drift.level})[/{style}]  since {since_word}:")
    if drift.history_rewritten:
        console.print("! saved commit no longer in history")
    if drift.new_commits:
        console.print(f"+ {drift.new_commits} new commit{'s' if drift.new_commits != 1 else ''}")
        for s in drift.commit_subjects[:3]:
            console.print(f"    [dim]{e(s)}[/dim]")
    if drift.changed_files:
        n = len(drift.changed_files)
        console.print(f"+ {n} relevant file{'s' if n != 1 else ''} changed")
        for f in drift.changed_files[:5]:
            console.print(f"    [dim]{e(f)}[/dim]")
        if n > 5:
            console.print(f"    [dim]... and {n - 5} more[/dim]")
    for st in drift.stale:
        console.print(f"[yellow]~ ASSUMPTION MAY BE STALE:[/yellow] {e(st.saved)}")
        for ev in st.evidence[:3]:
            console.print(f"    [dim]evidence: {e(ev)}[/dim]")


# --- tables -----------------------------------------------------------------
def render_top(rows: list[dict], report, switches_today: int) -> None:
    banner("1 HUMAN CORE\n")
    t = Table(box=None, pad_edge=False, show_edge=False)
    for col, just in (("PID", "left"), ("PROCESS", "left"), ("STATE", "left"), ("LOAD", "right"), ("CTX~", "right")):
        t.add_column(col, justify=just, style="bold" if col == "PID" else None, header_style="bold")
    order = {State.RUNNING: 0, State.READY: 1, State.ZOMBIE: 2, State.SLEEPING: 3, State.TERMINATED: 4}
    for r in sorted(rows, key=lambda r: (order[r["state"]], r["proc"].pid)):
        ctx = f"{r['ctx']}u" if r["ctx"] is not None else "-"
        t.add_row(r["proc"].pid_str, e(r["proc"].alias), state_cell(r["state"]), f"{round(r['load'] * 100)}%", ctx)
    console.print(t)
    console.print(f"\ncontext switches today: {switches_today}")
    console.print(f"active processes:       {report.active}")
    console.print(f"working-set pressure:   {round(report.pressure * 100)}% [dim](active/limit, est.)[/dim]  {report.pressure_label}")
    style = {"THRASHING": "bold red", "STRAINED": "yellow", "NOMINAL": "green"}[report.state]
    console.print(f"\nSTATE: [{style}]{report.state}[/]")
    if report.state == "THRASHING":
        med = fmt_age(report.median_session_s) if report.median_session_s is not None else "n/a"
        console.print(f"\n[bold red]THRASHING DETECTED[/bold red]\n")
        console.print(f"{_n(report.switches, 'project switch', 'project switches')} in {report.window_hours:g} hours")
        console.print(f"median uninterrupted session: {med}")
        console.print(f"{_n(report.reconstructions, 'switch', 'switches')} required stale-context reconstruction")
        console.print(f"{_n(report.active, 'active working set')}")
        console.print(f"signals: {', '.join(report.fired)}")
        console.print("\nThe system is spending too much time restoring context.")
    elif report.state == "STRAINED":
        console.print(f"[dim]signal: {', '.join(report.fired)}[/dim]")
    console.print("\n[dim]LOAD = share of recorded run-time, last 24h · CTX~ = estimated tokens in saved image[/dim]")


def render_ps(rows: list[dict], images: dict[int, ProcessImage | None]) -> None:
    t = Table(box=None, pad_edge=False, show_edge=False)
    for col in ("PID", "NAME", "STATE", "PC"):
        t.add_column(col, header_style="bold")
    order = {State.RUNNING: 0, State.READY: 1, State.ZOMBIE: 2, State.SLEEPING: 3, State.TERMINATED: 4}
    for r in sorted(rows, key=lambda r: (order[r["state"]], r["proc"].pid)):
        img = images.get(r["proc"].pid)
        pc = img.program_counter.task if img else "-"
        t.add_row(r["proc"].pid_str, e(r["proc"].alias), state_cell(r["state"]), e(pc[:48]))
    console.print(t)


def swap_line(path: Path | None) -> str:
    return f"paged -> {tilde(path)}" if path else "nothing to page (no image)"
