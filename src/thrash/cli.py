"""`thrash` command line. Orchestration and rendering only; logic lives in scheduler.py."""

from __future__ import annotations

import functools
import sys
import time
from pathlib import Path

import typer

from . import __version__, git_context as gc, ui
from .config import Config
from .ollama_client import ModelError
from .registry import RegistryError, State, slugify
from .scheduler import Kernel, KernelError, init_git_dir
from .privacy import ScanPolicy, absolute

app = typer.Typer(
    help="THRASH: a local human-process scheduler. It serializes and restores project context.",
    no_args_is_help=False, invoke_without_command=True, add_completion=False, pretty_exceptions_enable=False,
)


def get_kernel() -> Kernel:
    kernel = Kernel(Config.from_env())
    for proc in kernel.reg.all(include_terminated=True):
        ui.remember_project(proc)
    return kernel


def guard(fn):
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except (RegistryError, KernelError) as exc:
            ui.fail(str(exc))
            raise typer.Exit(1)
        except ModelError as exc:
            ui.model_unavailable(str(exc))
            raise typer.Exit(2)
    return wrapper


def _version(v: bool):
    if v:
        typer.echo(f"thrash {__version__}")
        raise typer.Exit()


@app.callback()
@guard
def main(ctx: typer.Context, version: bool = typer.Option(False, "--version", callback=_version, is_eager=True)):
    if ctx.invoked_subcommand is None:
        if _interactive():
            from .tui import KernelApp
            KernelApp(get_kernel()).run()
        else:
            typer.echo(ctx.get_help())


def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _snapshot_note(snap) -> None:
    if snap.image is not None and snap.error is None:
        ui.console.print(ui.image_counts(snap.image))
        if snap.reused:
            ui.console.print("[dim]working set unchanged: image reused[/dim]")
        else:
            ui.console.print(f"[dim]extracted by {ui.e(snap.image.meta.model)} in {snap.seconds:.1f}s[/dim]")
    elif snap.error:
        ui.model_unavailable(snap.error, snap.error_kind)


def admission(k, name, force=False, suspend=None, interrupt=False):
    """Return False if the request was captured instead of admitted."""
    from .diagnostics import diagnose
    from .interrupts import InterruptQueue
    d = diagnose(k)
    if interrupt:
        current = k.reg.running()
        item = InterruptQueue(k.cfg).capture(ui.safe("Consider project " + name), k.clock(),
                                            current.alias if current else None)
        k.tel.record("irq", k.clock(), irq_id=item.id, project=item.current)
        ui.console.print(f"Queued IRQ #{item.id}; no process created.")
        return False
    if suspend:
        k.suspend(suspend)
        d = diagnose(k)
    if not d.out_of_mind or force:
        return True
    ui.console.print("[bold red]OUT OF MIND[/bold red] — admission needs a deliberate choice.")
    ui.console.print(f"Active: {d.report.active} · pressure: {d.report.pressure:.0%} · "
                     f"switches: {d.report.switches} · pending IRQs: {d.pending_irqs}")
    ui.console.print("Suspension candidates: " + ui.e(", ".join(d.candidates) or "none"))
    ui.console.print("Use --suspend ALIAS, --interrupt, or --force. Nothing is killed automatically.")
    if _interactive():
        choice = typer.prompt("[S] suspend / [I] interrupt / [F] force / [C] cancel", default="C").lower()
        if choice == "f":
            return True
        if choice == "i":
            return admission(k, name, interrupt=True)
        if choice == "s":
            victim = typer.prompt("Suspend alias")
            return admission(k, name, suspend=victim)
    raise typer.Exit(1)


@app.command()
@guard
def init(
    alias: str = typer.Option(None, "--alias", "-a", help="Public-safe name shown everywhere."),
    path: Path = typer.Option(None, "--path", help="Project root (default: current directory)."),
    force: bool = typer.Option(False, "--force"),
    suspend_: str = typer.Option(None, "--suspend"),
    interrupt: bool = typer.Option(False, "--interrupt"),
):
    """Register the current project as a process and build its first process image."""
    k = get_kernel()
    start = absolute(path or Path.cwd())
    try:
        ScanPolicy(k.cfg.excluded_roots).require_root(start)
    except ValueError as exc:
        raise KernelError(str(exc)) from exc
    root = gc.toplevel(start, ScanPolicy(k.cfg.excluded_roots)) or start
    if not gc.is_git_repo(root):
        ui.console.print("[yellow]no Git repository detected: continuing with a plain file scan.[/yellow]")
    existing = k.reg.by_path(root)
    ui.banner()
    if existing:
        ui.console.print(f"\nAlready registered as {existing.alias} (PID {existing.pid_str}). Re-scanning.\n")
        proc = existing
        with ui.working("Building working set..."):
            snap = k.snapshot(proc, force=True)
    else:
        if alias is None:
            default = slugify(root.name)
            alias = typer.prompt("Public-safe alias (shown in all output)", default=default) if _interactive() else default
        if not admission(k, alias, force, suspend_, interrupt):
            return
        ui.console.print("\nRegistering process...\n")
        proc = k.reg.register(slugify(alias) if alias != alias.lower() else alias, root, k.clock())
        ui.remember_project(proc)
        k.tel.record("init", k.clock(), project=proc.alias)
        ui.console.print(f"PID       {proc.pid_str}\nNAME      {ui.e(proc.alias)}\nSTATE     {ui.state_cell(proc.state)}\n")
        with ui.working("Building working set..."):
            snap = k.snapshot(proc, force=True)
        marker = root / ".thrash"
        try:
            marker.mkdir(exist_ok=True)
            (marker / "project.json").write_text(f'{{"pid": {proc.pid}, "alias": "{proc.alias}"}}\n')
            (marker / ".gitignore").write_text("*\n")
        except OSError:
            pass
    _snapshot_note(snap)
    ui.console.print("\nProcess registered.")


@app.command()
@guard
def top(watch: bool = typer.Option(False, "--watch", "-w", help="Refresh every 2s (Ctrl-C to exit).")):
    """Kernel monitor: process table, pressure and thrashing state."""
    k = get_kernel()
    if not watch:
        rows, report, today = k.table()
        ui.render_top(rows, report, today)
        from .diagnostics import diagnose
        d = diagnose(k)
        ui.console.print(f"KERNEL MODE: {d.mode} · IRQ backlog: {d.pending_irqs}")
        for alias, wait in d.starved.items():
            if wait.starved:
                ui.console.print(f"STARVATION: {ui.e(alias)} READY for {wait.waiting_hours:.0f}h; "
                                 f"{wait.other_dispatches} other dispatches; {wait.execution_seconds:.0f}s execution.")
        for row in rows:
            if row["state"] == State.ZOMBIE:
                ui.console.print(f"ZOMBIE: {ui.e(row['proc'].alias)} · {row['inactive_days']:.0f} days idle · "
                                 f"{row['residue']} unresolved/blocker/TODO references in saved context.")
        if d.mode == "PANIC":
            ui.console.print("KERNEL PANIC: recovery advisory. Suspend a READY process, review interrupts, or continue deliberately.")
        return
    from rich.live import Live
    from rich.console import Group
    from rich.text import Text
    try:
        while True:
            with ui.console.capture() as cap:
                ui.render_top(*k.table())
            ui.console.clear()
            ui.console.print(Text.from_ansi(cap.get()))
            time.sleep(2)
    except KeyboardInterrupt:
        pass


@app.command()
@guard
def ps(all_: bool = typer.Option(False, "--all", "-a", help="Include TERMINATED.")):
    """Plain process list for scripts and screenshots."""
    k = get_kernel()
    rows, _, _ = k.table(include_terminated=all_)
    images = {}
    for r in rows:
        cf = k.load_context(r["proc"])
        images[r["proc"].pid] = cf.image if cf else None
    ui.render_ps(rows, images)


@app.command()
@guard
def status(project: str = typer.Argument(None, help="Defaults to the RUNNING process."),
           refresh: bool = typer.Option(False, "--refresh", help="Rebuild semantic context with local Gemma.")):
    """Detailed process image of the current (or named) process."""
    k = get_kernel()
    proc = k.reg.resolve(project, include_terminated=True) if project else k.current(Path.cwd())
    if proc is None:
        raise KernelError("no RUNNING process. use `thrash switch <project>` or name one.")
    row = next((r for r in k.table(include_terminated=True)[0] if r["proc"].pid == proc.pid), None)
    if refresh:
        with ui.working("Rebuilding working set..."):
            snap = k.snapshot(proc, force=True)
        _snapshot_note(snap)
    restored = k.restore(proc, reconstruct=False)
    ui.render_status(proc, restored.image, row["state"] if row else proc.state, restored.resume)


@app.command()
@guard
def switch(project: str = typer.Argument(..., help="Alias or PID.")):
    """Save the RUNNING process, restore PROJECT, report drift."""
    k = get_kernel()
    dest = k.reg.resolve(project)
    cur = k.reg.running()
    ui.console.print("[bold]CONTEXT SWITCH[/bold]\n")
    ui.console.print(f"FROM  {ui.e(cur.alias) if cur else '(idle)'}\nTO    {ui.e(dest.alias)}\n")
    with ui.working("Saving working set..." if cur else "Restoring working set..."):
        res = k.switch(project)
    if res.out is not None:
        _snapshot_note(res.out)
        ui.console.print(f"\n{ui.swap_line(res.swap_path)}")
    r = res.restore
    ui.render_page_fault(res.dest, r.image, r.age_s, r.drift, r.scanned, r.error, r.error_kind, resume=r.resume)
    if res.event.get("time_since_last_switch") is not None:
        ui.console.print(f"\n[dim]{ui.fmt_age(res.event['time_since_last_switch'])} since previous switch · "
                         f"restore {r.seconds:.2f}s[/dim]")


@app.command()
@guard
def suspend(project: str = typer.Argument(...)):
    """Snapshot PROJECT and move it to SLEEPING."""
    k = get_kernel()
    with ui.working("Serializing working set..."):
        proc, snap, swap = k.suspend(project)
    _snapshot_note(snap)
    ui.console.print(f"\nProcess {proc.pid_str} suspended.\nWorking set paged to swap.\n{ui.swap_line(swap)}")


@app.command()
@guard
def wake(project: str = typer.Argument(...)):
    """Move a SLEEPING process to READY and restore its context (does not switch to it)."""
    k = get_kernel()
    proc = k.reg.resolve(project)
    r = k.wake(project)
    ui.render_page_fault(proc, r.image, r.age_s, r.drift, r.scanned, r.error, r.error_kind, resume=r.resume)
    ui.console.print(f"\nProcess {proc.pid_str} is READY. Not switched.")


@app.command()
@guard
def fork(
    name: str = typer.Argument(..., help="Alias of the new process."),
    path: Path = typer.Option(None, "--path", help="Project root (default: current Git root)."),
    create: bool = typer.Option(False, "--create", help="Create ./NAME as a new Git repository."),
    force: bool = typer.Option(False, "--force", "-f", help="Fork despite resource pressure."),
    suspend_: str = typer.Option(None, "--suspend", "-s", help="Suspend this process first."),
    interrupt: bool = typer.Option(False, "--interrupt", help="Queue the idea instead of creating a process."),
):
    """Register a process, with deliberate admission under extreme pressure."""
    k = get_kernel()
    if not admission(k, name, force, suspend_, interrupt):
        return
    n, ratio = k.pressure()
    if n >= k.cfg.max_active and not force:
        ui.console.print("[bold yellow]fork(): resource pressure detected[/bold yellow]\n")
        ui.console.print(f"ACTIVE PROCESSES: {n}\nWORKING SET PRESSURE: {round(ratio * 100)}% ({'HIGH' if ratio >= 1 else 'ELEVATED'})\n")
        ui.console.print("Creating another active process may increase\ncontext recovery cost.\n")
        if _interactive():
            choice = typer.prompt("[S] suspend one  [F] fork anyway", default="F").strip().lower()
            if choice.startswith("s"):
                cand = next((p.alias for p in k.reg.all() if p.state == State.READY), None)
                victim = typer.prompt("suspend which", default=cand or "")
                k.suspend(victim)
                ui.console.print(f"suspended {ui.e(victim)}.\n")
        else:
            ui.console.print("[dim]non-interactive: forking anyway (--suspend NAME or --force to silence).[/dim]\n")
    if create:
        root = absolute(Path.cwd() / name)
        if not ScanPolicy(k.cfg.excluded_roots).allows(root):
            raise KernelError("excluded or unsafe project root")
        init_git_dir(root)
    else:
        start = absolute(path or Path.cwd())
        try:
            ScanPolicy(k.cfg.excluded_roots).require_root(start)
        except ValueError as exc:
            raise KernelError(str(exc)) from exc
        root = gc.toplevel(start, ScanPolicy(k.cfg.excluded_roots)) or start
    if taken := k.reg.by_path(root):
        raise KernelError(f"that directory is already process {taken.alias}. use --path or --create.")
    proc = k.reg.register(name, root, k.clock())
    k.tel.record("fork", k.clock(), project=proc.alias, active_before=n)
    ui.console.print(f"fork() -> PID {proc.pid_str}  {ui.e(proc.alias)}  {ui.state_cell(proc.state)}")
    with ui.working("Building working set..."):
        snap = k.snapshot(proc, force=True)
    _snapshot_note(snap)


@app.command()
@guard
def kill(
    project: str = typer.Argument(...),
    core: bool = typer.Option(None, "--core/--no-core", help="Write a core dump (asks if omitted)."),
    yes: bool = typer.Option(False, "--yes", "-y"),
):
    """Terminate a process in THRASH (the repository is never touched)."""
    k = get_kernel()
    ui.console.print(f"[bold red]SIGTERM[/bold red] -> {ui.e(project)}\n")
    with ui.working("Recovering final process state..."):
        plan = k.kill_plan(project)
    if plan.snapshot.error:
        ui.model_unavailable(plan.snapshot.error, plan.snapshot.error_kind)
    image = plan.snapshot.image
    if image:
        ui.console.print(f"PROCESS EXITING\n\nthings completed........ {len(image.completed)}\n"
                         f"things unfinished....... {len(image.unresolved) + len(image.blockers)}\n")
        ui.console.print(f"purpose: {ui.e(image.purpose or 'Not recorded.')}\n"
                         f"last known intention: {ui.e(image.next_action or image.program_counter.task)}\n"
                         f"resurrection worthwhile when: {ui.e(image.resurrection_hint or 'Not recorded.')}\n")
        for failure in image.failures:
            ui.console.print(f"failed approach: {ui.e(failure)}")
    ui.console.print(f"\nlast useful state:\n  {ui.e(plan.last_useful or 'unknown')}\n")
    ui.console.print("unfinished:")
    for u in plan.unfinished[:6] or ["(nothing recorded)"]:
        ui.console.print(f"  {ui.e(u)}")
    ui.console.print(f"\nreason inferred from repository:\n  {ui.e(plan.reason)}\n")
    if core is None:
        core = True if yes or not _interactive() else typer.confirm("Create core dump?", default=True)
    path = k.kill(plan, core)
    ui.console.print(f"core dumped:\ngraveyard/{ui.e(path.name)}" if path else "process terminated. no core dump.")


@app.command()
@guard
def resurrect(core: str = typer.Argument(..., help="Alias in the graveyard, or path to a .core file.")):
    """Re-register a terminated process from its core dump."""
    k = get_kernel()
    proc, dump, drift, age = k.resurrect(core)
    ui.remember_project(proc)
    ui.console.print("Restoring terminated process...\n")
    pc = dump.image.program_counter.task if dump.image else "unknown"
    ui.console.print(f"last known PC:\n  {ui.e(pc)}\n\nage:\n  {ui.fmt_age(age)}\n\nrepository drift:\n  {drift.level}")
    ui.render_drift(drift, "core dump")
    from .resume import build_resume_report
    ui.console.print(ui.resume_text(build_resume_report(proc.alias, dump.image, drift)))
    ui.console.print(f"\nProcess {proc.pid_str} ({ui.e(proc.alias)}) is READY.")


@app.command()
@guard
def irq(text: str = typer.Argument(...),
        route: bool = typer.Option(False, "--route", help="Ask local Gemma for advisory routing.")):
    """Capture an interrupt without leaving the current project."""
    from .interrupts import InterruptQueue
    k = get_kernel()
    queue = InterruptQueue(k.cfg)
    current = k.reg.running()
    if not text.strip():
        raise KernelError("Interrupt text cannot be empty")
    item = queue.capture(ui.safe(text), k.clock(), current.alias if current else None)
    k.tel.record("irq", k.clock(), irq_id=item.id, project=item.current)
    ui.console.print(f"INTERRUPT REQUEST #{item.id} — queued. Current execution preserved.")
    if route:
        item = queue.route(item.id, [p.alias for p in k.reg.all()])
        ui.console.print(f"Suggested route: {ui.e(item.route.kind)} {ui.e(item.route.project)}")
        ui.console.print(ui.e(item.route.reason))


@app.command()
@guard
def interrupts(ack: int = typer.Option(None, "--ack", help="Acknowledge an IRQ by ID."),
               all_: bool = typer.Option(False, "--all")):
    """Inspect pending interrupts; acknowledgment never creates a process."""
    from .interrupts import InterruptQueue
    queue = InterruptQueue(get_kernel().cfg)
    if ack is not None:
        try:
            queue.acknowledge(ack)
        except ValueError as exc:
            raise KernelError(str(exc)) from exc
    entries = [x for x in queue.read() if all_ or not x.acknowledged]
    for item in entries:
        ui.console.print(f"#{item.id} {'ACK' if item.acknowledged else 'PENDING'} "
                         f"{ui.e(item.text)} · {ui.e(item.route.kind)} {ui.e(item.route.project)}")
    if not entries:
        ui.console.print("No pending interrupts.")


@app.command()
def demo(script: bool = typer.Option(False, "--script", help="Print all nine synthetic scenes and exit.")):
    """Isolated synthetic kernel: N advances scenes in the TUI; Q cleans up."""
    from .demo import run_script, run_tui
    if script or not _interactive():
        run_script()
    else:
        run_tui()


if __name__ == "__main__":
    app()
