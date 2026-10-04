#!/usr/bin/env python3
"""Build the fully synthetic THRASH demo workspace.

Everything here is invented. Five tiny Git repositories with backdated commits go
into demo/workspace/, and THRASH state goes into an isolated demo/.thrash-home/,
so your real registry is never touched.

    python demo/build_demo.py            # (re)build
    source demo/env.sh                   # point THRASH at the demo home
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WS = HERE / "workspace"
HOME = HERE / ".thrash-home"
DAY = 86400

PROJECTS: dict[str, dict] = {
    "game-alpha": {
        "age_days": 3,
        "files": {
            "README.md": "# game-alpha\n\nA small 3D adventure. Current focus: character rig.\n",
            "docs/character.md": "# Character\n\nFacial hair: finished.\nHair physics: not decided how to implement.\nEngine: undecided.\n",
            "notes/rig.md": "# Rig notes\n\n- Decision: do not begin engine integration before the rig test.\n- Jaw is not rigged yet. Rig the jaw, then the rest of the face.\n- TODO: create a test pose\n- TODO: export to engine (AFTER the rig test)\n",
            "TODO.md": "- [x] model facial hair\n- [ ] rig jaw\n- [ ] rig face\n- [ ] test pose\n- [ ] hair physics (unresolved)\n",
        },
        "commits": [(3, "model facial hair"), (3, "notes: rig plan and engine decision")],
    },
    "research-beta": {
        "age_days": 1,
        "files": {
            "README.md": "# research-beta\n\nDoes a learned scheduler beat round-robin on bursty workloads?\n",
            "notes/hypothesis.md": "# Hypothesis\n\nBursty arrivals hurt round-robin tail latency.\n\nDecision: use the synthetic trace generator, not real traces.\nOpen question: which fairness metric to report?\nBlocker: baseline simulator crashes above 10k jobs.\n",
            "TODO.md": "- [ ] fix simulator crash above 10k jobs\n- [ ] pick fairness metric\n- [ ] run baseline sweep\n",
            "sim/baseline.py": "def round_robin(jobs, quantum=4):\n    # TODO: crashes above 10k jobs (index error in queue rotation)\n    ...\n",
        },
        "commits": [(2, "simulator: baseline round robin"), (1, "notes: hypothesis and trace decision")],
    },
    "robot-lab": {
        "age_days": 9,
        "files": {
            "README.md": "# robot-lab\n\nSix-legged walker with servo drivers.\n",
            "notes/calibration.md": "# Calibration\n\nLeg 1-4 servo offsets done. Legs 5 and 6 drift under load.\nDecision: keep 50Hz PWM; do not switch to a driver board yet.\n",
            "firmware/legs.ino": "// TODO: per-leg offset table for legs 5,6\nvoid setup() {}\nvoid loop() {}\n",
        },
        "commits": [(10, "firmware: offsets for legs 1-4"), (9, "notes: calibration status")],
    },
    "paper-crane": {
        "age_days": 6,
        "files": {
            "README.md": "# paper-crane\n\nShort article draft about origami-inspired folding heuristics.\n",
            "draft/outline.md": "# Outline\n\n1. Motivation (written)\n2. Fold model (half written)\n3. Results (not started)\n\nOpen question: include the failed experiment?\n",
        },
        "commits": [(7, "draft: motivation section"), (6, "draft: outline")],
    },
    "old-agent": {
        "age_days": 41,
        "files": {
            "README.md": "# old-agent\n\nA personal assistant agent that reads my calendar.\n",
            "notes/status.md": "# Status\n\nCalendar READ-ONLY integration works.\nWritable calendar needs a new permission scope; not requested yet.\nTODO: implement writable calendar\nTODO: confirmation prompt before any write\n",
            "agent/calendar.py": "def list_events():\n    return []  # read-only works\n\n# TODO: create_event needs write scope\n",
        },
        "commits": [(45, "calendar: read-only integration"), (41, "notes: status")],
    },
}


def git(repo: Path, *args: str, when: float | None = None) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "demo", "GIT_AUTHOR_EMAIL": "demo@example.invalid",
           "GIT_COMMITTER_NAME": "demo", "GIT_COMMITTER_EMAIL": "demo@example.invalid"}
    if when:
        stamp = f"{int(when)} +0000"
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = stamp
    subprocess.run(["git", "-C", str(repo), *args], check=True, env=env, capture_output=True)


def build() -> None:
    for d in (WS, HOME):
        if d.exists():
            shutil.rmtree(d)
    WS.mkdir(parents=True)
    now = time.time()
    for name, spec in PROJECTS.items():
        repo = WS / name
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        files = spec["files"]
        # split files across commits so history is not a single blob
        names = list(files)
        for i, (days_ago, msg) in enumerate(spec["commits"]):
            chunk = names[i::len(spec["commits"])] if i < len(spec["commits"]) - 1 else names[i:]
            chunk = [n for n in names if n in chunk]
            for n in chunk:
                (repo / n).parent.mkdir(parents=True, exist_ok=True)
                (repo / n).write_text(files[n])
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", msg, when=now - days_ago * DAY)
        # make working-tree mtimes match the story (matters for zombie detection)
        stamp = now - spec["age_days"] * DAY
        for p in repo.rglob("*"):
            if p.is_file() and ".git" not in p.parts:
                os.utime(p, (stamp, stamp))
    print(f"demo workspace: {WS}")
    print(f"thrash home:    {HOME}")


if __name__ == "__main__":
    build()
    # env.sh is portable, checked-in tooling; rebuilding a demo must not replace
    # it with a machine-specific absolute path.
    print(f"next: source {HERE / 'env.sh'}")
