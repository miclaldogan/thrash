# Demo workspace

Everything here is synthetic. No real project names.

- `build_demo.py` builds five tiny Git repos (`game-alpha`, `research-beta`, `robot-lab`, `paper-crane`, `old-agent`) with backdated commits in `demo/workspace/`, and prepares an isolated THRASH data directory `demo/.thrash-home/`. Both are git-ignored.
- `age_image.py <alias> <hours>` is **demo tooling**: it time-shifts a saved image so a stale page fault can be shown without waiting. THRASH itself never does this.
- `run_demo.sh` runs demos A-E end to end. Set `THRASH=/path/to/thrash` if it is not on `PATH`.

| Demo | What it shows |
|---|---|
| A | normal switch: save, page out, restore |
| B | page fault on a 71-hour-old image, with drift evidence |
| C | rapid switching until `thrash top` reports THRASHING |
| D | `old-agent`: 41 days idle with unresolved TODOs shows as ZOMBIE |
| E | `kill` writes a core dump; `resurrect` restores it and reports drift |

See [`../docs/demo-script.md`](../docs/demo-script.md) for the narrated 3-minute version.
