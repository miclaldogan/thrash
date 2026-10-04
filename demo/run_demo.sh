#!/usr/bin/env bash
# Reproduces demos A-E against the synthetic workspace. Needs Ollama + the model in THRASH_MODEL.
# Usage: demo/run_demo.sh [--pause]     (--pause waits for Enter between scenes)
set -euo pipefail
cd "$(dirname "$0")/.."
PAUSE=${1:-}
python3 demo/build_demo.py >/dev/null
export THRASH_HOME="$PWD/demo/.thrash-home"
T="${THRASH:-thrash}"
scene() { echo; echo "================ $* ================"; [ "$PAUSE" = "--pause" ] && read -r _ || true; }
run()   { echo "\$ thrash $*"; $T "$@"; echo; }

scene "SETUP: register five synthetic projects"
for p in game-alpha research-beta robot-lab paper-crane old-agent; do
  $T init --path "demo/workspace/$p" --alias "$p" >/dev/null && echo "registered $p"
done

scene "DEMO A: normal switch"
run switch research-beta
run switch game-alpha

scene "DEMO B: page fault on a stale image"
run switch robot-lab
python3 demo/age_image.py game-alpha 71          # demo tooling: pretend 71h passed
( cd demo/workspace/game-alpha \
  && mkdir -p engine Assets \
  && printf 'extends Node\n# engine integration scaffold\n' > engine/integration.gd \
  && git add -A && GIT_AUTHOR_NAME=demo GIT_AUTHOR_EMAIL=d@x.invalid GIT_COMMITTER_NAME=demo GIT_COMMITTER_EMAIL=d@x.invalid \
     git commit -qm "engine: start integration scaffold" )
run switch game-alpha
run status

scene "DEMO C: thrashing"
for i in 1 2 3 4; do
  $T switch research-beta >/dev/null; $T switch robot-lab >/dev/null; $T switch paper-crane >/dev/null; $T switch game-alpha >/dev/null
done
run top

scene "DEMO D: zombie"
run ps

scene "DEMO E: kill, core dump, resurrect"
python3 demo/age_image.py old-agent 1032          # demo tooling: pretend 43 days passed
run kill old-agent --core
( cd demo/workspace/old-agent && printf "# TODO: write scope experiment\n" >> agent/calendar.py \
  && git add -A && GIT_AUTHOR_NAME=demo GIT_AUTHOR_EMAIL=d@x.invalid GIT_COMMITTER_NAME=demo GIT_COMMITTER_EMAIL=d@x.invalid \
     git commit -qm "calendar: write scope experiment" )
run ps --all
run resurrect old-agent
run top
