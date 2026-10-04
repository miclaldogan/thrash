from thrash.interrupts import InterruptQueue
from thrash.ollama_client import ModelError, Reply


def test_capture_persists_without_switch(kernel3):
    k = kernel3
    k.switch('alpha')
    registry = k.cfg.registry_path.read_bytes()
    image = k.image_path(k.reg.running()).read_bytes()
    events = k.tel.read()
    q = InterruptQueue(k.cfg)
    item = q.capture('Try a smaller prototype', k.clock(), 'alpha')
    assert InterruptQueue(k.cfg).read()[0] == item
    assert k.cfg.registry_path.read_bytes() == registry
    assert k.image_path(k.reg.running()).read_bytes() == image
    assert k.tel.read() == events
    q.acknowledge(item.id)
    assert q.read()[0].acknowledged


def test_redaction_before_storage_and_routing(cfg, monkeypatch):
    q = InterruptQueue(cfg)
    item = q.capture('TODO api_key=secretvalue123456789 /home/person/private/file', 1)
    assert 'secretvalue123456789' not in q.path.read_text()
    assert '/home/person' not in q.path.read_text()
    def route(*args):
        assert 'secretvalue123456789' not in str(args)
        return Reply('{"kind":"existing","project":"invented"}', 0)
    monkeypatch.setattr('thrash.interrupts.chat_json', route)
    assert q.route(item.id, ['game-alpha']).route.kind == 'unclear'


def test_no_model_capture_survives(cfg, monkeypatch):
    q = InterruptQueue(cfg)
    item = q.capture('Idea', 1)
    def unavailable(*args):
        raise ModelError('offline')
    monkeypatch.setattr('thrash.interrupts.chat_json', unavailable)
    assert q.route(item.id, []).route.kind == 'unclear'
    assert q.read()[0].text == 'Idea'
