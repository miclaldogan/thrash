"""A terminal client of the kernel. All mutation and repository I/O is serialized off-UI."""
from __future__ import annotations

import os
from dataclasses import dataclass
from rich.text import Text
from textual import work
from textual.message import Message
from textual.binding import Binding
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll, Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Static, Input, Button, Label

from . import ui
from .diagnostics import diagnose
from .interrupts import InterruptQueue
from .registry import State
from .resume import build_resume_report


@dataclass
class Monitor:
    rows: list
    diagnostics: object
    events: list
    images: dict
    now: float


def monitor(kernel):
    kernel.reg.load()
    for p in kernel.reg.all(include_terminated=True):
        ui.remember_project(p)
    rows, _, _ = kernel.table(include_terminated=True)
    return Monitor(rows, diagnose(kernel), kernel.tel.read(),
                   {r['proc'].alias: kernel.load_context(r['proc']) for r in rows}, kernel.clock())


def memory_text(view):
    text = Text('WORKING MEMORY MAP\nEstimated context units = serialized characters / 4, not RAM.\n\n', style='cyan')
    for row in view.rows:
        p = row['proc']
        if p.state == State.TERMINATED:
            location = 'CORE'
        elif p.state == State.SLEEPING:
            location = 'SWAP'
        else:
            location = 'RESIDENT'
        units = row['ctx'] or 0
        # Bar scale is fixed, labelled, and derived only from saved image units.
        text.append(f'{p.alias:18} {location:8} {units:6} units  ', style='white')
        text.append('█' * min(32, (units+99)//100), style='blue' if location == 'SWAP' else 'cyan')
        text.append('\n')
    text.append('\nEach block ≈ 100 context units; bars cap at 3,200.\n', style='dim')
    return text


class ReportScreen(ModalScreen):
    BINDINGS = [('escape', 'close', 'Close'), ('q', 'close', 'Close')]
    def __init__(self, title, content):
        super().__init__()
        self.heading, self.content = title, content

    def compose(self) -> ComposeResult:
        with Vertical(id='report-dialog'):
            yield Static(Text(self.heading, style='bold cyan'))
            with VerticalScroll():
                yield Static(self.content, markup=False)
            yield Button('Return to kernel [Esc]', id='close')

    def action_close(self):
        self.dismiss()

    def on_button_pressed(self, event):
        self.dismiss()


class AskScreen(ModalScreen[str | None]):
    BINDINGS = [('escape', 'cancel', 'Cancel')]
    def __init__(self, title, confirm=False):
        super().__init__()
        self.heading, self.confirm = title, confirm

    def compose(self) -> ComposeResult:
        with Vertical(id='ask-dialog'):
            yield Label(Text(self.heading))
            if not self.confirm:
                yield Input(placeholder='Capture the thought; keep your current execution.', id='answer')
            with Horizontal():
                yield Button('Confirm' if self.confirm else 'Queue interrupt', id='accept', variant='primary')
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


class KernelResult(Message):
    def __init__(self, view=None, irqs=None, result=None, message=None, error=None):
        super().__init__()
        self.view, self.irqs, self.result, self.message, self.error = view, irqs, result, message, error


class KernelApp(App):
    TITLE = 'THRASH · HUMAN KERNEL'
    CSS = '''
    Screen { background: #090f14; color: #d0dce0; }
    #identity { height: 3; padding: 0 1; background: #14212b; color: #75dfda; }
    #metrics { height: 4; padding: 0 1; border-bottom: solid #28404d; }
    #body { height: 1fr; }
    #processes { width: 62%; height: 1fr; border: solid #28404d; }
    #right { width: 38%; padding: 0 1; }
    #detail { height: auto; }
    #history { height: auto; margin-top: 1; }
    #view { height: 1fr; padding: 1 2; display: none; }
    #echo { height: 2; color: #be9470; padding: 0 1; }
    #notice { height: 2; background: #14212b; padding: 0 1; }
    .pressure #metrics { border-bottom: solid #d0ab66; }
    .thrashing #metrics { border-bottom: heavy #e79a58; }
    .panic #metrics { border-bottom: heavy #f06b71; color: #f06b71; }
    ModalScreen { align: center middle; background: #000000 65%; }
    #report-dialog { width: 90%; height: 90%; padding: 1 2; background: #101d27; border: solid #75dfda; }
    #report-dialog VerticalScroll { height: 1fr; }
    #ask-dialog { width: 76; height: auto; padding: 1 2; background: #101d27; border: solid #75dfda; }
    #ask-dialog Label { height: auto; margin-bottom: 1; }
    #ask-dialog Horizontal { height: 3; margin-top: 1; }
    Button { margin-right: 1; }
    '''
    BINDINGS = [
        ('q', 'quit_safely', 'Quit'), ('i', 'irq', 'IRQ'), ('s', 'suspend', 'Suspend'),
        ('w', 'wake', 'Wake'), ('k', 'terminate', 'Core dump'), ('c', 'context', 'Context'),
        Binding('tab', 'view', 'View', priority=True), ('a', 'ack', 'Ack IRQ'), ('r', 'refresh_context', 'Rescan'),
        ('m', 'motion', 'Motion'),
    ]

    def __init__(self, kernel, reduced_motion=None, demo=False):
        super().__init__()
        self.kernel = kernel
        self.reduced_motion = bool(os.environ.get('THRASH_REDUCED_MOTION')) if reduced_motion is None else reduced_motion
        self.synthetic = demo
        self.busy = False
        self.view = None
        self.view_index = 0
        self.phase = 0
        self.quit_pending = False
        self.aliases = []

    def compose(self) -> ComposeResult:
        yield Static('THRASH HUMAN KERNEL\n1 human. 1 core. Too many processes.', id='identity')
        yield Static('Reading saved scheduler state…', id='metrics', markup=False)
        with Horizontal(id='body'):
            yield DataTable(id='processes', cursor_type='row', zebra_stripes=True)
            with VerticalScroll(id='right'):
                yield Static('', id='detail', markup=False)
                yield Static('', id='history', markup=False)
        with VerticalScroll(id='view'):
            yield Static('', id='alternate', markup=False)
        yield Static('', id='echo', markup=False)
        yield Static('Enter restore · ↑↓ select · C inspect · Tab memory / interrupts', id='notice', markup=False)
        yield Footer()

    def on_mount(self):
        self.query_one(DataTable).add_columns('PID', 'ALIAS', 'STATE', 'WSS≈', 'FAULTS', 'AGE')
        self.query_one(DataTable).focus()
        if self.synthetic:
            self.query_one('#identity', Static).update('THRASH · SYNTHETIC DEMO — simulated history & model fixture\n1 human. 1 core. Too many processes.')
        self.refresh_monitor()
        self.set_interval(3, self.refresh_monitor)
        self.set_interval(.8, self.animate_pressure)

    def selected(self):
        table = self.query_one(DataTable)
        return self.aliases[table.cursor_row] if self.aliases and table.cursor_row < len(self.aliases) else None

    def notice(self, message):
        self.query_one('#notice', Static).update(Text(ui.safe(message)))

    def refresh_monitor(self):
        if not self.busy and not isinstance(self.screen, ModalScreen):
            self.start('refresh')

    def start(self, action, alias=None, text=None):
        if self.busy:
            self.notice('Kernel operation in progress; wait for its durable result.')
            return
        self.busy = True
        if action != 'refresh':
            labels = {'switch':'PAGE FAULT · saving current context and restoring selected working set…',
                      'context':'Reading saved context and checking repository drift…',
                      'rescan':'Rebuilding context with local Gemma…',
                      'suspend':'Serializing working set to swap…', 'wake':'Loading saved working set…',
                      'kill':'Recovering final state and writing core dump…', 'irq':'Queuing interrupt…',
                      'ack':'Acknowledging interrupt…'}
            self.notice(labels[action])
        self.perform(action, alias, text)

    @work(thread=True, exit_on_error=False)
    def perform(self, action, alias, text):
        result = None
        message = None
        try:
            k = self.kernel
            k.reg.load()
            if action == 'switch':
                switched = k.switch(alias)
                report = switched.restore
                result = ('PAGE FAULT · ' + alias, self.restore_content(report))
                message = 'Working set restored. Read NEXT INSTRUCTION before dispatching another process.'
                if switched.out and switched.out.error:
                    message = 'Outgoing snapshot unavailable; previous image retained. ' + switched.out.error
            elif action in ('context', 'wake'):
                report = k.wake(alias) if action == 'wake' else k.restore(k.reg.resolve(alias, True), reconstruct=False)
                result = ('PAGE FAULT · ' + alias if action == 'wake' else 'SAVED CONTEXT · ' + alias,
                          self.restore_content(report))
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
                item = InterruptQueue(k.cfg).capture(ui.safe(text), k.clock(), run.alias if run else None)
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
        if self.quit_pending:
            self.exit()

    def finished(self, view, irqs, result, message):
        selected = self.selected()
        self.view, self.irqs = view, irqs
        d = view.diagnostics
        self.screen.remove_class('pressure', 'thrashing', 'panic')
        self.screen.add_class(d.mode.lower())
        self.query_one('#metrics', Static).update(Text(
            f'STATE: {d.mode}   ACTIVE {d.report.active}/{self.kernel.cfg.max_active}   '
            f'PRESSURE {d.report.pressure:.0%}   SWITCHES {d.report.switches}/{self.kernel.cfg.window_hours:g}h\n'
            f'IRQ {d.pending_irqs}   STALE {d.stale_images}   SIGNALS: {", ".join(d.reasons) or "none"}\n'
            + ('KERNEL PANIC · suspend READY work [S], review IRQs [Tab], or continue deliberately.' if d.mode == 'PANIC'
               else 'OUT OF MIND · suspend a candidate before admitting work, or queue an IRQ.' if d.out_of_mind
               else 'Only THRASH sessions are measured. WSS is an estimate, not human memory capacity.')))
        table = self.query_one(DataTable)
        table.clear()
        self.aliases = []
        for row in view.rows:
            p = row['proc']
            self.aliases.append(p.alias)
            cf = view.images[p.alias]
            faults = sum(e.get('type') == 'switch' and e.get('to_project') == p.alias and e.get('reconstructed', False)
                         for e in view.events)
            state = 'STARVED' if d.starved.get(p.alias) and d.starved[p.alias].starved else row['state'].value
            table.add_row(p.pid_str, Text(p.alias), state, str(row['ctx'] or '—'), str(faults),
                          ui.fmt_age(view.now-cf.image.meta.created_at) if cf else 'missing', key=p.alias)
        if selected in self.aliases:
            table.move_cursor(row=self.aliases.index(selected))
        self.update_detail()
        self.update_alternate()
        history = Text('DISPATCH HISTORY\n', style='bold cyan')
        for e in [e for e in view.events if e.get('type') == 'switch'][-6:]:
            history.append(ui.safe(f"{e.get('from_project') or 'idle'} → {e.get('to_project')}\n"), style='dim')
        self.query_one('#history', Static).update(history)
        self.busy = False
        if message:
            self.notice(message)
        if self.quit_pending:
            self.exit()
        elif result:
            self.push_screen(ReportScreen(*result))

    def on_data_table_row_highlighted(self, event):
        self.update_detail()

    def on_data_table_row_selected(self, event):
        if alias := self.selected():
            self.start('switch', alias)

    def update_detail(self):
        if not self.view or not (alias := self.selected()):
            return
        row = next(r for r in self.view.rows if r['proc'].alias == alias)
        cf = self.view.images[alias]
        text = Text(alias+'\n', style='bold cyan')
        if cf:
            text.append('\nNEXT INSTRUCTION\n', style='bold')
            text.append(ui.safe(cf.image.next_action or cf.image.program_counter.task)+'\n', style='white')
            text.append(f'\n{len(cf.image.completed)} completed · {len(cf.image.decisions)} decisions\n'
                        f'{len(cf.image.unresolved)} unresolved · {len(cf.image.blockers)} blockers\n', style='dim')
        else:
            text.append('No saved context. R rebuilds with local Gemma.\n')
        wait = self.view.diagnostics.starved.get(alias)
        if wait and wait.starved:
            text.append(f'\nSTARVATION\nREADY {wait.waiting_hours:.0f}h; {wait.other_dispatches} other dispatches; '
                        f'{wait.execution_seconds:.0f}s execution.\n', style='yellow')
        if row['state'] == State.ZOMBIE:
            text.append(f"\nZOMBIE\n{row['inactive_days']:.0f} days idle; {row['residue']} saved unfinished references.\n"
                        'No activity and unfinished residue. Close deliberately or resume.\n', style='red')
        text.append('\nC: full restoration report\nR: refresh semantic evidence\n', style='dim')
        self.query_one('#detail', Static).update(text)

    def update_alternate(self):
        if not self.view:
            return
        if self.view_index == 1:
            content = memory_text(self.view)
        else:
            content = Text('INTERRUPT QUEUE\nA acknowledges the oldest pending IRQ. No project is created automatically.\n\n', style='cyan')
            for item in self.irqs:
                if not item.acknowledged:
                    content.append(ui.safe(f'#{item.id}  {item.text}\n  route: {item.route.kind} {item.route.project}\n'), style='white')
            if not any(not i.acknowledged for i in self.irqs):
                content.append('No pending interrupts.\n')
        self.query_one('#alternate', Static).update(content)

    def animate_pressure(self):
        if not self.view:
            return
        self.phase += 1
        mode = self.view.diagnostics.mode
        history = [e.get('to_project', '') for e in self.view.events if e.get('type') == 'switch'][-4:]
        if mode in ('THRASHING', 'PANIC') and history:
            # Only actual recent dispatches; separate from the stable metrics/table.
            offset = 0 if self.reduced_motion else self.phase % (4 if mode == 'PANIC' else 2)
            line = 'DISPATCH ECHO (visual)  ' + '   '.join(history)
            text = Text(' '*offset + ui.safe(line), style='red' if mode == 'PANIC' else 'yellow')
        else:
            text = Text('Memory stable.' if mode == 'NORMAL' else 'Working-set pressure rising.', style='dim')
        self.query_one('#echo', Static).update(text)

    def action_view(self):
        if isinstance(self.screen, ModalScreen):
            self.screen.focus_next()
            return
        self.view_index = (self.view_index+1) % 3
        self.query_one('#body').display = self.view_index == 0
        self.query_one('#view').display = self.view_index != 0
        self.update_alternate()
        if self.view_index == 0:
            self.query_one(DataTable).focus()
        else:
            self.query_one('#view').focus()

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
