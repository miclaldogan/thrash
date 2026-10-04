import pytest
from typer.testing import CliRunner

from conftest import Clock, fake_extractor, make_repo
from thrash import cli
from thrash.config import Config
from thrash.scheduler import Kernel

runner = CliRunner()


@pytest.fixture
def env(tmp_path, monkeypatch):
    cfg = Config(data_dir=tmp_path / "data")
    clock = Clock()
    monkeypatch.setattr(cli, "get_kernel", lambda: Kernel(cfg, extractor=fake_extractor, clock=clock))
    return cfg, clock, tmp_path


def test_end_to_end_and_alias_only(env):
    cfg, clock, tmp = env
    secret = make_repo(tmp / "my-secret-startup-x")
    other = make_repo(tmp / "other")
    for repo, alias in ((secret, "game-alpha"), (other, "research-beta")):
        res = runner.invoke(cli.app, ["init", "--path", str(repo), "--alias", alias])
        assert res.exit_code == 0, res.output
    assert "001" in runner.invoke(cli.app, ["ps"]).output
    runner.invoke(cli.app, ["switch", "research-beta"])
    clock.advance(300)
    out = runner.invoke(cli.app, ["switch", "game-alpha"]).output
    assert "CONTEXT SWITCH" in out and "PAGE FAULT" in out and "NEXT INSTRUCTION" in out
    for cmd in (["top"], ["ps"], ["status"], ["switch", "research-beta"], ["suspend", "game-alpha"], ["wake", "game-alpha"]):
        o = runner.invoke(cli.app, cmd)
        assert o.exit_code == 0, (cmd, o.output)
        assert "secret-startup" not in o.output and str(secret) not in o.output
    top = runner.invoke(cli.app, ["top"]).output
    assert "game-alpha" in top and "STATE:" in top


def test_thrashing_visible_in_top(env):
    cfg, clock, tmp = env
    for n in ("a1", "b1"):
        runner.invoke(cli.app, ["init", "--path", str(make_repo(tmp / n)), "--alias", n])
    for i in range(8):
        runner.invoke(cli.app, ["switch", "a1" if i % 2 == 0 else "b1"])
        clock.advance(30)
    assert "THRASHING DETECTED" in runner.invoke(cli.app, ["top"]).output


def test_unknown_process_exit_code(env):
    res = runner.invoke(cli.app, ["switch", "ghost"])
    assert res.exit_code == 1


def test_fork_pressure_non_interactive(env, monkeypatch):
    cfg, clock, tmp = env
    monkeypatch.setenv("THRASH_MAX_ACTIVE", "1")
    cfg.max_active = 1
    runner.invoke(cli.app, ["init", "--path", str(make_repo(tmp / "p1")), "--alias", "p1"])
    res = runner.invoke(cli.app, ["fork", "p2", "--path", str(make_repo(tmp / "p2"))])
    assert res.exit_code == 0 and "resource pressure detected" in res.output and "p2" in res.output


def test_no_model_top_still_works(tmp_path, monkeypatch):
    cfg = Config(data_dir=tmp_path / "d", ollama_url="http://127.0.0.1:1")
    monkeypatch.setattr(cli, "get_kernel", lambda: Kernel(cfg))
    r = runner.invoke(cli.app, ["init", "--path", str(make_repo(tmp_path / "r")), "--alias", "r"])
    assert r.exit_code == 0 and "LOCAL MODEL UNAVAILABLE" in r.output
    assert runner.invoke(cli.app, ["top"]).exit_code == 0
