"""Context drift: compare a saved process image with the repository as it is now.

Deterministic. We never claim a contradiction; we report evidence and say
"may be stale" when a saved open assumption shares vocabulary with new work.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import git_context as gc
from .privacy import IgnoreRules
from .process_image import Fingerprint, ProcessImage

OPEN_WORDS = ("undecided", "unresolved", "not started", "not begun", "postponed", "pending",
              "todo", "unknown", "blocked", "later", "deferred", "open", "tbd", "missing")
STOP = set("""the and for with that this from into not has have are was were been will would should could
about after before while when what which their there then than them they your our its not none yes
done finished started start begin begun integration unresolved undecided postponed pending todo""".split())


@dataclass
class StaleAssumption:
    saved: str
    evidence: list[str]


@dataclass
class DriftReport:
    new_commits: int = 0
    commit_subjects: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    stale: list[StaleAssumption] = field(default_factory=list)
    history_rewritten: bool = False

    @property
    def level(self) -> str:
        n_files, n_commits, n_stale = len(self.changed_files), self.new_commits, len(self.stale)
        if self.history_rewritten or n_files >= 15 or n_commits >= 10 or n_stale >= 2:
            return "HIGH"
        if n_files > 5 or n_commits > 3 or n_stale == 1:
            return "MODERATE"
        if n_files or n_commits:
            return "LOW"
        return "NONE"


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z][a-z0-9_]{3,}", text.lower()) if t not in STOP}


def open_assumptions(image: ProcessImage) -> list[str]:
    out = [f"{k}: {v}" for k, v in image.registers.items() if any(w in v.lower() for w in OPEN_WORDS)]
    out += list(image.unresolved)
    return out


def compute_drift(root: Path, image: ProcessImage, saved: Fingerprint, rules: IgnoreRules, now: float) -> DriftReport:
    report = DriftReport()
    cur = gc.current_fingerprint(root, rules, now)

    changed: set[str] = set()
    commits: list[gc.Commit] = []
    if saved.head and cur.head and saved.head != cur.head:
        n = gc.commit_count_since(root, saved.head)
        if n is None:
            report.history_rewritten = True
        else:
            report.new_commits = n
            commits = gc.recent_commits(root, min(n, 50), since_sha=saved.head)
            changed.update(gc.files_changed_since(root, saved.head) or [])
    for rel, mtime in cur.files.items():
        old = saved.files.get(rel)
        if old is None or abs(old - mtime) > 1:
            changed.add(rel)
    changed.update(rel for rel in saved.files if rel not in cur.files)
    changed.update(set(cur.dirty) ^ set(saved.dirty))

    report.changed_files = sorted(f for f in changed if not rules.is_ignored(f))
    report.commit_subjects = [c.subject for c in commits[:5]]

    evidence_pool = [(f, f.lower()) for f in report.changed_files]
    subjects = [(c.subject, c.subject.lower()) for c in commits]
    for assumption in open_assumptions(image):
        toks = _tokens(assumption)
        hits: list[str] = []
        for tok in sorted(toks):
            hits += [f for f, low in evidence_pool if tok in low and f not in hits]
            hits += [f"commit: {s}" for s, low in subjects if tok in low and f"commit: {s}" not in hits]
        if hits:
            report.stale.append(StaleAssumption(assumption, hits[:4]))
    return report
