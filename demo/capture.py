"""Render the checked-in synthetic offline demo transcript as terminal SVGs.

No real-project input is accepted. Run from any directory with THRASH's dependencies.
"""
from io import StringIO
from pathlib import Path

from rich.console import Console
from rich.text import Text

from thrash.privacy import public_text


def capture() -> None:
    examples = Path(__file__).resolve().parent.parent / "docs/examples"
    transcript = (examples / "offline-demo-run.txt").read_text()
    if public_text(transcript) != transcript:
        raise ValueError("demo transcript contains text requiring privacy filtering")
    scene_b = transcript.split("DEMO B: page fault on a stale image", 1)[1]
    page_fault = "$ thrash switch game-alpha\n" + scene_b.split("$ thrash switch game-alpha\n", 1)[1].split("$ thrash status", 1)[0]
    scene_c = transcript.split("DEMO C: thrashing", 1)[1]
    top = "$ thrash top\n" + scene_c.split("$ thrash top\n", 1)[1].split("================ DEMO D", 1)[0]
    for name, title, output in (("page-fault.svg", "THRASH · PAGE FAULT", page_fault),
                                ("thrashing.svg", "THRASH · HUMAN KERNEL", top)):
        console = Console(record=True, width=90, file=StringIO())
        console.print(Text(output.strip()))
        console.save_svg(str(examples / name), title=title)


if __name__ == "__main__":
    capture()
