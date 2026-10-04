import pytest

from thrash.registry import Registry, RegistryError, State


def test_register_and_resolve(cfg, repos, clock):
    r = Registry(cfg)
    a = r.register("alpha", repos["alpha"], clock())
    assert a.pid == 1 and a.pid_str == "001" and a.state == State.READY
    assert r.resolve("alpha") is a and r.resolve("1") is a and r.resolve("alp") is a
    assert Registry(cfg).resolve("alpha").pid == 1  # persisted


def test_duplicate_alias_and_path_rejected(cfg, repos, clock):
    r = Registry(cfg)
    r.register("alpha", repos["alpha"], clock())
    with pytest.raises(RegistryError):
        r.register("alpha", repos["beta"], clock())
    with pytest.raises(RegistryError):
        r.register("other", repos["alpha"], clock())


def test_invalid_alias(cfg, repos, clock):
    with pytest.raises(RegistryError):
        Registry(cfg).register("Bad Name!", repos["alpha"], clock())


def test_only_one_running(cfg, repos, clock):
    r = Registry(cfg)
    a = r.register("alpha", repos["alpha"], clock())
    b = r.register("beta", repos["beta"], clock())
    r.set_running(a, clock())
    r.set_running(b, clock())
    assert [p.alias for p in r.processes if p.state == State.RUNNING] == ["beta"]
    assert a.state == State.READY


def test_ambiguous_prefix(cfg, repos, clock):
    r = Registry(cfg)
    r.register("game-a", repos["alpha"], clock())
    r.register("game-b", repos["beta"], clock())
    with pytest.raises(RegistryError, match="ambiguous"):
        r.resolve("game")


def test_zombie_not_assignable(cfg, repos, clock):
    r = Registry(cfg)
    a = r.register("alpha", repos["alpha"], clock())
    with pytest.raises(RegistryError):
        r.set_state(a, State.ZOMBIE, clock())
