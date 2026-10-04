from thrash.visuals import VisualPressure


def test_visual_recovery_and_motion():
    v = VisualPressure()
    assert v.tick('NORMAL') == 0
    assert v.tick('PANIC') == 3
    assert v.tick('NORMAL') == 2
    assert v.tick('NORMAL') == 1
    assert v.tick('NORMAL') == 0
    v.tick('PANIC', True)
    assert v.offset(True) == 0
    assert v.tick('NORMAL', True) == 0
