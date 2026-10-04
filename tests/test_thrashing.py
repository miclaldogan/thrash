from thrash.config import Config
from thrash.scheduler import evaluate_thrashing, load_shares
from thrash.registry import Process

NOW = 1_800_000_000.0


def sw(minutes_ago, session=60, recon=False):
    return {"ts": NOW - minutes_ago * 60, "type": "switch", "ended_project": "x",
            "session_seconds": session, "reconstructed": recon}


def test_nominal():
    r = evaluate_thrashing([sw(10, 3600)], active=2, cfg=Config(), now=NOW)
    assert r.state == "NOMINAL" and r.fired == []


def test_rapid_switching_thrashes():
    events = [sw(i) for i in range(1, 8)]
    r = evaluate_thrashing(events, active=3, cfg=Config(), now=NOW)
    assert r.state == "THRASHING"
    assert {"switch rate", "short sessions"} <= set(r.fired)
    assert r.switches == 7


def test_single_signal_is_strained():
    r = evaluate_thrashing([sw(5, 3600)], active=4, cfg=Config(), now=NOW)
    assert r.state == "STRAINED" and r.fired == ["working-set pressure"]


def test_window_excludes_old_events():
    events = [sw(60 * 10 + i) for i in range(10)]
    assert evaluate_thrashing(events, 1, Config(), NOW).switches == 0


def test_thresholds_configurable():
    cfg = Config(switch_limit=2, signals_required=1)
    events = [sw(5, 3600), sw(4, 3600)]
    assert evaluate_thrashing(events, 1, cfg, NOW).state == "THRASHING"


def test_reconstruction_signal():
    events = [sw(i + 1, 3600, recon=True) for i in range(3)]
    r = evaluate_thrashing(events, 1, Config(), NOW)
    assert r.reconstructions == 3 and "context reconstruction" in r.fired


def test_median_needs_three_sessions():
    r = evaluate_thrashing([sw(1), sw(2)], 1, Config(), NOW)
    assert "short sessions" not in r.fired


def test_load_shares():
    events = [{"ts": NOW - 100, "ended_project": "a", "session_seconds": 300},
              {"ts": NOW - 50, "ended_project": "b", "session_seconds": 100}]
    run = Process(pid=1, alias="b", path="/x", state="RUNNING", registered_at=0, running_since=NOW - 100)
    shares = load_shares(events, run, NOW)
    assert round(shares["a"], 2) == 0.6 and round(shares["b"], 2) == 0.4
    assert load_shares([], None, NOW) == {}
