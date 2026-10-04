# Demo script (about 3 minutes)

Setup, once, off camera:

```bash
ollama pull gemma3:4b
pip install -e .
python demo/build_demo.py && source demo/env.sh      # synthetic workspace, isolated THRASH_HOME
for p in game-alpha research-beta robot-lab paper-crane old-agent; do
  thrash init --path demo/workspace/$p --alias $p >/dev/null
done
```

`demo/run_demo.sh [--pause]` runs everything below in order.

## 0:00 The premise (say it, don't type it)

"A computer saves a process's state before switching. Humans don't. THRASH does."

```bash
thrash ps
```

## 0:20 A. Normal switch

```bash
thrash switch research-beta
thrash switch game-alpha
```

Point at: the working-set counts, `paged -> ...swap/research-beta.ctx`, then `PAGE FAULT`, PC, registers, `NEXT INSTRUCTION`.

## 1:00 B. Page fault on a stale image

```bash
thrash switch robot-lab
python demo/age_image.py game-alpha 71        # demo tooling: pretend 71 hours passed
( cd demo/workspace/game-alpha && mkdir -p engine && echo "# scaffold" > engine/integration.gd \
  && git add -A && git commit -qm "engine: start integration scaffold" )
thrash switch game-alpha
```

Point at: `Process image is 71 hours old`, `POSSIBLE DRIFT`, `ASSUMPTION MAY BE STALE` with its evidence. Say that it says *may*, with the evidence, not "contradiction".

## 1:45 C. Thrashing

```bash
for i in 1 2 3 4; do for p in research-beta robot-lab paper-crane game-alpha; do thrash switch $p >/dev/null; done; done
thrash top
```

Point at: `STATE: THRASHING`, the signals that fired, and that every number comes from the event log, not from the model.

## 2:20 D. Zombie

```bash
thrash ps          # old-agent: ZOMBIE (41 days idle + unresolved work)
```

## 2:35 E. Kill, core dump, resurrect

```bash
python demo/age_image.py old-agent 1032
thrash kill old-agent --core
thrash resurrect old-agent
```

Point at: `last useful state`, `unfinished`, `core dumped`, then the drift report on resurrection.

## Bonus: no network, no model

```bash
THRASH_OLLAMA_URL=http://127.0.0.1:1 thrash switch research-beta   # LOCAL MODEL UNAVAILABLE, switch still happens
thrash top                                                          # still works
```
