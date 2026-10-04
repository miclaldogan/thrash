import pytest
from thrash import scope
from thrash.demo import DemoScenario
from thrash.diagnostics import diagnose
from thrash.tui import KernelApp, FaultScreen, PanicScreen, monitor
from thrash.resume import build_resume_report
from thrash.registry import State
from textual.widgets import Input, Footer, DataTable


def test_trace_boundaries_collision_and_punctures():
    events = [{'type':'switch','ts':1,'to_project':'alpha'},
              {'type':'switch','ts':2,'to_project':'beta','reconstructed':True},
              {'type':'irq','ts':2}, {'type':'switch','ts':20,'to_project':'alpha'},
              {'type':'switch','ts':101,'to_project':'beta'}]
    t=scope.trace(events,0,100,10,{'alpha':'A','beta':'B'})
    assert t.line == '×─A───────'
    assert t.dispatches==3 and t.collisions==1
    assert t.marks[0]=='◆' and t.irqs==t.faults==1
    assert scope.trace([],0,100,10,{}).line == '·'*10


def test_scar_requires_actual_history(kernel3,clock):
    k=kernel3
    text=scope.dispatch_text(monitor(k)).plain
    assert 'no recorded dispatches' in text
    k.switch('alpha')
    clock.advance(26*3600)
    view=monitor(k)
    t=scope.trace(view.events,clock()-48*3600,clock()-24*3600,50,scope.tokens(view))
    assert t.dispatches==1 and 'A' in t.line
    assert 'no recorded dispatches' not in scope.dispatch_text(view).plain


def test_allocations_cross_horizon_only_on_state_change(kernel3):
    k=kernel3
    before=monitor(k)
    assert scope.allocations(before)==(['alpha','beta','gamma'],[],[])
    assert '3/4 scheduler units' in scope.page_text(before).plain
    k.suspend('beta')
    after=monitor(k)
    resident,swap,_=scope.allocations(after)
    assert resident==['alpha','gamma'] and swap==['beta']
    text=scope.page_text(after).plain
    top,bottom=text.split('SWAP HORIZON')
    assert 'BBBB' not in top and 'BBBB' in bottom
    assert 'NOT RAM' in text
    k.wake('beta')
    assert scope.allocations(monitor(k))[1]==[]


def test_cinematic_is_a_presentation_of_canonical_report(kernel3):
    cf=kernel3.load_context(kernel3.reg.resolve('alpha'))
    report=build_resume_report('alpha',cf.image)
    report.decisions[0].reason='Avoid repeat work'
    report.next_action='[type=CNAME] inspect /home/person/private/file'
    before=report.model_dump_json()
    assert 'PROGRAM COUNTER' in scope.restoration_text(report,0).plain
    assert 'REGISTERS' not in scope.restoration_text(report,0).plain
    full=scope.restoration_text(report,4).plain
    for section in ['YOU WERE HERE','YOU DECIDED','YOU STOPPED AT','WHILE YOU WERE GONE','NEXT EXECUTION','FAULT RESOLVED']:
        assert section in full
    assert 'Avoid repeat work' in full and '[type=CNAME]' in full
    assert '/home/person' not in full
    assert report.model_dump_json()==before
    assert 'FAULT RESOLVED' not in scope.restoration_text(build_resume_report('empty',None),4).plain


async def settled(app,pilot):
    for _ in range(150):
        await pilot.pause(.02)
        if app.view and not app.busy:return
    raise AssertionError('Worker did not finish')


@pytest.mark.asyncio
async def test_scope_cursor_and_no_default_footer(kernel3):
    app=KernelApp(kernel3,reduced_motion=True)
    async with app.run_test(size=(80,24)) as pilot:
        await settled(app,pilot)
        assert not app.query(Footer)
        assert app.query_one(DataTable).show_header is False
        await pilot.press('down')
        assert app.selected()=='beta'
        await pilot.press('enter')
        await settled(app,pilot)
        assert isinstance(app.screen,FaultScreen)
        assert app.screen.stage==4 and kernel3.reg.running().alias=='beta'
        await pilot.press('enter')
        assert not isinstance(app.screen,FaultScreen)


@pytest.mark.asyncio
async def test_sparse_panic_actions_and_recovery():
    with DemoScenario() as demo:
        for _ in range(8):demo.advance()
        app=KernelApp(demo.kernel,reduced_motion=True,demo=True)
        async with app.run_test(size=(100,35)) as pilot:
            await settled(app,pilot)
            assert isinstance(app.screen,PanicScreen)
            assert app.screen.diagnostics.pending_irqs==9
            await pilot.press('s')
            alias=app.screen.query_one(Input).value
            await pilot.press('enter')
            await settled(app,pilot)
            assert demo.kernel.reg.resolve(alias).state==State.SLEEPING
            assert not isinstance(app.screen,PanicScreen)
            assert app.view.diagnostics.mode!='PANIC'
            assert app.swap_effect is None or app.swap_effect[0]==alias


def test_semantic_text_palette_is_legible():
    def luminance(h):
        channels=[int(h[i:i+2],16)/255 for i in (1,3,5)]
        c=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in channels]
        return sum(v*w for v,w in zip(c,(.2126,.7152,.0722)))
    bg=luminance(scope.BACKGROUND)
    for color in (scope.BONE,scope.GRAPHITE,scope.CYAN,scope.AMBER,scope.RUST,scope.RED):
        assert (luminance(color)+.05)/(bg+.05)>=4.5


@pytest.mark.asyncio
async def test_resize_rebins_trace_and_panic_irq_view(kernel3):
    from textual.widgets import Static
    app=KernelApp(kernel3,reduced_motion=True)
    async with app.run_test(size=(120,44)) as pilot:
        await settled(app,pilot)
        await pilot.resize_terminal(80,24)
        await pilot.pause(.1)
        app.render_scope()
        plain=app.query_one('#dispatch',Static).render().plain
        assert max(map(len,plain.splitlines()))<=72
        assert app.compact


@pytest.mark.asyncio
async def test_panic_irq_recovery_control():
    with DemoScenario() as demo:
        for _ in range(8):demo.advance()
        app=KernelApp(demo.kernel,reduced_motion=True,demo=True)
        async with app.run_test(size=(100,35)) as pilot:
            await settled(app,pilot)
            await pilot.press('i')
            await pilot.pause(.05)
            assert app.view_index==2
            assert not isinstance(app.screen,PanicScreen)
            await pilot.press('a')
            await settled(app,pilot)
            assert app.view.diagnostics.pending_irqs==8
            assert not isinstance(app.screen,PanicScreen)


def test_visual_effects_require_the_corresponding_signal(kernel3,clock):
    k=kernel3
    v=monitor(k)
    assert 'ECHO' not in scope.dispatch_text(v,motion=True).plain
    assert scope.page_text(v,phase=0,motion=True).plain==scope.page_text(v,phase=1,motion=True).plain
    k.cfg.max_active=3
    v=monitor(k)
    assert scope.page_text(v,phase=0,motion=True).plain!=scope.page_text(v,phase=1,motion=True).plain
    assert 'ECHO' not in scope.dispatch_text(v,motion=True).plain
    for i in range(6):
        k.switch('alpha' if i%2==0 else 'beta')
        clock.advance(1)
    v=monitor(k)
    assert 'ECHO' in scope.dispatch_text(v,motion=True).plain
    assert 'ECHO' not in scope.dispatch_text(v,motion=False).plain


@pytest.mark.asyncio
async def test_unavailable_fault_never_claims_resolution(kernel3):
    from textual.widgets import Static
    from thrash.ollama_client import ModelError
    k=kernel3
    k.image_path(k.reg.resolve('alpha')).unlink()
    def unavailable(*args,**kwargs):
        raise ModelError('Local model offline /home/person/private/file')
    k._extractor=unavailable
    app=KernelApp(k,reduced_motion=True)
    async with app.run_test(size=(100,35)) as pilot:
        await settled(app,pilot)
        await pilot.press('enter')
        await settled(app,pilot)
        assert isinstance(app.screen,FaultScreen)
        text=app.screen.query_one('#fault-stream',Static).render().plain
        assert 'offline' in text
        assert '/home/person' not in text
        assert 'FAULT RESOLVED' not in text
