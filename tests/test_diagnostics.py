from thrash.diagnostics import starvation, diagnose
from thrash.interrupts import InterruptQueue
from thrash.registry import State


def test_starvation_needs_contention_and_ready(kernel3, clock):
    k = kernel3
    p = k.reg.resolve('alpha')
    clock.advance(72*3600)
    assert not starvation(p, [], k.cfg, clock()).starved
    events = [{'ts': clock(), 'type':'switch', 'to_project':'beta'}]*6
    assert starvation(p, events, k.cfg, clock()).starved
    k.reg.set_state(p, State.SLEEPING, clock())
    assert not starvation(p, events, k.cfg, clock()).starved
    k.reg.set_state(p, State.READY, clock())
    assert not starvation(p, events, k.cfg, clock()).starved


def test_panic_is_conjunctive_and_recovers(kernel3, clock):
    k = kernel3
    k.cfg.panic_active = 3
    clock.advance(72*3600)
    for _ in range(20):
        k.tel.record('switch', clock(), to_project='alpha')
    assert diagnose(k).mode != 'PANIC'
    q = InterruptQueue(k.cfg)
    for _ in range(8):
        q.capture('synthetic idea', clock())
    assert diagnose(k).mode == 'PANIC'
    k.suspend('beta')
    assert diagnose(k).mode != 'PANIC'
    clock.advance(k.cfg.window_hours*3600+1)
    assert diagnose(k).mode == 'NORMAL'


def test_ready_timestamp_legacy_and_reset(kernel3, clock):
    k = kernel3
    k.switch('alpha')
    clock.advance(100)
    k.switch('beta')
    assert k.reg.resolve('alpha').ready_since == clock()
    k.reg.resolve('alpha').ready_since = None
    assert starvation(k.reg.resolve('alpha'), [], k.cfg, clock()).waiting_hours >= 0
