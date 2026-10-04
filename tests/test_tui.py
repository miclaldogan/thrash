import asyncio
import pytest
from textual.widgets import DataTable, Input
from thrash.tui import KernelApp, ReportScreen, memory_text, monitor
from thrash.interrupts import InterruptQueue
from thrash.registry import State


async def settled(app, pilot):
    for _ in range(100):
        await pilot.pause(.02)
        if not app.busy and app.view:
            return
    raise AssertionError('Worker did not finish')


@pytest.mark.asyncio
async def test_keyboard_restore_irq_suspend_wake(kernel3):
    app = KernelApp(kernel3, reduced_motion=True)
    async with app.run_test(size=(120, 40)) as pilot:
        await settled(app, pilot)
        assert app.query_one(DataTable).row_count == 3
        await pilot.press('enter')
        await settled(app, pilot)
        assert isinstance(app.screen, ReportScreen)
        assert kernel3.reg.running().alias == 'alpha'
        await pilot.press('escape', 'i')
        app.screen.query_one(Input).value = '[type=CNAME] idea'
        await pilot.press('enter')
        await settled(app, pilot)
        assert InterruptQueue(kernel3.cfg).read()[0].text == '[type=CNAME] idea'
        assert kernel3.reg.running().alias == 'alpha'
        await pilot.press('s')
        await settled(app, pilot)
        assert kernel3.reg.resolve('alpha').state == State.SLEEPING
        await pilot.press('w')
        await settled(app, pilot)
        assert kernel3.reg.resolve('alpha').state == State.READY
        await pilot.press('escape', 'tab', 'tab', 'a')
        await settled(app, pilot)
        assert InterruptQueue(kernel3.cfg).read()[0].acknowledged


@pytest.mark.asyncio
async def test_context_literal_and_termination_cancel(kernel3):
    p = kernel3.reg.resolve('alpha')
    cf = kernel3.load_context(p)
    cf.image.next_action = '[type=CNAME] inspect /home/person/private/file'
    cf.write(kernel3.image_path(p))
    app = KernelApp(kernel3)
    async with app.run_test(size=(100, 35)) as pilot:
        await settled(app, pilot)
        await pilot.press('c')
        await settled(app, pilot)
        assert isinstance(app.screen, ReportScreen)
        assert '[type=CNAME]' in app.screen.content.plain
        assert '/home/person' not in app.screen.content.plain
        await pilot.press('escape', 'k', 'escape')
        assert kernel3.reg.resolve('alpha').state == State.READY


def test_memory_uses_real_units(kernel3):
    view = monitor(kernel3)
    text = memory_text(view).plain
    assert '300' not in text
    assert '100 units' in text
    assert 'RESIDENT' in text
