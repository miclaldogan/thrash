"""Explicitly synthetic scenes, isolated under a temporary directory, with no model calls."""
from __future__ import annotations
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from rich.text import Text
from .config import Config
from .diagnostics import diagnose
from .interrupts import InterruptQueue
from .process_image import ProcessImage, ImageMeta, estimate_units
from .scheduler import Kernel
from .registry import State
from . import ui

SCENES = ('Clean kernel', 'PAGE FAULT', 'Interrupt', 'Thrashing', 'Starvation',
          'Zombie', 'OUT OF MIND', 'Kernel panic', 'Recovery')


class DemoClock:
    def __init__(self):
        self.now = 1800000000.0
    def __call__(self):
        return self.now
    def advance(self, seconds):
        self.now += seconds


def fixture_image(alias, ctx, previous, now):
    """Hand-authored fixture, not represented as a model response."""
    image = ProcessImage(
        project=alias,
        summary='Built the camera prototype and checked idle poses. Turn testing is unfinished.',
        completed=[{'text':'Camera follow prototype runs', 'source':'notes.md', 'explicit':True}],
        decisions=[{'text':'Validate rig before engine integration', 'reason':'Avoid rebuilding an untested rig',
                    'source':'notes.md', 'explicit':True}],
        program_counter={'task':'Stopped before testing the 45-degree turn pose', 'confidence':.86},
        registers={'rig':'idle validated; turning untested', 'engine':'integration deferred'},
        stack=['Validate turn pose', 'Export validated rig', 'Integrate controller'],
        open_handles=['notes.md', 'README.md'], unresolved=['Does the shoulder deform during a turn?'],
        blockers=['Turn pose has not been validated'],
        next_action='Open notes.md and test the rig at a 45-degree turn before engine integration.',
        last_useful_state='Idle-pose prototype is available.', purpose='Explore a small character controller.',
        failures=['Early integration needed rework because the rig changed.'],
        resurrection_hint='Return when a turn-pose test can be completed.', evidence=['notes.md'],
        meta=ImageMeta(created_at=now, model='SYNTHETIC FIXTURE — no inference', context_version=2,
                       head=ctx.fingerprint.head, todo_count=ctx.todo_count))
    image.meta.ctx_units = estimate_units(image.model_dump_json())
    return image


class DemoScenario:
    def __init__(self):
        self.temp = TemporaryDirectory(prefix='thrash-synthetic-')
        self.root = Path(self.temp.name)
        self.clock = DemoClock()
        self.kernel = Kernel(Config(data_dir=self.root/'state'), extractor=fixture_image, clock=self.clock)
        self.scene = -1

    def close(self):
        self.temp.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def add(self, alias, age_days=0):
        root = self.root/'workspace'/alias
        root.mkdir(parents=True)
        (root/'README.md').write_text('# Synthetic character controller\nDemo fixture; not a real project.\n')
        (root/'notes.md').write_text('- [x] Camera follow prototype runs\n'
            'DECISION: Validate rig before engine integration. WHY: Avoid rebuilding an untested rig.\n'
            'STOPPED: Before the 45-degree turn test.\n- [ ] Validate shoulder during turn\n'
            'FAILED: Early integration needed rework because the rig changed.\n')
        for path in root.iterdir():
            os.utime(path, (self.clock()-age_days*86400,)*2)
        self.kernel.register_project(root, alias)

    def switches(self, count):
        for _ in range(count):
            run = self.kernel.reg.running()
            self.clock.advance(90)
            self.kernel.switch('vision-lab' if run and run.alias == 'game-alpha' else 'game-alpha')

    def advance(self):
        if self.scene >= 8:
            return None, 'Synthetic demo complete. Q exits and removes temporary demo state.'
        self.scene += 1
        k = self.kernel
        result = None
        detail = ''
        if self.scene == 0:
            for alias in ('game-alpha', 'paper-crane', 'vision-lab'):
                self.add(alias)
        elif self.scene == 1:
            self.clock.advance(71*3600)
            root = Path(k.reg.resolve('game-alpha').path)
            (root/'notes.md').write_text((root/'notes.md').read_text() + '\nUPDATE: Engine integration now started; rig validation is incomplete.\n')
            os.utime(root/'notes.md', (self.clock(),)*2)
            report = k.switch('game-alpha').restore
            content = Text('SYNTHETIC · Process image is 71 hours old.\n', style='yellow')
            content.append(ui.resume_text(report.resume))
            result = ('PAGE FAULT · game-alpha', content)
        elif self.scene == 2:
            item = InterruptQueue(k.cfg).capture('Try a procedural walk cycle', self.clock(), 'game-alpha')
            k.tel.record('irq', self.clock(), irq_id=item.id, project='game-alpha')
            detail = 'IRQ queued; game-alpha keeps its running session.'
        elif self.scene == 3:
            self.switches(8)
        elif self.scene == 4:
            self.clock.advance(49*3600)
            self.switches(6)
            wait = diagnose(k).starved['paper-crane']
            detail = f'paper-crane READY {wait.waiting_hours:.0f}h; {wait.other_dispatches} other dispatches; no execution.'
        elif self.scene == 5:
            self.add('film-study', age_days=20)
            detail = 'film-study: 20 simulated days idle plus unfinished repository residue.'
        elif self.scene == 6:
            self.add('circuit-garden')
            self.add('signal-box')
            d = diagnose(k)
            detail = f'OUT OF MIND: {d.report.active} active. Suspend, queue an IRQ, or force admission.'
        elif self.scene == 7:
            self.clock.advance(25*3600)
            self.switches(22)
            for i in range(8):
                InterruptQueue(k.cfg).capture(f'Synthetic idea {i+2}', self.clock(), k.reg.running().alias)
            detail = 'All four PANIC gates are met. Controls remain available.'
        elif self.scene == 8:
            for p in k.reg.all():
                if p.state == State.READY:
                    k.suspend(p.alias)
            queue = InterruptQueue(k.cfg)
            for item in queue.read():
                queue.acknowledge(item.id)
            self.clock.advance(k.cfg.window_hours*3600+1)
            detail = 'READY work paged to swap; IRQs acknowledged; simulated quiet window elapsed.'
        label = f'SYNTHETIC SCENE {self.scene+1}/9 · {SCENES[self.scene]}'
        return result, label + (' · '+detail if detail else '')


def run_script():
    with DemoScenario() as demo:
        ui.console.print('SYNTHETIC DEMO — fixture images and simulated time. No model calls or real project data.')
        for _ in SCENES:
            result, message = demo.advance()
            ui.console.print(Text('\n'+message, style='bold cyan'))
            if result:
                ui.console.print(result[1])
            else:
                ui.render_top(*demo.kernel.table())
            d = diagnose(demo.kernel)
            ui.console.print(f'KERNEL MODE: {d.mode} · IRQ: {d.pending_irqs} · stale: {d.stale_images}')


def run_tui():
    from .tui import KernelApp
    class DemoApp(KernelApp):
        BINDINGS = [('n', 'next_scene', 'Next scene')]
        def action_next_scene(self):
            self.start('demo')
    with DemoScenario() as demo:
        demo.advance()
        app = DemoApp(demo.kernel, demo=True)
        app.demo_controller = demo
        app.run()
