"""A terminal client of the kernel. All mutation and repository I/O is serialized off-UI."""
from __future__ import annotations

import os
from dataclasses import dataclass
from rich.text import Text, Span
from textual import work
from textual.message import Message
from textual.binding import Binding
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll, Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static, Input, Button, Label

from . import ui
from .diagnostics import diagnose
from .interrupts import InterruptQueue
from .registry import State
from .scheduler import CoreDump
from .resume import build_resume_report
from .visuals import VisualPressure
from . import scope


@dataclass
class Monitor:
    rows: list
    diagnostics: object
    events: list
    images: dict
    now: float
    capacity: int = 4
    stale_hours: float = 24


def monitor(kernel):
    kernel.reg.load()
    for p in kernel.reg.all(include_terminated=True):
        ui.remember_project(p)
    rows, _, _ = kernel.table(include_terminated=True)
    for row in rows:
        row['core_saved'] = kernel.core_path(row['proc'].alias).is_file()
    return Monitor(rows, diagnose(kernel), kernel.tel.read(),
                   {r['proc'].alias: kernel.load_context(r['proc']) for r in rows}, kernel.clock(), kernel.cfg.max_active, kernel.cfg.stale_hours)


def memory_text(view):
    """Printable page-map compatibility surface; WSS remains a separate estimate."""
    text = scope.page_text(view)
    text.append('\n\nSAVED IMAGE SIZE / characters ÷ 4, not allocation frames\n',style=scope.GRAPHITE)
    for row in view.rows:
        text.append(f"{row['proc'].alias}: {row['ctx'] or 0} units\n",style=scope.BONE)
    return text


class ReportScreen(ModalScreen):
    BINDINGS = [('escape', 'close', 'Close'), ('q', 'close', 'Close')]
    def __init__(self, title, content):
        super().__init__()
        self.heading, self.content = title, content.copy()
        self.content.style = scope.BONE
        self.content.spans = [Span(span.start, span.end,
            scope.RUST if 'yellow' in str(span.style) or 'red' in str(span.style) else
            scope.GRAPHITE if 'dim' in str(span.style) else scope.BONE)
            for span in self.content.spans]

    def compose(self) -> ComposeResult:
        with Vertical(id='report-dialog'):
            yield Static(Text(self.heading, style=scope.BONE))
            with VerticalScroll():
                yield Static(self.content, markup=False)
            yield Button('Return to kernel [Esc]', id='close')

    def action_close(self):
        self.dismiss()

    def on_button_pressed(self, event):
        self.dismiss()


class AskScreen(ModalScreen[str | None]):
    BINDINGS = [('escape', 'cancel', 'Cancel')]
    def __init__(self, title, confirm=False, initial="", submit="Queue interrupt", placeholder="Capture the thought; keep your current execution."):
        super().__init__()
        self.heading, self.confirm = title, confirm
        self.initial, self.submit, self.placeholder = initial, submit, placeholder

    def compose(self) -> ComposeResult:
        with Vertical(id='ask-dialog'):
            yield Label(Text(self.heading))
            if not self.confirm:
                yield Input(value=self.initial, placeholder=self.placeholder, id='answer')
            with Horizontal():
                yield Button('Confirm' if self.confirm else self.submit, id='accept')
                yield Button('Cancel', id='cancel')

    def on_mount(self):
        if not self.confirm:
            self.query_one(Input).focus()

    def action_cancel(self):
        self.dismiss(None)

    def on_input_submitted(self, event):
        if event.value.strip():
            self.dismiss(event.value)

    def on_button_pressed(self, event):
        if event.button.id == 'cancel':
            self.dismiss(None)
        elif self.confirm:
            self.dismiss('yes')
        else:
            value = self.query_one(Input).value
            if value.strip():
                self.dismiss(value)


class SchedulerCursor(DataTable):
    """Use Textual's keyboard/scroll mechanics, with a single literal scheduler rail."""
    def __init__(self, **kwargs):
        super().__init__(cursor_type='row', show_header=False, show_row_labels=False,
                         show_cursor=True, cursor_foreground_priority="renderable", zebra_stripes=False, cell_padding=0, **kwargs)


class FaultScreen(ReportScreen):
    BINDINGS = [('escape', 'close', 'Return'), ('q', 'close', 'Return'),
                ('space', 'advance', 'Reveal'), ('enter', 'resolve', 'Resolve')]
    def __init__(self, title, content, report=None, reduced_motion=False):
        super().__init__(title, content)
        self.report = report
        self.reduced_motion = reduced_motion
        self.stage = 4 if reduced_motion else 0
        self.error = None

    def compose(self) -> ComposeResult:
        with Vertical(id='fault-shell'):
            yield Static(Text('PAGE FAULT\n'+self.heading.removeprefix('PAGE FAULT · '),style=scope.BONE), id='fault-title')
            yield Static('', id='fault-status', markup=False)
            with VerticalScroll(id='fault-scroll'):
                yield Static('', id='fault-stream', markup=False)
            yield Static('', id='fault-next', markup=False)
            yield Static('SPACE reveal   ESC return', id='fault-rail', markup=False)

    def on_mount(self):
        self.present()
        self.set_interval(.65, self.advance_stage)

    def load_report(self, report, content):
        self.report, self.content = report, content
        self.stage = 4 if self.reduced_motion else 0
        if self.is_mounted: self.present()

    def show_error(self, message):
        self.error = ui.safe(message)
        self.present()

    def advance_stage(self):
        if self.report and self.stage<4:
            self.stage += 1
            self.present()

    def action_advance(self):
        if self.report:
            self.stage = 4
            self.present()

    def action_resolve(self):
        if self.report and self.stage<4: self.action_advance()
        else: self.dismiss()

    def present(self):
        if self.error:
            status = 'RESTORATION INTERRUPTED'
            text = Text(self.error,style=scope.RUST)
        elif self.report is None:
            status = 'locating process image… / kernel operation in progress'
            text = Text('Saved context will appear when the kernel returns evidence.\nNo presentation progress is being counted as I/O.',style=scope.GRAPHITE)
        else:
            status = ('process image located / presenting saved state' if self.report.available
                      else 'no process image recovered')
            text = scope.restoration_text(self.report,min(self.stage,3)) if self.report.available else self.content
            if self.report.available:
                status += f' / confidence {self.report.confidence:.2f} (model)'
            if self.report.snapshot_timestamp is not None:
                status += ' / '+ui.fmt_age(max(0,self.app.kernel.clock()-self.report.snapshot_timestamp))+' old'
        self.query_one('#fault-rail',Static).display = self.stage < 4
        self.query_one('#fault-status',Static).update(Text(status,style=scope.GRAPHITE))
        self.query_one('#fault-stream',Static).update(text)
        if self.report and self.report.available and self.stage>=3:
            next_text = Text('NEXT EXECUTION\n',style=scope.CYAN)
            next_text.append(ui.safe(self.report.next_action or 'Review saved evidence.'),style=scope.CYAN)
            if self.report.drift_level != 'NONE':
                next_text.append('\nReview changed evidence before executing the saved instruction.',style=scope.RUST)
            next_text.append('\n\nFAULT RESOLVED   ENTER return to execution' if self.stage==4 else '\nSaved instruction / inspect changed evidence first',style=scope.GRAPHITE)
            self.query_one('#fault-next',Static).update(next_text)
        else: self.query_one('#fault-next',Static).update('')


class PanicScreen(ModalScreen):
    BINDINGS = [('s','suspend','Suspend'),('i','interrupts','Interrupts'),
                ('c','continue','Continue'),('escape','continue','Continue'),('q','continue','Continue')]
    def __init__(self, diagnostics):
        super().__init__()
        self.diagnostics = diagnostics

    def compose(self) -> ComposeResult:
        with Vertical(id='panic-shell'):
            yield Static('KERNEL PANIC',id='panic-title',markup=False)
            yield Static('',id='panic-counts',markup=False)
            yield Static('S SUSPEND    I INTERRUPTS    C CONTINUE',id='panic-rail',markup=False)

    def on_mount(self):
        self.update_counts(self.diagnostics)
        if not self.app.reduced_motion:
            self.add_class('panic-flash')
            self.set_timer(.7,lambda:self.remove_class('panic-flash'))

    def update_counts(self, d):
        self.diagnostics = d
        text = Text('coherent working set lost\nRECOVERY ADVISORY\n\n',style=scope.GRAPHITE,justify='center')
        text.append(f'{d.report.active} runnable\n{d.report.switches} switches / {d.report.window_hours:g}h\n'
                    f'{d.pending_irqs} interrupts\n{d.stale_images} stale images\n\n',style=scope.BONE)
        text.append("scheduler is alive.\n\nuseful work isn't.",style=scope.GRAPHITE)
        self.query_one('#panic-counts',Static).update(text)

    def action_continue(self):
        self.app.panic_acknowledged = True
        self.dismiss()

    def action_interrupts(self):
        app = self.app
        app.panic_acknowledged = True
        self.dismiss()
        app.view_index = 1
        app.action_view()

    def action_suspend(self):
        candidates = self.diagnostics.candidates
        if not candidates:
            return
        self.app.push_screen(AskScreen('PAGE OUT / '+', '.join(candidates), initial=candidates[0],
                                      submit='Page out', placeholder='READY alias to suspend'),
                             lambda alias:self.app.start('suspend',alias) if alias else None)


class KernelResult(Message):
    def __init__(self, view=None, irqs=None, result=None, message=None, error=None):
        super().__init__()
        self.view, self.irqs, self.result, self.message, self.error = view, irqs, result, message, error


class KernelApp(App):
    TITLE = 'HUMAN KERNEL / SCOPE'
    ENABLE_COMMAND_PALETTE = False
    CSS = '''
    Screen { background: #090b0b; color: #ddd7c9; }
    * { scrollbar-size: 1 1; scrollbar-color: #515552; scrollbar-background: #090b0b; scrollbar-color-hover: #858580; scrollbar-color-active: #ddd7c9; }
    #identity { height: 2; padding: 0 2; color: #858580; }
    #metrics { height: auto; padding: 0 2; color: #858580; }
    #body { height: 1fr; padding: 0 2; }
    #dispatch, #frames, #core { height: auto; margin-top: 1; }
    #processes { height: 6; background: #090b0b; border: none; padding-left: 4; }
    #processes:focus { background-tint: #000000 0%; }
    #processes > .datatable--cursor { background: #090b0b; color: #ddd7c9; text-style: none; }
    #processes:focus > .datatable--cursor { background: #090b0b; color: #ddd7c9; text-style: none; }
    #processes > .datatable--hover { background: #090b0b; }
    #process-label { height: 2; margin-top: 1; color: #858580; }
    #view { height: 1fr; padding: 1 6; display: none; }
    #irq-rail { height: 1; padding: 0 2; color: #d9b56e; }
    #echo { height: 1; padding: 0 2; color: #858580; }
    #notice { height: 1; padding: 0 2; color: #858580; }
    #command-rail { height: 1; padding: 0 2; color: #858580; }
    .compact #identity { height: 1; }
    .compact #metrics { height: 1; text-wrap: nowrap; text-overflow: ellipsis; }
    .compact #dispatch, .compact #frames, .compact #core { margin-top: 0; }
    .compact #process-label { height: 1; margin-top: 0; }
    .compact #echo { display: none; }

    ModalScreen { align: center middle; background: #000000 90%; }
    #report-dialog { width: 94%; height: 94%; padding: 1 3; background: #090b0b; border: none; }
    #report-dialog VerticalScroll { height: 1fr; }
    #ask-dialog { width: 80%; max-width: 90; height: auto; padding: 2 3; background: #090b0b; border-top: solid #d9b56e; border-bottom: solid #515552; }
    #ask-dialog Label { height: auto; margin-bottom: 1; color: #d9b56e; }
    #ask-dialog Horizontal { height: 3; margin-top: 1; }
    Input { background-tint: #000000 0%; border: none; border-bottom: solid #515552; background: #090b0b; color: #ddd7c9; padding: 0; }
    Input > .input--selection { background: #353931; color: #ddd7c9; }
    Input:focus { border: none; border-bottom: solid #d9b56e; background: #090b0b; }
    Button { text-style: none; border: none; background: #090b0b; color: #858580; margin-right: 3; min-width: 12; }
    Button:hover { background: #1b1e1d; color: #ddd7c9; }
    Button:focus { background: #1b1e1d; color: #ddd7c9; text-style: underline; }
    FaultScreen { background: #000000; }
    #fault-shell { width: 100%; height: 100%; padding: 1 5; background: #000000; }
    #fault-title { height: 3; color: #ddd7c9; }
    #fault-status { height: 2; color: #858580; }
    #fault-scroll { height: 1fr; }
    #fault-stream { height: auto; }
    #fault-next { height: auto; max-height: 6; color: #90c7c5; margin-top: 1; }
    #fault-rail { height: 1; color: #858580; }
    PanicScreen { background: #090b0b; }
    #panic-shell { width: 80%; height: auto; align: center middle; }
    #panic-title { height: 3; text-align: center; color: #ddd7c9; text-style: bold; }
    .panic-flash #panic-title { color: #e77870; }
    #panic-counts { height: auto; text-align: center; }
    #panic-rail { height: 3; text-align: center; margin-top: 2; color: #858580; }
    '''
    BINDINGS = [
        ('q', 'quit_safely', 'Quit'), ('i', 'irq', 'IRQ'), ('s', 'suspend', 'Suspend'),
        ('w', 'wake', 'Wake'), ('k', 'terminate', 'Core dump'), ('c', 'context', 'Context'),
        Binding('tab', 'view', 'View', priority=True), ('a', 'ack', 'Ack IRQ'), ('r', 'refresh_context', 'Rescan'),
        ('m', 'motion', 'Motion'), ('question_mark', 'help', 'Help'),
    ]

    def __init__(self, kernel, reduced_motion=None, demo=False):
        super().__init__()
        self.kernel = kernel
        self.reduced_motion = bool(os.environ.get('THRASH_REDUCED_MOTION')) if reduced_motion is None else reduced_motion
        self.synthetic = demo
        self.busy = False
        self.view = None
        self.view_index = 0
        self.visual = VisualPressure()
        self.swap_effect = None
        self.quit_pending = False
        self.aliases = []
        self.pending_irqs = []
        self.fault_screen = None
        self.panic_acknowledged = False
        self.rebuild_stage = None
        self._terminal_width = 80
        self._terminal_height = 24

    def compose(self) -> ComposeResult:
        yield Static('HUMAN KERNEL SCOPE / 01                                      THRASH', id='identity', markup=False)
        yield Static('Reading scheduler state…', id='metrics', markup=False)
        with VerticalScroll(id='body'):
            yield Static('', id='dispatch', markup=False)
            yield Static('', id='frames', markup=False)
            yield Static('', id='core', markup=False)
            yield Static('04   SCHEDULER CURSOR / ↑↓ select · Enter dispatch', id='process-label', markup=False)
            yield SchedulerCursor(id='processes')
        with VerticalScroll(id='view'):
            yield Static('', id='alternate', markup=False)
        yield Static('', id='irq-rail', markup=False)
        yield Static('', id='echo', markup=False)
        yield Static('', id='notice', markup=False)
        yield Static('TAB VIEW   I INTERRUPT   S SUSPEND   K TERM   ? HELP', id='command-rail', markup=False)

    def on_mount(self):
        self.query_one(DataTable).add_column('scheduler', key='scheduler')
        self.query_one(DataTable).focus(scroll_visible=False)
        self.refresh_monitor()
        self.monitor_timer = self.set_interval(3, self.refresh_monitor)
        self.pressure_timer = self.set_interval(.5, self.animate_pressure)

    def on_resize(self, event):
        self._terminal_width = event.size.width
        self._terminal_height = event.size.height
        if self.view and self.is_mounted:
            self.call_after_refresh(self.render_scope)

    def selected(self):
        table = self.query_one(DataTable)
        return self.aliases[table.cursor_row] if self.aliases and table.cursor_row < len(self.aliases) else None

    def notice(self, message):
        self.query_one('#notice', Static).update(Text(ui.safe(message.replace("SYNTHETIC SCENE", "SCENE") if self.synthetic else message)))

    def refresh_monitor(self):
        if not self.busy and (not isinstance(self.screen, ModalScreen) or isinstance(self.screen, PanicScreen)):
            self.start('refresh')

    def start(self, action, alias=None, text=None):
        if self.busy:
            if action == 'irq':
                current = next((r['proc'].alias for r in self.view.rows if r['proc'].state == State.RUNNING), None) if self.view else None
                self.pending_irqs.append((current, text))
                self.notice('IRQ held in the interface; it will persist after the current kernel operation.')
            else:
                self.notice('Kernel operation in progress; wait for its durable result.')
            return
        self.busy = True
        if action != 'refresh':
            labels = {'switch':'PAGE FAULT · saving current context and restoring selected working set…',
                      'context':'Reading saved context and checking repository drift…',
                      'rescan':'Rebuilding context with local Gemma…',
                      'suspend':'Serializing working set to swap…', 'wake':'Loading saved working set…',
                      'kill':'Recovering final state and writing core dump…', 'irq':'Queuing interrupt…',
                      'ack':'Acknowledging interrupt…', 'demo':'Advancing scenario…'}
            self.notice(labels[action])
        if action in ('switch', 'wake'):
            self.fault_screen = FaultScreen('PAGE FAULT · ' + alias, Text(), reduced_motion=self.reduced_motion)
            self.push_screen(self.fault_screen)
        self.perform(action, alias, text)

    @work(thread=True, exit_on_error=False)
    def perform(self, action, alias, text):
        result = None
        message = None
        try:
            k = self.kernel
            k.reg.load()
            if action == 'demo':
                result, message = self.demo_controller.advance()
                if result and result[0].startswith('PAGE FAULT'):
                    restored = k.restore(k.reg.running(), reconstruct=False)
                    result = (*result, restored.resume)
            elif action == 'switch':
                switched = k.switch(alias)
                report = switched.restore
                result = ('PAGE FAULT · ' + alias, self.restore_content(report), report.resume)
                message = 'Working set restored. Read NEXT INSTRUCTION before dispatching another process.'
                if switched.out and switched.out.error:
                    message = 'Outgoing snapshot unavailable; previous image retained. ' + switched.out.error
            elif action == 'context' and k.reg.resolve(alias, True).state == State.TERMINATED:
                path = k.core_path(alias)
                if not path.is_file():
                    raise ValueError('No core dump was saved for this terminated process')
                core = CoreDump.model_validate_json(path.read_text())
                content = Text(ui.safe('Termination: ' + core.reason) + '\n\n')
                content.append(ui.resume_text(build_resume_report(alias, core.image)))
                result = ('CORE DUMP · ' + alias, content)
            elif action in ('context', 'wake'):
                report = k.wake(alias) if action == 'wake' else k.restore(k.reg.resolve(alias, True), reconstruct=False)
                result = ('PAGE FAULT · ' + alias if action == 'wake' else 'SAVED CONTEXT · ' + alias,
                          self.restore_content(report), report.resume if action == 'wake' else None)
            elif action == 'rescan':
                snap = k.snapshot(k.reg.resolve(alias), force=True)
                if snap.error:
                    message = snap.error
                report = k.restore(k.reg.resolve(alias), reconstruct=False)
                result = ('REFRESHED CONTEXT · ' + alias, self.restore_content(report))
            elif action == 'suspend':
                proc, snap, swap = k.suspend(alias)
                message = f'{proc.alias} → SWAP · SLEEPING. ' + ('Saved working set paged.' if swap else 'No saved image available.')
                if snap.error:
                    message += ' ' + snap.error
            elif action == 'kill':
                plan = k.kill_plan(alias)
                k.kill(plan, core=True)
                result = ('PROCESS EXITING · ' + alias, ui.resume_text(build_resume_report(alias, plan.snapshot.image)))
                message = f'Core saved: graveyard/{alias}.core · repository untouched.'
            elif action == 'irq':
                run = k.reg.running()
                item = InterruptQueue(k.cfg).capture(ui.safe(text), k.clock(), alias if alias is not None else run.alias if run else None)
                k.tel.record('irq', k.clock(), irq_id=item.id, project=item.current)
                message = f'IRQ #{item.id} queued. Current execution preserved.'
            elif action == 'ack':
                InterruptQueue(k.cfg).acknowledge(int(text))
                message = f'IRQ #{text} acknowledged.'
            view = monitor(k)
            irqs = InterruptQueue(k.cfg).read()
            self.post_message(KernelResult(view, irqs, result, message))
        except Exception as exc:
            # The UI boundary sanitizes even filesystem exceptions; no rich tracebacks with local paths.
            self.post_message(KernelResult(error=str(exc)))

    def restore_content(self, report):
        text = Text(f'Process image is {ui.fmt_age(report.age_s)} old.\n', style='dim')
        if report.error:
            text.append(ui.safe(report.error)+'\n', style='yellow')
        text.append(ui.resume_text(report.resume))
        return text

    def on_kernel_result(self, event):
        if event.error is not None:
            self.failed(event.error)
        else:
            self.finished(event.view, event.irqs, event.result, event.message)

    def failed(self, message):
        self.busy = False
        self.notice('Operation failed: ' + message)
        if self.fault_screen and self.fault_screen.is_mounted:
            self.fault_screen.show_error(message)
        self.finish_pending()

    def finished(self, view, irqs, result, message):
        selected = self.selected()
        previous_mode = self.view.diagnostics.mode if self.view else None
        self.view, self.irqs = view, irqs
        d = view.diagnostics
        if previous_mode == 'PANIC' and d.mode != 'PANIC' and not self.reduced_motion:
            self.rebuild_stage = 0
        table = self.query_one(DataTable)
        table.clear()
        self.aliases = [r['proc'].alias for r in view.rows]
        for row in view.rows:
            alias = row['proc'].alias
            table.add_row(scope.scheduler_line(view, row, alias == selected), key=alias)
        table.styles.height = max(2, min(6, len(view.rows)))
        if selected in self.aliases:
            table.move_cursor(row=self.aliases.index(selected))
        self.update_detail()
        self.update_alternate()
        self.render_scope()
        if d.mode != 'PANIC':
            self.panic_acknowledged = False
            if isinstance(self.screen, PanicScreen):
                self.screen.dismiss()
        elif isinstance(self.screen, PanicScreen):
            self.screen.update_counts(d)
        self.busy = False
        if message:
            self.notice(message)
            if '→ SWAP' in message:
                self.swap_effect = (message.split(' → SWAP',1)[0], 4)
        if result and not self.quit_pending:
            if len(result)>2 and result[2] is not None:
                if self.fault_screen and self.fault_screen.is_mounted:
                    self.fault_screen.load_report(result[2], result[1])
                else:
                    self.fault_screen = FaultScreen(result[0], result[1], result[2], self.reduced_motion)
                    self.push_screen(self.fault_screen)
            else:
                self.push_screen(ReportScreen(*result[:2]))
        elif d.mode == 'PANIC' and not self.panic_acknowledged and not isinstance(self.screen, ModalScreen):
            self.visual.tick('PANIC', self.reduced_motion)
            self.push_screen(PanicScreen(d))
        self.finish_pending()

    def finish_pending(self):
        if self.pending_irqs:
            alias, text = self.pending_irqs.pop(0)
            self.start('irq', alias=alias, text=text)
        elif self.quit_pending:
            self.exit()

    def on_data_table_row_highlighted(self, event):
        self.update_detail()

    def on_data_table_row_selected(self, event):
        if alias := self.selected():
            self.start('switch', alias)

    def update_detail(self):
        if not self.view:
            return
        selected = self.selected()
        table = self.query_one(DataTable)
        for row in self.view.rows:
            alias = row['proc'].alias
            if alias in self.aliases:
                table.update_cell(alias, 'scheduler', scope.scheduler_line(self.view, row, alias == selected))
        self.query_one('#core', Static).update(scope.core_text(self.view, selected, self.compact, max(30,min(self.size.width,self._terminal_width)-8)))
        if selected:
            wait = self.view.diagnostics.starved.get(selected)
            if wait and wait.starved:
                self.notice(f'STARVED / {selected} · READY {wait.waiting_hours:.0f}h · {wait.other_dispatches} other dispatches · {wait.execution_seconds:.0f}s run')
            row = next((r for r in self.view.rows if r['proc'].alias==selected),None)
            if row and row['state']==State.ZOMBIE:
                self.notice(f"ZOMBIE / {selected} · {row['inactive_days']:.0f}d idle · {row['residue']} unfinished references")

    @property
    def compact(self):
        return min(self.size.width,self._terminal_width) < 100 or min(self.size.height,self._terminal_height) < 32

    def render_scope(self):
        if not self.view:
            return
        view, d = self.view, self.view.diagnostics
        self.screen_stack[0].set_class(self.compact, 'compact')
        width = max(30, min(self.size.width,self._terminal_width)-8)
        motion = not self.reduced_motion and d.mode != 'NORMAL'
        phase = self.visual.phase
        self.query_one('#metrics', Static).update(Text(
            f'{d.mode} / {d.report.active} runnable · {d.report.pressure:.0%} allocation · '
            f'{d.report.switches} dispatches · {d.stale_images} stale',
            style=scope.RED if d.mode in ('THRASHING','PANIC') else scope.GRAPHITE))
        self.query_one('#dispatch', Static).update(scope.dispatch_text(view, width, phase, motion, self.compact))
        self.query_one('#frames', Static).update(scope.page_text(view, width, phase, motion, self.swap_effect, self.compact))
        self.query_one('#core', Static).update(scope.core_text(view, self.selected(), self.compact, width))
        self.query_one('#irq-rail', Static).update(scope.irq_text(getattr(self,'irqs',[]), phase, motion))
        if self.rebuild_stage is not None:
            if self.rebuild_stage < 1:
                self.query_one('#frames',Static).update(Text('02   REBUILDING SCOPE / allocation confirmed',style=scope.GRAPHITE))
            if self.rebuild_stage < 2:
                self.query_one('#core',Static).update(Text('03   REBUILDING SCOPE / execution state retained',style=scope.GRAPHITE))

    def update_alternate(self):
        if not self.view:
            return
        if self.view_index == 1:
            content = scope.page_text(self.view, max(40,self.size.width-14), migration=self.swap_effect)
        else:
            content = Text('INTERRUPT QUEUE\nA acknowledges the oldest pending IRQ. No project is created automatically.\n\n', style=scope.BONE)
            for item in self.irqs:
                if not item.acknowledged:
                    content.append(ui.safe(f'#{item.id}  {item.text}\n  route: {item.route.kind} {item.route.project}\n'), style=scope.BONE)
            if not any(not i.acknowledged for i in self.irqs):
                content.append('No pending interrupts.\n')
        self.query_one('#alternate', Static).update(content)

    def animate_pressure(self):
        if not self.view:
            return
        d = self.view.diagnostics
        if self.rebuild_stage is not None:
            self.rebuild_stage += 1
            if self.rebuild_stage >= 3: self.rebuild_stage = None
        level = self.visual.tick(d.mode, self.reduced_motion)
        self.render_scope()
        scar = ''
        if level > {'NORMAL':0,'PRESSURE':1,'THRASHING':2,'PANIC':3}[d.mode]:
            scar = 'RECONSTITUTING FRAME · residual dispatch echo settling'
        elif d.stale_images and d.mode != 'NORMAL' and (self.reduced_motion or self.visual.phase%2==0):
            stale = [r['proc'].alias for r in self.view.rows if r['proc'].state in (State.READY,State.RUNNING)
                     and (not self.view.images[r['proc'].alias] or self.view.now-self.view.images[r['proc'].alias].image.meta.created_at >= self.kernel.cfg.stale_hours*3600)]
            scar = 'STALE IMAGE TRACE / ' + ' · '.join(stale[:3])
        if 'context reconstruction' in d.report.fired and not self.reduced_motion and self.visual.phase%2:
            restored = [e.get('to_project') for e in self.view.events if e.get('type')=='switch' and e.get('reconstructed')
                        and self.view.now-d.report.window_hours*3600 <= e['ts'] <= self.view.now]
            scar = 'RESTORE ECHO / ' + ' ← '.join(restored[-3:])
        if self.swap_effect:
            alias,ticks = self.swap_effect
            scar = f'PAGE OUT / {alias} crossed the swap horizon · saved context retained'
            self.swap_effect = (alias,ticks-1) if ticks>1 and not self.reduced_motion else None
            if self.view_index==1: self.update_alternate()
        self.query_one('#echo', Static).update(Text(ui.safe(scar),style=scope.GRAPHITE))

    def action_view(self):
        if isinstance(self.screen, ModalScreen):
            self.screen.focus_next()
            return
        self.view_index = (self.view_index+1) % 3
        self.query_one('#body').display = self.view_index == 0
        self.query_one('#view').display = self.view_index != 0
        self.update_alternate()
        if self.view_index == 0:
            self.query_one(DataTable).focus(scroll_visible=False)
        else:
            self.query_one('#view').focus()

    def action_help(self):
        content = Text('↑↓ SELECT   ENTER DISPATCH\nC READ CONTEXT   R RECONSTRUCT\nI CAPTURE IRQ   S PAGE OUT   W WAKE\nK TERMINATE + CORE   TAB SCOPE / PAGES / IRQ\nA ACK OLDEST IRQ (IRQ view)   M REDUCED MOTION\nQ EXIT   ESC RETURN\n\nTrace: fixed time cells. × means multiple dispatches.\n↑ IRQ   ! reconstruction   ◆ both\nScar: actual dispatches from 48–24 hours ago.\n16 page frames = one scheduler allocation unit, not RAM.\nWSS ctx units estimate saved-image characters / 4.\nCyan marks execution; amber marks interrupts; red marks contention.\n\nIn the synthetic demo, N advances the scenario.', style=scope.BONE)
        self.push_screen(ReportScreen('KERNEL KEYMAP', content))

    def action_motion(self):
        self.reduced_motion = not self.reduced_motion
        self.notice('Reduced motion ON' if self.reduced_motion else 'Reduced motion OFF')

    def action_context(self):
        if alias := self.selected():
            self.start('context', alias)

    def action_refresh_context(self):
        if alias := self.selected():
            self.start('rescan', alias)

    def action_suspend(self):
        if alias := self.selected():
            self.start('suspend', alias)

    def action_wake(self):
        if alias := self.selected():
            self.start('wake', alias)

    def action_irq(self):
        self.push_screen(AskScreen('INTERRUPT REQUEST · preserve current execution'),
                         lambda value: self.start('irq', text=value) if value else None)

    def action_ack(self):
        if self.view_index == 2 and hasattr(self, 'irqs'):
            item = next((i for i in self.irqs if not i.acknowledged), None)
            if item:
                self.start('ack', text=str(item.id))

    def action_terminate(self):
        if alias := self.selected():
            self.push_screen(AskScreen(f'Terminate {alias} and preserve a core dump? Repository stays untouched.', confirm=True),
                             lambda value: self.start('kill', alias) if value else None)

    def action_quit_safely(self):
        if self.busy:
            self.quit_pending = True
            self.notice('Finishing the current durable operation, then exiting…')
        else:
            self.exit()
