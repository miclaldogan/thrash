#!/usr/bin/env python3
"""DEMO TOOLING ONLY: time-shift a saved process image so a page fault can be shown
without waiting 71 real hours.   usage: age_image.py <alias> <hours>

It rewrites `created_at` / `saved_at` in the stored context files. THRASH itself
never does this.
"""
import json
import os
import sys
from pathlib import Path

home = Path(os.environ["THRASH_HOME"])
alias, hours = sys.argv[1], float(sys.argv[2])
reg = json.loads((home / "registry.json").read_text())
pid = next(p["pid"] for p in reg["processes"] if p["alias"] == alias)
for f in (home / "processes" / f"{pid:03d}.json", home / "swap" / f"{alias}.ctx"):
    if f.exists():
        d = json.loads(f.read_text())
        d["saved_at"] -= hours * 3600
        d["image"]["meta"]["created_at"] -= hours * 3600
        d["fingerprint"]["taken_at"] -= hours * 3600
        f.write_text(json.dumps(d, indent=2))
print(f"{alias}: image aged by {hours:g}h")
