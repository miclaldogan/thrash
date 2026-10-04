import pytest
import typer
from thrash.cli import admission
from thrash.interrupts import InterruptQueue


def test_oom_requires_explicit_action(kernel3, monkeypatch):
    k = kernel3
    k.cfg.oom_active = 3
    monkeypatch.setattr('thrash.cli._interactive', lambda: False)
    before = k.cfg.registry_path.read_bytes()
    with pytest.raises(typer.Exit):
        admission(k, 'vision-lab')
    assert k.cfg.registry_path.read_bytes() == before
    assert admission(k, 'vision-lab', force=True)
    assert not admission(k, 'vision-lab', interrupt=True)
    assert InterruptQueue(k.cfg).read()[0].text == 'Consider project vision-lab'
    assert admission(k, 'vision-lab', suspend='alpha')
    assert k.active_count() == 2
