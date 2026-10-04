"""The kernel: process states, context switching, zombie and thrashing heuristics.

All numbers in here are deterministic. The model is only ever asked for text
(see extract.py); it never computes a timestamp, a count or a pressure value.
"""

from __future__ import annotations

import statistics
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from pydantic import BaseModel

from . import git_context as gc
from .config import Config
from .drift import DriftReport, compute_drift
from .extract import Extractor, ollama_extractor
from .ollama_client import ModelError, check_ready
from .privacy import IgnoreRules, ScanPolicy
from .process_image import ContextFile, Fingerprint, ImageError, ProcessImage
from .registry import Process, Registry, RegistryError, State
from .telemetry import Telemetry
from .resume import ResumeReport, build_resume_report


class KernelError(Exception):
    pass


# --------------------------------------------------------------------------
# pure heuristics (unit-tested without any I/O)
# --------------------------------------------------------------------------

@dataclass
class ThrashReport:
    state: str  # NOMINAL | STRAINED | THRASHING
    switches: int
    window_hours: float
    median_session_s: float | None
    sessions: int
    reconstructions: int
    active: int
    pressure: float  # active / max_active  (an estimate, defined in the README)
    fired: list[str] = field(default_factory=list)

    @property
    def pressure_label(self) -> str:
        return "HIGH" if self.pressure >= 1.0 else "ELEVATED" if self.pressure >= 0.75 else "LOW"


def evaluate_thrashing(events: list[dict], active: int, cfg: Config, now: float) -> ThrashReport:
    since = now - cfg.window_hours * 3600
    sw = [e for e in events if e.get("type") == "switch" and e["ts"] >= since]
    sessions = [e["session_seconds"] for e in events
                if e["ts"] >= since and e.get("session_seconds") is not None and e.get("ended_project")]
    median = statistics.median(sessions) if sessions else None
    recon = sum(1 for e in sw if e.get("reconstructed"))
    pressure = active / cfg.max_active if cfg.max_active else 0.0

    fired = []
    if len(sw) >= cfg.switch_limit:
        fired.append("switch rate")
    if len(sessions) >= 3 and median is not None and median < cfg.median_session_min * 60:
        fired.append("short sessions")
    if recon >= cfg.recon_limit:
        fired.append("context reconstruction")
    if active >= cfg.max_active:
        fired.append("working-set pressure")

    if len(fired) >= cfg.signals_required:
        state = "THRASHING"
    elif fired:
        state = "STRAINED"
    else:
        state = "NOMINAL"
    return ThrashReport(state, len(sw), cfg.window_hours, median, len(sessions), recon, active, pressure, fired)


def load_shares(events: list[dict], running: Process | None, now: float, hours: float = 24.0) -> dict[str, float]:
    """Share of recorded run-time per project over the last `hours`. Deterministic, from sessions."""
    since = now - hours * 3600
    secs: dict[str, float] = {}
    for e in events:
        if since <= e["ts"] <= now and e.get("ended_project") and e.get("session_seconds") is not None:
            start = e["ts"] - max(0.0, e["session_seconds"])
            duration = max(0.0, e["ts"] - max(since, start))
            secs[e["ended_project"]] = secs.get(e["ended_project"], 0.0) + duration
    if running and running.running_since is not None:
        secs[running.alias] = secs.get(running.alias, 0.0) + max(0.0, now - max(since, running.running_since))
    total = sum(secs.values())
    return {k: v / total for k, v in secs.items()} if total else {}


def derive_state(proc: Process, image: ProcessImage | None, last_activity: float | None,
                 cfg: Config, now: float) -> tuple[State, float | None, int]:
    """(effective state, inactive days, residue). ZOMBIE = idle long enough AND unresolved residue."""
    residue = 0
    if image is not None:
        residue = len(image.unresolved) + len(image.blockers) + image.meta.todo_count
    inactive = None if last_activity is None else max(0.0, (now - last_activity) / 86400)
    if proc.state in (State.READY, State.SLEEPING) and inactive is not None \
            and inactive >= cfg.zombie_days and residue > 0:
        return State.ZOMBIE, inactive, residue
    return proc.state, inactive, residue


# --------------------------------------------------------------------------
# results
# --------------------------------------------------------------------------

@dataclass
class SnapshotResult:
    image: ProcessImage | None
    reused: bool = False
    error: str | None = None
    error_kind: str | None = None  # "model" | "invalid" | "path"
    seconds: float = 0.0


@dataclass
class RestoreReport:
    proc: Process
    image: ProcessImage | None
    age_s: float | None = None
    drift: DriftReport = field(default_factory=DriftReport)
    reconstructed: bool = False
    scanned: bool = False
    error: str | None = None
    error_kind: str | None = None
    seconds: float = 0.0
    resume: ResumeReport | None = None


@dataclass
class SwitchResult:
    source: Process | None
    dest: Process
    out: SnapshotResult | None
    swap_path: Path | None
    restore: RestoreReport
    event: dict


@dataclass
class KillPlan:
    proc: Process
    snapshot: SnapshotResult
    last_useful: str
    unfinished: list[str]
    reason: str
    inactive_days: float | None


class CoreDump(BaseModel):
    version: int = 1
    alias: str
    pid: int
    path: str
    killed_at: float
    reason: str
    last_activity: float | None = None
    image: ProcessImage | None = None
    fingerprint: Fingerprint | None = None


# --------------------------------------------------------------------------
# the kernel
# --------------------------------------------------------------------------

class Kernel:
    def __init__(self, cfg: Config, extractor: Extractor | None = None,
                 clock: Callable[[], float] = time.time, registry: Registry | None = None):
        cfg.ensure_dirs()
        self.cfg = cfg
        self.reg = registry or Registry(cfg)
        self.tel = Telemetry(cfg.events_path)
        self._extractor = extractor
        self.clock = clock

    # --- storage helpers ---------------------------------------------------
    def image_path(self, p: Process) -> Path:
        return self.cfg.processes_dir / f"{p.pid_str}.json"

    def swap_path(self, p: Process) -> Path:
        return self.cfg.swap_dir / f"{p.alias}.ctx"

    def core_path(self, alias: str) -> Path:
        return self.cfg.graveyard_dir / f"{alias}.core"

    def rules(self, p: Process) -> IgnoreRules:
        return IgnoreRules.load(Path(p.path), self.cfg.global_ignore_path, ScanPolicy(self.cfg.excluded_roots))

    def load_context(self, p: Process) -> ContextFile | None:
        return ContextFile.read(self.image_path(p))

    def _extractor_ready(self) -> Extractor:
        if self._extractor is None:
            check_ready(self.cfg)  # raises a clear ModelError
            self._extractor = ollama_extractor(self.cfg)
        return self._extractor

    # --- snapshot / restore ------------------------------------------------
    def snapshot(self, proc: Process, force: bool = False) -> SnapshotResult:
        now = self.clock()
        root = Path(proc.path)
        if not ScanPolicy(self.cfg.excluded_roots).allows(root):
            return SnapshotResult(None, error="excluded or unsafe project root", error_kind="path")
        prev = self.load_context(proc)
        if not root.is_dir():
            return SnapshotResult(prev.image if prev else None, error=f"project path is gone: {proc.alias}", error_kind="path")
        ctx = gc.gather_context(root, self.cfg, self.rules(proc), now)
        if not ctx.fingerprint.files:
            return SnapshotResult(None, error="nothing to scan: no readable files", error_kind="empty")
        if prev and not force and prev.fingerprint.same_state_as(ctx.fingerprint):
            return SnapshotResult(prev.image, reused=True)
        t0 = time.monotonic()
        try:
            image = self._extractor_ready()(proc.alias, ctx, prev.image if prev else None, now)
        except ModelError as e:
            return SnapshotResult(prev.image if prev else None, error=str(e), error_kind="model")
        except ImageError as e:
            return SnapshotResult(prev.image if prev else None, error=str(e), error_kind="invalid")
        ContextFile(alias=proc.alias, saved_at=now, image=image, fingerprint=ctx.fingerprint).write(self.image_path(proc))
        return SnapshotResult(image, seconds=time.monotonic() - t0)

    def page_out(self, proc: Process) -> Path | None:
        """Copy the resident image to swap. Returns None if there is nothing to page."""
        cf = self.load_context(proc)
        if cf is None:
            return None
        cf.write(self.swap_path(proc))
        return self.swap_path(proc)

    def restore(self, proc: Process, reconstruct: bool = True) -> RestoreReport:
        t0 = time.monotonic()
        now = self.clock()
        if not ScanPolicy(self.cfg.excluded_roots).allows(Path(proc.path)):
            raise KernelError("excluded or unsafe project root")
        candidates = [self.load_context(proc), ContextFile.read(self.swap_path(proc))]
        # Resident wins ties (e.g. forced rescans with an unchanged test clock).
        cf = max((c for c in candidates if c is not None), key=lambda c: c.saved_at, default=None)
        scanned, err, kind = False, None, None
        if cf is None and reconstruct:
            snap = self.snapshot(proc, force=True)
            scanned, err, kind = True, snap.error, snap.error_kind
            cf = self.load_context(proc)
        if cf is None:
            return RestoreReport(proc, None, reconstructed=True, scanned=scanned, error=err,
                                 error_kind=kind, seconds=time.monotonic() - t0,
                                 resume=build_resume_report(proc.alias, None))
        age = max(0.0, now - cf.image.meta.created_at)
        drift = DriftReport()
        if Path(proc.path).is_dir() and not scanned:
            drift = compute_drift(Path(proc.path), cf.image, cf.fingerprint, self.rules(proc), now)
        recon = scanned or age >= self.cfg.stale_hours * 3600 or drift.level in ("MODERATE", "HIGH")
        return RestoreReport(proc, cf.image, age, drift, recon, scanned, err, kind, time.monotonic() - t0,
                             build_resume_report(proc.alias, cf.image, drift))

    # --- lifecycle ---------------------------------------------------------
    def register_project(self, path: Path, alias: str, event: str = "init") -> tuple[Process, SnapshotResult]:
        ScanPolicy(self.cfg.excluded_roots).require_root(path)
        now = self.clock()
        proc = self.reg.register(alias, path, now)
        self.tel.record(event, now, project=proc.alias)
        return proc, self.snapshot(proc, force=True)

    def _end_session(self, proc: Process, now: float) -> float | None:
        return (now - proc.running_since) if proc.state == State.RUNNING and proc.running_since else None

    def switch(self, ref: str) -> SwitchResult:
        dest = self.reg.resolve(ref)
        cur = self.reg.running()
        if cur and cur.pid == dest.pid:
            raise KernelError(f"{dest.alias} is already RUNNING")
        now = self.clock()
        out = swap = None
        session = None
        if cur:
            out = self.snapshot(cur)
            swap = self.page_out(cur)
            session = self._end_session(cur, now)
            self.reg.set_state(cur, State.READY, now)
        prev_switches = self.tel.switches()
        since_last = (now - prev_switches[-1]["ts"]) if prev_switches else None
        report = self.restore(dest)
        self.reg.set_running(dest, now)
        event = self.tel.record(
            "switch", now,
            from_project=cur.alias if cur else None, to_project=dest.alias,
            time_since_last_switch=since_last,
            snapshot_age=report.age_s, restore_duration=round(report.seconds, 3),
            ended_project=cur.alias if cur else None, session_seconds=session,
            reconstructed=report.reconstructed, drift=report.drift.level,
            dest_last_commit=gc.last_commit_ts(Path(dest.path)) if Path(dest.path).is_dir() else None,
        )
        return SwitchResult(cur, dest, out, swap, report, event)

    def suspend(self, ref: str) -> tuple[Process, SnapshotResult, Path | None]:
        proc = self.reg.resolve(ref)
        if proc.state == State.SLEEPING:
            raise KernelError(f"{proc.alias} is already SLEEPING")
        now = self.clock()
        snap = self.snapshot(proc)
        swap = self.page_out(proc)
        session = self._end_session(proc, now)
        self.reg.set_state(proc, State.SLEEPING, now)
        self.tel.record("suspend", now, project=proc.alias, ended_project=proc.alias if session is not None else None,
                        session_seconds=session, reused=snap.reused)
        return proc, snap, swap

    def wake(self, ref: str) -> RestoreReport:
        proc = self.reg.resolve(ref)
        if proc.state != State.SLEEPING:
            raise KernelError(f"{proc.alias} is {proc.state.value}, not SLEEPING")
        now = self.clock()
        report = self.restore(proc)
        self.reg.set_state(proc, State.READY, now)
        self.tel.record("wake", now, project=proc.alias, snapshot_age=report.age_s,
                        restore_duration=round(report.seconds, 3), reconstructed=report.reconstructed)
        return report

    # --- pressure ----------------------------------------------------------
    def active_count(self) -> int:
        return sum(1 for p in self.reg.all() if p.state in (State.RUNNING, State.READY))

    def pressure(self) -> tuple[int, float]:
        n = self.active_count()
        return n, (n / self.cfg.max_active if self.cfg.max_active else 0.0)

    # --- termination -------------------------------------------------------
    def kill_plan(self, ref: str) -> KillPlan:
        proc = self.reg.resolve(ref)
        snap = self.snapshot(proc)
        img = snap.image
        root = Path(proc.path)
        act = gc.repo_last_activity(root, self.rules(proc)) if root.is_dir() else None
        days = None if act is None else max(0.0, (self.clock() - act) / 86400)
        if days is not None and days >= 1:
            reason = f"no repository activity for {int(days)} days"
        elif days is not None:
            reason = "repository active within the last day; closed deliberately"
        else:
            reason = "no repository evidence available"
        last_useful = (img.last_useful_state or img.program_counter.task) if img else ""
        unfinished = list(img.unresolved + img.blockers) if img else []
        return KillPlan(proc, snap, last_useful, unfinished, reason, days)

    def kill(self, plan: KillPlan, core: bool) -> Path | None:
        proc, now = plan.proc, self.clock()
        session = self._end_session(proc, now)
        path = None
        if core:
            cf = self.load_context(proc)
            dump = CoreDump(
                alias=proc.alias, pid=proc.pid, path=proc.path, killed_at=now, reason=plan.reason,
                last_activity=None if plan.inactive_days is None else now - plan.inactive_days * 86400,
                image=cf.image if cf else plan.snapshot.image, fingerprint=cf.fingerprint if cf else None,
            )
            path = self.core_path(proc.alias)
            self.cfg.graveyard_dir.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".core.tmp")
            tmp.write_text(dump.model_dump_json(indent=2), encoding="utf-8")
            tmp.replace(path)
        self.reg.set_state(proc, State.TERMINATED, now)
        self.tel.record("kill", now, project=proc.alias, core=bool(path), ended_project=proc.alias if session is not None else None,
                        session_seconds=session)
        return path

    def resurrect(self, ref: str) -> tuple[Process, CoreDump, DriftReport, float | None]:
        p = Path(ref).expanduser()
        core_file = p if p.is_file() else self.core_path(ref.strip().lower())
        if not core_file.is_file():
            raise KernelError(f"no core dump found for {ref!r} (looked in {self.cfg.graveyard_dir})")
        try:
            dump = CoreDump.model_validate_json(core_file.read_text(encoding="utf-8"))
        except ValueError as e:
            raise KernelError(f"core dump unreadable: {core_file.name}") from e
        if not ScanPolicy(self.cfg.excluded_roots).allows(Path(dump.path)):
            raise KernelError("excluded or unsafe project root")
        if not Path(dump.path).is_dir():
            raise KernelError("repository path in the core dump no longer exists")
        now = self.clock()
        existing = next((x for x in self.reg.all(include_terminated=True) if x.alias == dump.alias), None)
        if existing and existing.state != State.TERMINATED:
            raise KernelError(f"{dump.alias} is already alive ({existing.state.value})")
        if existing:
            self.reg.revive(existing, dump.path)
            proc = existing
        else:
            proc = self.reg.register(dump.alias, dump.path, now)
        drift = DriftReport()
        if dump.image and dump.fingerprint:
            ContextFile(alias=proc.alias, saved_at=now, image=dump.image, fingerprint=dump.fingerprint).write(self.image_path(proc))
            ContextFile(alias=proc.alias, saved_at=now, image=dump.image, fingerprint=dump.fingerprint).write(self.swap_path(proc))
            drift = compute_drift(Path(proc.path), dump.image, dump.fingerprint, self.rules(proc), now)
        age = (now - dump.image.meta.created_at) if dump.image else None
        self.tel.record("resurrect", now, project=proc.alias, snapshot_age=age, drift=drift.level)
        return proc, dump, drift, age

    # --- reporting ---------------------------------------------------------
    def current(self, cwd: Path | None = None) -> Process | None:
        if run := self.reg.running():
            return run
        if cwd and (top := gc.toplevel(cwd, ScanPolicy(self.cfg.excluded_roots))):
            return self.reg.by_path(top)
        return None

    def table(self, include_terminated: bool = False) -> tuple[list[dict], ThrashReport, int]:
        now = self.clock()
        events = self.tel.read()
        procs = self.reg.all(include_terminated)
        shares = load_shares(events, self.reg.running(), now)
        rows = []
        for p in procs:
            if not ScanPolicy(self.cfg.excluded_roots).allows(Path(p.path)):
                continue
            cf = self.load_context(p)
            img = cf.image if cf else None
            root = Path(p.path)
            act = gc.repo_last_activity(root, self.rules(p)) if root.is_dir() and p.state != State.TERMINATED else None
            state, inactive, residue = derive_state(p, img, act, self.cfg, now)
            rows.append({
                "proc": p, "state": state, "load": shares.get(p.alias, 0.0),
                "ctx": img.meta.ctx_units if img else None, "inactive_days": inactive,
                "residue": residue, "has_image": img is not None,
            })
        report = evaluate_thrashing(events, self.active_count(), self.cfg, now)
        today = datetime.fromtimestamp(now).date()
        switches_today = sum(1 for e in events if e.get("type") == "switch"
                             and datetime.fromtimestamp(e["ts"]).date() == today)
        return rows, report, switches_today


def init_git_dir(path: Path) -> None:
    """Used by `fork --create`."""
    path.mkdir(parents=True, exist_ok=True)
    if not gc.is_git_repo(path):
        subprocess.run(["git", "-C", str(path), "init", "-q", "-b", "main"], check=False)


__all__ = ["Kernel", "KernelError", "RegistryError", "evaluate_thrashing", "load_shares", "derive_state",
           "ThrashReport", "CoreDump"]
