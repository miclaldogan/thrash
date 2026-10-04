import pytest

from conftest import commit, fake_extractor
from thrash.extract import sanitize
from thrash.process_image import ContextFile, ModelOutput
from thrash.registry import Process
from thrash.scheduler import load_shares


def test_rescan_restores_newest_image_not_old_swap(kernel3, repos, clock):
    k = kernel3
    k.suspend("alpha")
    old = k.load_context(k.reg.resolve("alpha"))
    clock.advance(20)
    commit(repos["alpha"], "new task", {"notes.md": "next task"})

    def changed(alias, ctx, previous, now):
        img = fake_extractor(alias, ctx, previous, now)
        img.program_counter.task = "new task"
        return img

    k._extractor = changed
    p = k.reg.resolve("alpha")
    k.snapshot(p, force=True)
    assert ContextFile.read(k.swap_path(p)).saved_at == old.saved_at
    report = k.wake("alpha")
    assert report.image.program_counter.task == "new task"
    assert report.age_s == 0
    assert report.drift.level == "NONE"


def test_restore_falls_back_to_newer_swap_or_when_resident_corrupt(kernel3, clock):
    k = kernel3
    p = k.reg.resolve("alpha")
    k.page_out(p)
    swap = ContextFile.read(k.swap_path(p))
    swap.saved_at += 10
    swap.image.program_counter.task = "swap task"
    swap.write(k.swap_path(p))
    assert k.restore(p).image.program_counter.task == "swap task"
    k.image_path(p).write_text("damaged")
    assert k.restore(p).image.program_counter.task == "swap task"


@pytest.mark.parametrize("source", ["", " ", "invented.md"])
def test_unsourced_decisions_are_inferred(source):
    out = ModelOutput(program_counter="next", decisions=[{"text": "use small batches", "source": source, "explicit": True}])
    out, _ = sanitize(out, {"notes.md"})
    assert not out.decisions[0].explicit
    assert out.decisions[0].source == ""


def test_valid_source_is_normalized_and_explicit_preserved():
    out = ModelOutput(program_counter="next", decisions=[{"text": "use small batches", "source": " ./notes.md ", "explicit": True}])
    out, dropped = sanitize(out, {"notes.md"})
    assert out.decisions[0].explicit and out.decisions[0].source == "notes.md"
    assert dropped == 0


def test_load_clips_completed_sessions_at_window_start():
    now = 300000.0
    run = Process(pid=2, alias="beta", path="/synthetic", state="RUNNING", registered_at=1, running_since=now - 43200)
    events = [{"ts": now - 43200, "ended_project": "alpha", "session_seconds": 172800}]
    assert load_shares(events, run, now) == {"alpha": 0.5, "beta": 0.5}


def test_load_clips_running_session_and_ignores_future_events():
    now = 300000.0
    run = Process(pid=1, alias="alpha", path="/synthetic", state="RUNNING", registered_at=1, running_since=now - 172800)
    events = [{"ts": now, "ended_project": "beta", "session_seconds": 86400},
              {"ts": now + 3600, "ended_project": "future", "session_seconds": 100000}]
    assert load_shares(events, run, now) == {"alpha": 0.5, "beta": 0.5}


def test_failed_core_replace_keeps_previous_dump(kernel3, monkeypatch):
    k = kernel3
    path = k.core_path("alpha")
    path.write_text("previous core")
    plan = k.kill_plan("alpha")

    def fail_replace(*args):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(type(path), "replace", fail_replace)
    with pytest.raises(OSError):
        k.kill(plan, core=True)
    assert path.read_text() == "previous core"
    assert k.reg.resolve("alpha").state.value == "READY"
