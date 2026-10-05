"""Prompt 3 visual specimens. All history comes from explicit synthetic kernel operations."""
import asyncio
import os
from pathlib import Path
os.environ.pop('NO_COLOR',None)
from thrash.demo import DemoScenario
from thrash.tui import KernelApp, FaultScreen, AskScreen, PanicScreen
from thrash.interrupts import InterruptQueue
from thrash.registry import State
from textual.widgets import Input


async def settle(app,pilot):
    for _ in range(200):
        await pilot.pause(.025)
        if app.view and not app.busy:return
    raise RuntimeError('Kernel operation did not settle')


def svg(app,path):
    # Preserve leading spaces with SVG renderers that otherwise collapse them.
    text=app.export_screenshot().replace('<svg ','<svg xml:space="preserve" ',1)
    text = text.replace("Fira Code", "Iosevka Term")
    path.write_text(text)


def dispatch(demo,alias,seconds):
    demo.clock.advance(seconds)
    demo.kernel.switch(alias)


def queue(demo,text):
    k=demo.kernel
    run=k.reg.running()
    item=InterruptQueue(k.cfg).capture(text,demo.clock(),run.alias if run else None)
    k.tel.record('irq',demo.clock(),irq_id=item.id,project=item.current)


def seed_history(demo):
    demo.advance()
    for alias in ('game-alpha','vision-lab','game-alpha','paper-crane','game-alpha'):
        dispatch(demo,alias,3600)
    demo.clock.advance(26*3600)
    for p in demo.kernel.reg.all():demo.kernel.snapshot(p,force=True)
    for alias in ('vision-lab','paper-crane','game-alpha','vision-lab'):
        dispatch(demo,alias,2700)


async def capture(destination):
    destination.mkdir(parents=True,exist_ok=True)
    with DemoScenario() as demo:
        seed_history(demo)
        k=demo.kernel
        app=KernelApp(k,demo=True,reduced_motion=True)
        async with app.run_test(size=(120,44)) as pilot:
            await settle(app,pilot)
            svg(app,destination/'01-normal.svg')
            svg(app,destination/'08-scheduler-scar.svg')
            await pilot.resize_terminal(80,24)
            svg(app,destination/'10-compact.svg')
            await pilot.resize_terminal(120,44)
            # Capture the real input surface before committing the synthetic thought.
            await pilot.press('i')
            app.screen.query_one(Input).value='Try the turn-pose test before changing the rig'
            svg(app,destination/'07-irq-capture.svg')
            await pilot.press('enter')
            await settle(app,pilot)
            # A fourth runnable process fills the configured allocation without a switch storm.
            demo.add('circuit-garden')
            app.start('refresh');await settle(app,pilot)
            assert app.view.diagnostics.mode=='PRESSURE'
            svg(app,destination/'03-pressure.svg')
            # Stale context, and a genuine changed file inside this synthetic workspace.
            proc=k.reg.resolve('game-alpha')
            cf=k.load_context(proc)
            cf.image.meta.created_at=demo.clock()-71*3600
            cf.write(k.image_path(proc))
            # Resident wins over this unchanged older swap via saved_at.
            root=Path(proc.path)
            with (root/'notes.md').open('a') as f:f.write('\nUPDATE: Engine integration started before the turn test.\n')
            os.utime(root/'notes.md',(demo.clock(),)*2)
            app.start('switch','game-alpha');await settle(app,pilot)
            assert isinstance(app.screen,FaultScreen)
            svg(app,destination/'02-page-fault.svg')
            app.screen.stage=2;app.screen.present()
            await pilot.pause(.01)
            svg(app,destination/'02b-registers-stack.svg')
            await pilot.press('escape')
            for i in range(12):dispatch(demo,'vision-lab' if i%2==0 else 'game-alpha',90)
            app.reduced_motion=False
            app.start('refresh');await settle(app,pilot)
            assert app.view.diagnostics.mode=='THRASHING'
            app.animate_pressure();await pilot.pause(.05)
            svg(app,destination/'04-thrashing.svg')
            # A real suspension changes the allocation; the trace is only a presentation echo.
            app.start('suspend','paper-crane');await settle(app,pilot)
            app.swap_effect=('paper-crane',4)
            app.render_scope();await pilot.pause(.05)
            svg(app,destination/'09-swap-migration.svg')
            # Restore capacity and meet all existing PANIC gates with synthetic telemetry.
            k.wake('paper-crane')
            demo.add('film-study',age_days=20)
            demo.add('signal-box')
            demo.clock.advance(25*3600)
            for i in range(22):dispatch(demo,'vision-lab' if i%2==0 else 'game-alpha',90)
            for i in range(8):queue(demo,f'Synthetic interrupt {i+2}')
            app.start('refresh');await settle(app,pilot)
            assert isinstance(app.screen,PanicScreen)
            await pilot.pause(.8)
            svg(app,destination/'05-kernel-panic.svg')
            await pilot.press('c')
            # Full recovery includes an explicitly simulated quiet history window.
            for p in k.reg.all():
                if p.state==State.READY:k.suspend(p.alias)
            q=InterruptQueue(k.cfg)
            for item in q.read():q.acknowledge(item.id)
            demo.clock.advance(k.cfg.window_hours*3600+1)
            app.start('refresh');await settle(app,pilot)
            assert app.view.diagnostics.mode=='NORMAL'
            app.visual.level=3
            app.animate_pressure();await pilot.pause(.01)
            svg(app,destination/'06-recovery.svg')
            for _ in range(3):app.animate_pressure()
            svg(app,destination/'06b-recovered.svg')
            await pilot.press('tab')
            svg(app,destination/'09b-swap-horizon.svg')


if __name__=='__main__':
    asyncio.run(capture(Path(__file__).resolve().parents[1]/'docs'/'examples'/'scope'))
