"""Terminal rendering. Terse, technical, slightly ominous. No emoji."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import re

from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.text import Text

from . import KERNEL_VERSION
from .drift import DriftReport
from .process_image import ProcessImage
from .registry import Process, State
from .privacy import public_text
from .resume import ResumeReport, build_resume_report


_project_names: dict[str, str] = {}


def remember_project(proc: Process) -> None:
    name = Path(proc.path).name
    if name and name != proc.alias:
        _project_names[name] = proc.alias


def safe(value: str) -> str:
    value = public_text(value)
    for name, alias in _project_names.items():
        value = re.sub(r"(?<![\w.-])" + re.escape(name) + r"(?![\w.-])", alias, value)
    return value


def e(value: str) -> str:
    return escape(safe(value))

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


def resume_text(report: ResumeReport) -> Text:
    """One literal-text renderer shared by the CLI and TUI (never parse repository markup)."""
    out = Text()

    def heading(label: str) -> None:
        out.append(label + "\n", style="bold cyan")

    def line(value: str = "", style: str | None = None) -> None:
        out.append(safe(value) + "\n", style=style)

    def items(label: str, values: list[str]) -> None:
        heading(label)
        for value in values or ["Not recorded."]:
            line("  " + value)
        line()

    if not report.available:
        heading("CONTEXT UNAVAILABLE")
        line("No saved process image. Start local Ollama and rescan this project with thrash init.")
        return out
    heading("LAST KNOWN EXECUTION STATE")
    line(f"{report.project} · confidence {report.confidence:.2f} (model-reported)", "dim")
    line()
    items("WHAT YOU DID", [report.what_happened] if report.what_happened else [])
    heading("WHAT YOU FINISHED")
    if not report.completed:
        line("  No completed work recorded; pending work is not assumed finished.")
    for item in report.completed:
        line(f"  - {item.text}" + (" (inferred)" if not item.explicit else ""))
        if item.source:
            line(f"    evidence: {item.source}", "dim")
    line()
    heading("WHAT YOU DECIDED AND WHY")
    if not report.decisions:
        line("  No decisions recorded.")
    for decision in report.decisions:
        line(f"  - {decision.text}" + (" (inferred)" if not decision.explicit else ""))
        line(f"    why: {decision.reason or 'Reason not recorded.'}")
        if decision.source:
            line(f"    evidence: {decision.source}", "dim")
    line()
    items("WHERE YOU LEFT OFF / PROGRAM COUNTER", [report.last_execution_point] if report.last_execution_point else [])
    items("REGISTERS", [f"R{i} = {key}: {value}" for i, (key, value) in enumerate(report.registers.items())])
    items("STACK RESTORED", [f"{i}. {task}" for i, task in enumerate(report.stack, 1)])
    items("RELEVANT FILES / OPEN HANDLES", report.relevant_files)
    heading("WHAT CHANGED SINCE THEN")
    changes = report.changes_since_snapshot
    if changes.history_rewritten:
        line("  Saved commit no longer available; history needs review.", "yellow")
    line(f"  {changes.new_commits} new commits · {len(changes.files)} changed files")
    for subject in changes.commit_subjects:
        line(f"  commit: {subject}")
    for path in changes.files:
        line(f"  file: {path}")
    if report.drift_level != "NONE":
        line(f"  POSSIBLE DRIFT ({report.drift_level})", "yellow")
    for stale in report.possible_drift:
        line(f"  ASSUMPTION MAY BE STALE: {stale.saved}", "yellow")
        for evidence in stale.evidence:
            line(f"    evidence: {evidence}", "dim")
    line()
    items("WHAT REMAINS UNRESOLVED", report.unresolved)
    items("BLOCKERS", report.blockers)
    items("EVIDENCE", report.evidence)
    if report.purpose:
        items("PURPOSE", [report.purpose])
    if report.failures:
        items("FAILED APPROACHES", report.failures)
    if report.resurrection_hint:
        items("RETURN WHEN", [report.resurrection_hint])
    heading("NEXT EXECUTION")
    line("NEXT INSTRUCTION:", "dim")
    line(report.next_action or "Review the saved evidence and record one immediate next step.", "bold")
    if report.legacy_image:
        line("Older image: completed work and reasons may be absent. Use status --refresh to enrich it.", "dim")
    if report.drift_level != "NONE":
        line("Check the drift above before executing a stale instruction.", "yellow")
    return out


def render_status(proc: Process, img: ProcessImage | None, state: State,
                  resume: ResumeReport | None = None) -> None:
    remember_project(proc)
    console.print(f"[bold]PID {proc.pid_str}  {e(proc.alias)}  {state_cell(state)}[/bold]\n")
    console.print(resume_text(resume or build_resume_report(proc.alias, img)))
    if img:
        m = img.meta
        console.print(f"\n[dim]image: model {e(m.model)} · ~{m.ctx_units}u (estimate) · "
                      f"extract {m.extract_seconds}s · {m.dropped_paths} invalid path(s) rejected · "
                      f"{m.redactions} redaction(s)[/dim]")


def render_page_fault(proc: Process, img: ProcessImage | None, age_s: float | None, drift: DriftReport,
                      scanned: bool, error: str | None, error_kind: str | None, since_word: str = "suspend",
                      resume: ResumeReport | None = None) -> None:
    remember_project(proc)
    console.print("\n[bold magenta]PAGE FAULT[/bold magenta]\n")
    console.print(f"Restoring process {proc.pid_str}...\n")
    if error:
        model_unavailable(error, error_kind)
    if img:
        console.print(f"locating process image........ found\n"
                      f"loading decisions............. {len(img.decisions)}\n"
                      f"loading unresolved state...... {len(img.unresolved)}\n"
                      f"loading working files......... {len(img.open_handles)}")
        console.print("\nContext reconstructed from repository." if scanned else
                      f"\nProcess image is {fmt_age(age_s)} old.")
        console.print()
    console.print(resume_text(resume or build_resume_report(proc.alias, img, drift)))
    if img:
        console.print("\n[bold green]FAULT RESOLVED[/bold green] · saved working set restored")


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
    for row in rows:
        remember_project(row["proc"])
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
    for row in rows:
        remember_project(row["proc"])
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
    return f"paged -> swap/{e(path.name)}" if path else "nothing to page (no image)"
