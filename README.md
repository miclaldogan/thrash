# THRASH

**My laptop has a scheduler. My friend didn't.**

## The human bug

My friend has too many tabs open.

Not browser tabs. Mental ones.

One contains music. One contains a math problem. One contains a game. Three contain research ideas. There is probably a half-written article somewhere, three repositories are open, and one project hasn't been touched for ten days but she still thinks about it every morning.

The obvious solution was a task manager.

She already had task managers. The task managers became additional tabs.

So I stopped treating her like an unorganized human and started treating her like a badly scheduled computer.

Her problem isn't laziness and it isn't output. She produces a lot. Her problem is the *switch*: every time she jumps projects she has to rebuild what she was doing, why, what she'd decided, what was unresolved, which files mattered, and the very next step. Eventually she spends more time recovering context than working.

## What thrashing means

An operating system **thrashes** when it spends more time moving memory in and out than doing useful work. The CPU is busy, nothing gets finished.

A computer avoids the worst of it by saving the full state of a process before switching away, and restoring it exactly when it comes back. Humans usually don't. **THRASH does it for us.**

> THRASH does not tell you to focus. It shows you what context switching is actually costing you.

THRASH is a software productivity experiment inspired by OS concepts. It is **not** a medical or psychological tool and makes no claims about attention, ADHD, or anyone's brain.

## The idea

Projects are processes. THRASH keeps a local process table, and when you leave a project it serializes a **process image**, the minimum context needed to resume it:

```yaml
project: game-alpha
program_counter: {task: "rig jaw", confidence: 0.9}   # confidence is model-reported
registers: {engine: undecided, facial_hair: finished}
stack: [rig jaw]
open_handles: [TODO.md, notes/rig.md, docs/character.md]
decisions:
  - {text: "do not begin engine integration before the rig test", source: notes/rig.md}
unresolved: [hair physics]
next_action: "rig the jaw"
```

When you come back it restores that image (a **page fault**) and checks it against the repository as it is now (**drift**).

## Demo

All output below is real, from the synthetic workspace in [`demo/`](demo/) (full run: [`docs/examples/demo-run.txt`](docs/examples/demo-run.txt)).

```text
$ thrash switch game-alpha

CONTEXT SWITCH

FROM  robot-lab
TO    game-alpha

PAGE FAULT

Restoring process 001...

PC  -> rig jaw  (conf 0.80)
R0  -> facial_hair: finished

STACK RESTORED  (1 frames)

Process image is 71 hours old.

POSSIBLE DRIFT (MODERATE)  since suspend:
+ 1 new commit
    engine: start integration scaffold
+ 1 relevant file changed
    engine/integration.gd
~ ASSUMPTION MAY BE STALE: engine: undecided
    evidence: engine/integration.gd
    evidence: commit: engine: start integration scaffold

NEXT INSTRUCTION:
rig jaw
```

```text
$ thrash top
THRASH HUMAN KERNEL 0.1
1 HUMAN CORE

PID  PROCESS        STATE    LOAD  CTX~
001  game-alpha     RUNNING   14%  214u
002  research-beta  READY     68%  224u
003  robot-lab      READY     10%  200u
004  paper-crane    READY      8%  155u
005  old-agent      ZOMBIE     0%  220u

context switches today: 20
active processes:       5
working-set pressure:   125% (active/limit, est.)  HIGH

STATE: THRASHING

THRASHING DETECTED

20 project switches in 4 hours
median uninterrupted session: 0 sec
5 active working sets
signals: switch rate, short sessions, working-set pressure

The system is spending too much time restoring context.
```

Reproduce everything: `demo/run_demo.sh` (needs Ollama + a Gemma model). The demo uses an isolated `THRASH_HOME`, so your real state is untouched. The 71-hour age is simulated with `demo/age_image.py`, which is labeled demo tooling; THRASH never fakes time.

## Processes

| State | Meaning | How it is decided |
|---|---|---|
| `RUNNING` | what you are working on | stored; the registry enforces **at most one** |
| `READY` | active, waiting for attention | stored |
| `SLEEPING` | deliberately suspended, context serialized | stored (`thrash suspend`) |
| `ZOMBIE` | idle but still haunted | **derived**, never stored: no repo activity for `THRASH_ZOMBIE_DAYS` (14) **and** residue (unresolved items, blockers, or TODO/FIXME/open-checkbox lines) |
| `TERMINATED` | closed on purpose | stored; optional core dump |

Killing a process only changes THRASH's state. Your repository is never touched.

## Context switching

`thrash switch <project>` does, in order:

1. inspect the leaving project's repository (commits, dirty files, notes, TODOs),
2. build or update its process image (skipped if the repository is byte-for-byte unchanged since the last image: *working set unchanged: image reused*),
3. page it out to `swap/<alias>.ctx`,
4. record the switch and move it to `READY`,
5. restore the destination image (**PAGE FAULT**),
6. compare it with the repository now and report **drift**,
7. mark the destination `RUNNING`.

If the destination has never been scanned, the page fault reconstructs its context from the repository, and that counts as a *reconstruction* in the thrashing heuristic.

Drift is deterministic. It lists commits and files changed since the snapshot, and flags a saved *open* assumption ("undecided", "unresolved", "not started"...) as `ASSUMPTION MAY BE STALE` only when new commit subjects or changed paths share vocabulary with it, always with the evidence attached. It never claims a contradiction.

## What Gemma actually does

Gemma, through Ollama, does one job: **turn repository text into a structured process image** (program counter, registers, stack, decisions, unresolved questions, blockers, next action, last useful state, evidence).

- The reply is constrained with a JSON schema, then validated by Pydantic. Malformed output gets **one** repair attempt, then is rejected; nothing invalid is ever stored, and the previous image survives.
- Paths the model cites that do not exist (or are ignored) are dropped and counted. A decision without a real source is marked *inferred*.
- The prompt says: don't invent facts, prefer evidence, separate explicit decisions from inference, state uncertainty, cite files from the file list only.

Gemma is **not** responsible for timestamps, switch counts, pressure, file discovery, or Git diffs. All of that is plain deterministic code.

## Why local/open-weight AI

THRASH reads the contents of unreleased, private projects. That context should not leave the machine. It runs on a local Gemma through Ollama: no API keys, no cloud, no telemetry. In a test run, every `connect()` made during a real switch targeted `127.0.0.1:11434` / `::1:11434` and nothing else. If Ollama is down, deterministic commands (`top`, `ps`, `status`, state changes) keep working and extraction reports `LOCAL MODEL UNAVAILABLE`.

## Privacy

- **Aliases.** Every command displays the alias you chose at `init`, never the directory name or path (paths live only in `registry.json`).
- **`.thrashignore`** (project root, plus `$THRASH_HOME/thrashignore` globally): ignored paths are never listed, read, fingerprinted or sent to the model. Defaults: `.env`, `*.pem`, `*.key`, `credentials*`, `secrets*`, `node_modules/`, `.venv/`, `dist/`, `build/`, `.git/`, ... Syntax is a gitignore subset (no `!` negation).
- **Redaction.** Secret-looking assignments (`api_key = ...`, `password: ...`, known token shapes, private-key blocks) are masked even in files that are allowed.
- **No surveillance.** No keystrokes, no browser history, no global process scanning. THRASH logs only what THRASH itself does (`events.jsonl`).

Limit: a README or note that *contains* your real project name will still reach the local model and may appear in a generated summary. Use an alias *and* check what your notes say.

## How thrashing is detected

A scheduler heuristic, **not** neuroscience. Four transparent signals over a sliding window (default 4 hours):

| Signal | Fires when | Env var |
|---|---|---|
| switch rate | switches in window ≥ 6 | `THRASH_SWITCH_LIMIT` |
| short sessions | median session < 20 min (needs ≥ 3 sessions) | `THRASH_MEDIAN_SESSION_MIN` |
| context reconstruction | switches that needed reconstruction ≥ 3 | `THRASH_RECON_LIMIT` |
| working-set pressure | active (RUNNING+READY) ≥ 4 | `THRASH_MAX_ACTIVE` |

`THRASHING` when at least `THRASH_SIGNALS_REQUIRED` (2) fire, `STRAINED` for one, otherwise `NOMINAL`. Window: `THRASH_WINDOW_HOURS`.

A switch needed *reconstruction* if the destination had no image, its image is older than `THRASH_STALE_HOURS` (24), or drift was MODERATE/HIGH.

Metrics shown by `thrash top`: **LOAD** is the share of recorded run-time in the last 24 h (from your sessions). **CTX~** is an *estimate*: serialized image size ÷ 4 ≈ tokens. **Pressure** is active ÷ limit, a definition, not a measurement of anything in your head.

## Installation

Requires Python 3.11+, Git, and [Ollama](https://ollama.com) with a Gemma model.

```bash
ollama pull gemma3:4b
git clone https://github.com/miclaldogan/thrash && cd thrash
python -m venv .venv && . .venv/bin/activate
pip install -e .            # or: pipx install .
thrash --help
```

Configuration is plain environment variables (see [`.env.example`](.env.example)). `THRASH_MODEL` picks the model (default `gemma3:4b`); `THRASH_OLLAMA_URL` the server; `THRASH_HOME` the data directory (default `~/.local/share/thrash`, XDG-aware).

## Commands

| Command | What it does |
|---|---|
| `thrash init [--alias A]` | register the current project, build its first process image |
| `thrash top [-w]` | kernel monitor: process table, pressure, thrashing state |
| `thrash ps [-a]` | plain process list for scripts and screenshots |
| `thrash status [P]` | full process image of the running (or named) process |
| `thrash switch P` | save the running process, restore P, report drift |
| `thrash suspend P` | snapshot P and put it to SLEEPING |
| `thrash wake P` | SLEEPING → READY and restore context (does not switch) |
| `thrash fork NAME` | register a new process; warns under pressure (`--suspend X`, `--force`, `--create`) |
| `thrash kill P` | extract final state, optionally write a core dump (`--core/--no-core`, `-y`) |
| `thrash resurrect CORE` | re-register a terminated process from its core dump |

`fork` advises, it never blocks: interactive shells get `[S] suspend one / [F] fork anyway`; non-interactive runs warn and proceed.

## Architecture

```text
cli.py ──► scheduler.py (Kernel) ──► registry.py      process table, one-RUNNING invariant
 │             │    │                 telemetry.py     events.jsonl
 ▼             │    └► drift.py       saved image vs repo now
ui.py          ▼
        git_context.py ──► privacy.py   evidence gathering; ignore rules + redaction
               │
               ▼
        extract.py ──► prompts.py, ollama_client.py ──► local Ollama / Gemma
               │
               ▼
        process_image.py   schemas + strict validation
```

Storage (`~/.local/share/thrash/`): `registry.json`, `events.jsonl`, `processes/NNN.json` (live image + fingerprint), `swap/<alias>.ctx` (paged-out copy), `graveyard/<alias>.core`. JSON/JSONL only, no database. Writes are atomic.

Events carry: timestamp, from/to project, time since last switch, snapshot age, restore duration, session length, whether reconstruction was needed, drift level, and the destination's last commit time.

## Limitations

- It is only as good as your repositories. Work that lives in no file, commit or note is invisible to it. THRASH never sees what is in your head.
- Small local models misread things. Confidence is the model's own, and a low-evidence repo gets a plausible-looking but thin image. Review `thrash status`.
- Drift uses keyword overlap, not understanding: it can miss real contradictions and flag coincidences (hence "may be stale").
- The model cannot see work that is not in the working tree (e.g. an unsaved Blender scene).
- Heuristic thresholds are defaults I picked, not validated against anyone. Tune them.
- Single user, single machine, Linux-first (paths are platform-aware; only Linux was tested).
- No shell integration yet: it records what you tell THRASH, not what you do.

## License

MIT. See [LICENSE](LICENSE).
