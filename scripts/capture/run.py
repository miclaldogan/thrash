"""Reproducible submission media. Only hand-authored, temporary demo projects.

Hold durations edit the presentation of actual UI states; event time is simulated
by DemoClock. They are not model latency measurements. See docs/demo-script.md.
"""
import argparse
import asyncio
import os
from pathlib import Path
import sys
os.environ.pop('NO_COLOR',None)
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'demo'))
from capture_scope import seed_history,dispatch,queue,settle
from render import svg,screenshot,gif,font
from thrash.demo import DemoScenario
from thrash.tui import KernelApp,FaultScreen,PanicScreen
from thrash.registry import State
from thrash.interrupts import InterruptQueue
from textual.widgets import Input


async def capture(destination):
    destination.mkdir(parents=True,exist_ok=True)
    animations={}
    with DemoScenario() as demo:
        seed_history(demo);k=demo.kernel
        app=KernelApp(k,demo=True,reduced_motion=True)
        async with app.run_test(size=(120,40)) as pilot:
            await settle(app,pilot)
            screenshot(app,destination,'01-normal');screenshot(app,destination,'07-scheduler-scar')
            # The selected scheduler cursor is game-alpha; dispatch the same selection.
            fault=[(svg(app),1)]
            proc=k.reg.resolve('game-alpha');cf=k.load_context(proc)
            cf.image.meta.created_at=demo.clock()-71*3600;cf.write(k.image_path(proc))
            root=Path(proc.path)
            with (root/'notes.md').open('a') as f:f.write('\nUPDATE: Engine integration started before the turn test.\n')
            os.utime(root/'notes.md',(demo.clock(),)*2)
            app.start('switch','game-alpha');await settle(app,pilot)
            assert isinstance(app.screen,FaultScreen)
            for stage,duration in [(0,1),(1,1),(2,1),(3,2),(4,2)]:
                app.screen.stage=stage;app.screen.present();await pilot.pause(.02)
                fault.append((svg(app),duration))
            screenshot(app,destination,'02-page-fault');animations['page-fault']=fault
            await pilot.press('enter');await settle(app,pilot)
            # Input, queue confirmation and unchanged RUNNING process are real operations.
            running=k.reg.running().alias;irq=[(svg(app),1)]
            await pilot.press('i');await pilot.pause(.05)
            app.screen.query_one(Input).value='';await pilot.pause(.02);irq.append((svg(app),.5))
            for value in ('Try the turn-pose test','Try the turn-pose test before changing the rig'):
                app.screen.query_one(Input).value=value;await pilot.pause(.02);irq.append((svg(app),1))
            screenshot(app,destination,'03-irq')
            await pilot.press('enter');await settle(app,pilot)
            assert k.reg.running().alias==running
            irq.append((svg(app),2.5));animations['irq']=irq
            # Real recorded dispatches activate the existing scheduler heuristic.
            demo.add('circuit-garden');app.start('refresh');await settle(app,pilot)
            thrashing=[(irq[0][0],1),(svg(app),1)]
            for i in range(12):
                dispatch(demo,'vision-lab' if i%2==0 else 'game-alpha',90)
                if i in (2,5,8,11):
                    app.start('refresh');await settle(app,pilot)
                    app.reduced_motion=False;app.animate_pressure();await pilot.pause(.02)
                    thrashing.append((svg(app),.75))
            assert app.view.diagnostics.mode=='THRASHING'
            screenshot(app,destination,'04-thrashing')
            for _ in range(4):
                app.animate_pressure();await pilot.pause(.02);thrashing.append((svg(app),.5))
            animations['thrashing']=thrashing
            recovery=[(svg(app),1)]
            app.start('suspend','paper-crane');await settle(app,pilot)
            app.swap_effect=('paper-crane',4);app.render_scope();await pilot.pause(.02)
            recovery.append((svg(app),1.5))
            # Suspension reduces active-set pressure immediately. Switch pressure needs
            # its configured quiet window to expire, explicitly simulated here.
            demo.clock.advance(k.cfg.window_hours*3600+1)
            app.start('refresh');await settle(app,pilot)
            for _ in range(4):
                app.animate_pressure();await pilot.pause(.02);recovery.append((svg(app),.5))
            assert app.view.diagnostics.mode=='NORMAL'
            recovery.append((svg(app),2));screenshot(app,destination,'05-swap-recovery')
            animations['swap-recovery']=recovery
            k.wake('paper-crane');demo.add('film-study',age_days=20);demo.add('signal-box')
            demo.clock.advance(25*3600)
            for i in range(22):dispatch(demo,'vision-lab' if i%2==0 else 'game-alpha',90)
            for i in range(8):queue(demo,f'Try experiment {i+1}')
            app.start('refresh');await settle(app,pilot)
            assert isinstance(app.screen,PanicScreen)
            await pilot.pause(.8);screenshot(app,destination,'06-kernel-panic')
    for name,frames in animations.items():
        gif(frames,destination/(name+'.gif'));print(name,'rendered',flush=True)
    print('Capture font:',font()[0],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path('docs/media'))
    args=p.parse_args();asyncio.run(capture(args.output))
