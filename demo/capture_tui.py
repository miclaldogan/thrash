"""Reproduce public-safe SVGs from the isolated synthetic demo (no Ollama needed)."""
import asyncio
import os
from pathlib import Path

# Screenshots have an explicit color theme, independent of the invoking shell.
os.environ.pop('NO_COLOR', None)
from rich.console import Console
from thrash.demo import DemoScenario
from thrash.tui import KernelApp


async def settle(app, pilot):
    for _ in range(200):
        await pilot.pause(.025)
        if not app.busy and app.view:
            return
    raise RuntimeError('Kernel worker did not complete')


async def capture(destination):
    destination.mkdir(parents=True, exist_ok=True)
    with DemoScenario() as demo:
        demo.advance()
        app = KernelApp(demo.kernel, demo=True, reduced_motion=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(app, pilot)
            (destination/'kernel-normal.svg').write_text(app.export_screenshot())
            result, _ = demo.advance()
            console = Console(record=True, width=100)
            with console.capture():
                console.print('SYNTHETIC FIXTURE · 71-hour age simulated · no model call')
                console.print(result[0])
                console.print(result[1])
            console.save_svg(str(destination/'resume-fixture.svg'), title='THRASH · PAGE FAULT', clear=False)
            console.save_text(str(destination/'resume-fixture.txt'))
            for _ in range(6):
                demo.advance()
            app.refresh_monitor()
            await settle(app, pilot)
            app.animate_pressure()
            await pilot.pause(.1)
            (destination/'kernel-panic.svg').write_text(app.export_screenshot())
            demo.advance()
            app.refresh_monitor()
            await settle(app, pilot)
            app.animate_pressure()
            await pilot.pause(.1)
            (destination/'kernel-recovery.svg').write_text(app.export_screenshot())
            await pilot.press('tab')
            (destination/'kernel-memory.svg').write_text(app.export_screenshot())


if __name__ == '__main__':
    asyncio.run(capture(Path(__file__).resolve().parents[1]/'docs'/'examples'))
