from thrash.demo import DemoScenario
from thrash.diagnostics import diagnose
from thrash.registry import State


def test_nine_scenes_and_isolation(tmp_path, monkeypatch):
    real = tmp_path/'real-state'
    real.mkdir()
    marker = real/'marker'
    marker.write_text('untouched')
    monkeypatch.setenv('THRASH_HOME', str(real))
    with DemoScenario() as demo:
        assert demo.kernel.cfg.data_dir != real
        root = demo.root
        modes = []
        for i in range(9):
            result, message = demo.advance()
            assert 'SYNTHETIC' in message
            d = diagnose(demo.kernel)
            modes.append(d.mode)
            if i == 1:
                assert '71 hours old' in result[1].plain
                assert 'WHAT YOU FINISHED' in result[1].plain
            if i == 4:
                assert d.starved['paper-crane'].starved
            if i == 5:
                assert next(r for r in demo.kernel.table()[0] if r['proc'].alias == 'film-study')['state'] == State.ZOMBIE
            if i == 6:
                assert d.out_of_mind
        assert modes[0] == modes[-1] == 'NORMAL'
        assert modes[3] == 'THRASHING'
        assert modes[7] == 'PANIC'
    assert not root.exists()
    assert marker.read_text() == 'untouched'
    assert list(real.iterdir()) == [marker]
