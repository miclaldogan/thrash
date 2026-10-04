import pytest

from conftest import commit
from thrash.registry import State
from thrash.scheduler import KernelError, derive_state
from thrash.ollama_client import OllamaUnavailable
from thrash.process_image import ContextFile


def test_switch_moves_running_and_records_event(kernel3, clock):
    k = kernel3
    r1 = k.switch("alpha")
    assert r1.source is None and r1.dest.state == State.RUNNING
    clock.advance(600)
    r2 = k.switch("beta")
    assert r2.source.alias == "alpha" and r2.source.state == State.READY
    assert [p.alias for p in k.reg.all() if p.state == State.RUNNING] == ["beta"]
    ev = r2.event
    assert ev["from_project"] == "alpha" and ev["to_project"] == "beta"
    assert ev["session_seconds"] == 600 and ev["time_since_last_switch"] == 600
    assert {"snapshot_age", "restore_duration", "reconstructed"} <= ev.keys()
    assert r2.swap_path.exists() and r2.swap_path.name == "alpha.ctx"


def test_switch_to_running_is_error(kernel3):
    kernel3.switch("alpha")
    with pytest.raises(KernelError):
        kernel3.switch("alpha")


def test_suspend_wake(kernel3, clock):
    k = kernel3
    k.switch("alpha")
    clock.advance(100)
    proc, snap, swap = k.suspend("alpha")
    assert proc.state == State.SLEEPING and swap.exists()
    assert k.reg.running() is None
    with pytest.raises(KernelError):
        k.suspend("alpha")
    rep = k.wake("alpha")
    assert proc.state == State.READY and rep.image is not None
    with pytest.raises(KernelError):
        k.wake("alpha")  # not sleeping any more


def test_restore_reports_drift(kernel3, repos, clock):
    k = kernel3
    k.switch("alpha")
    k.switch("beta")  # alpha paged out
    clock.advance(3600 * 71)
    commit(repos["alpha"], "engine: scaffold integration", {"engine/core.py": "x = 1\n"})
    res = k.switch("alpha")
    d = res.restore.drift
    assert d.new_commits == 1 and "engine/core.py" in d.changed_files
    assert res.restore.age_s >= 71 * 3600
    assert res.restore.reconstructed  # image older than stale_hours
    assert any("engine" in s.saved for s in d.stale)  # register 'engine: undecided' may be stale


def test_unchanged_repo_reuses_image(kernel3):
    k = kernel3
    p = k.reg.resolve("alpha")
    snap = k.snapshot(p)
    assert snap.reused


def test_kill_core_resurrect(kernel3, repos, clock):
    k = kernel3
    plan = k.kill_plan("gamma")
    path = k.kill(plan, core=True)
    assert path.exists() and k.reg.resolve("gamma", include_terminated=True).state == State.TERMINATED
    assert repos["gamma"].exists()  # repository untouched
    from thrash.registry import RegistryError
    with pytest.raises(RegistryError):
        k.reg.resolve("gamma")
    clock.advance(86400 * 43)
    proc, dump, drift, age = k.resurrect("gamma")
    assert proc.state == State.READY and proc.pid == 3 and age >= 43 * 86400
    assert drift.level == "NONE"


def test_resurrect_missing_core(kernel3):
    with pytest.raises(KernelError):
        kernel3.resurrect("nope")


def test_kill_running_ends_session(kernel3, clock):
    k = kernel3
    k.switch("alpha")
    clock.advance(50)
    k.kill(k.kill_plan("alpha"), core=False)
    ev = k.tel.read()[-1]
    assert ev["type"] == "kill" and ev["session_seconds"] == 50
    assert k.reg.running() is None


def test_zombie_derivation(kernel3, cfg, clock):
    p = kernel3.reg.resolve("beta")
    img = ContextFile.read(kernel3.image_path(p)).image
    old = clock() - 40 * 86400
    state, days, residue = derive_state(p, img, old, cfg, clock())
    assert state == State.ZOMBIE and days >= 39 and residue > 0
    assert derive_state(p, img, clock() - 86400, cfg, clock())[0] == State.READY
    p.state = State.RUNNING
    assert derive_state(p, img, old, cfg, clock())[0] == State.RUNNING


def test_model_unavailable_does_not_break_switch(kernel, repos, clock):
    def dead(*a, **k):
        raise OllamaUnavailable("http://localhost:1")
    kernel._extractor = dead
    kernel.register_project(repos["alpha"], "alpha")
    kernel.register_project(repos["beta"], "beta")
    r = kernel.switch("alpha")
    assert r.restore.image is None and r.restore.error_kind == "model"
    assert r.dest.state == State.RUNNING
    rows, report, _ = kernel.table()
    assert len(rows) == 2
