"""Deterministic repository inspection. No model involved.

Everything here goes through the privacy rules first: ignored paths are never
listed, read, or fingerprinted.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .privacy import IgnoreRules, redact
from .process_image import Fingerprint

TODO_RE = re.compile(r"\b(?:TODO|FIXME|XXX)\b|^\s*[-*]\s*\[ \]", re.M)
DOC_HINTS = ("readme", "todo", "notes", "roadmap", "design", "decision", "plan", "changelog", "status")
MAX_FILE_BYTES = 200_000
MAX_INVENTORY = 2000


def git(root: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def is_git_repo(root: Path) -> bool:
    return git(root, "rev-parse", "--is-inside-work-tree") is not None


def toplevel(path: Path) -> Path | None:
    out = git(path, "rev-parse", "--show-toplevel")
    return Path(out.strip()) if out else None


def head_sha(root: Path) -> str | None:
    out = git(root, "rev-parse", "HEAD")
    return out.strip() if out else None


def last_commit_ts(root: Path) -> float | None:
    out = git(root, "log", "-1", "--format=%ct")
    return float(out.strip()) if out and out.strip() else None


@dataclass
class Commit:
    sha: str
    ts: float
    subject: str
    files: list[str] = field(default_factory=list)


def recent_commits(root: Path, n: int = 15, since_sha: str | None = None) -> list[Commit]:
    rng = f"{since_sha}..HEAD" if since_sha else "HEAD"
    out = git(root, "log", rng, f"-n{n}", "--format=@@%h|%ct|%s", "--name-only")
    commits: list[Commit] = []
    if not out:
        return commits
    for block in out.split("@@")[1:]:
        lines = block.strip().splitlines()
        head = lines[0].split("|", 2)
        if len(head) < 3:
            continue
        commits.append(Commit(head[0], float(head[1]), head[2], [l for l in lines[1:] if l.strip()]))
    return commits


def commit_count_since(root: Path, sha: str) -> int | None:
    out = git(root, "rev-list", "--count", f"{sha}..HEAD")
    return int(out.strip()) if out and out.strip().isdigit() else None


def files_changed_since(root: Path, sha: str) -> list[str] | None:
    out = git(root, "diff", "--name-only", sha, "HEAD")
    return None if out is None else [l for l in out.splitlines() if l]


def dirty_files(root: Path) -> list[str]:
    out = git(root, "status", "--porcelain", "-uall")
    files = []
    for line in (out or "").splitlines():
        path = line[3:].split(" -> ")[-1].strip().strip('"')
        if path:
            files.append(path)
    return files


def inventory(root: Path, rules: IgnoreRules) -> dict[str, float]:
    """relpath -> mtime for every non-ignored file (tracked + untracked-not-gitignored)."""
    out = git(root, "ls-files", "-co", "--exclude-standard")
    if out is not None:
        rels = [l for l in out.splitlines() if l]
    else:
        rels = []
        for dp, dns, fns in os.walk(root):
            dns[:] = [d for d in dns if not rules.is_ignored(os.path.relpath(os.path.join(dp, d), root) + "/x")]
            rels += [os.path.relpath(os.path.join(dp, f), root) for f in fns]
    inv: dict[str, float] = {}
    for rel in rels:
        if rules.is_ignored(rel):
            continue
        try:
            inv[rel] = (root / rel).stat().st_mtime
        except OSError:
            continue
        if len(inv) >= MAX_INVENTORY:
            break
    return inv


def read_text(path: Path, limit: int) -> str | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        data = path.read_bytes()[: limit * 4]
    except OSError:
        return None
    if b"\0" in data[:2048]:
        return None
    return data.decode("utf-8", errors="replace")[:limit]


def current_fingerprint(root: Path, rules: IgnoreRules, now: float) -> Fingerprint:
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    return Fingerprint(
        head=head_sha(root),
        branch=branch.strip() if branch else None,
        taken_at=now,
        dirty=sorted(f for f in dirty_files(root) if not rules.is_ignored(f)),
        files=inventory(root, rules),
    )


@dataclass
class RepoContext:
    """Everything the model is allowed to see, already filtered and redacted."""

    sections: list[tuple[str, str]]
    allowed_paths: set[str]
    fingerprint: Fingerprint
    todo_count: int
    redactions: int
    last_activity: float | None

    def render(self) -> str:
        return "\n\n".join(f"### {title}\n{body}" for title, body in self.sections if body.strip())


def _doc_score(rel: str, mtime: float) -> tuple[int, float]:
    low = rel.lower()
    name = os.path.basename(low)
    hinted = any(h in name for h in DOC_HINTS) or any(h in low.split("/")[0] for h in ("docs", "notes"))
    doc = low.endswith((".md", ".txt", ".rst", ".org"))
    return (2 if hinted and doc else 1 if doc else 0, mtime)


def gather_context(root: Path, cfg: Config, rules: IgnoreRules, now: float) -> RepoContext:
    fp = current_fingerprint(root, rules, now)
    inv = fp.files
    budget = cfg.context_chars
    redactions = 0
    todo_count = 0
    sections: list[tuple[str, str]] = []

    commits = recent_commits(root, 15)
    if commits:
        lines = []
        for c in commits:
            files = [f for f in c.files if not rules.is_ignored(f)][:6]
            lines.append(f"{c.sha} {_ago(now - c.ts)} ago: {c.subject}  [{', '.join(files)}]")
        sections.append(("RECENT COMMITS (newest first)", "\n".join(lines)))
    if fp.dirty:
        sections.append(("UNCOMMITTED CHANGES", "\n".join(fp.dirty[:30])))

    by_recent = sorted(inv.items(), key=lambda kv: kv[1], reverse=True)
    sections.append(
        ("RECENTLY MODIFIED FILES", "\n".join(f"{rel} ({_ago(now - m)} ago)" for rel, m in by_recent[:20]))
    )
    sections.append(("FILE LIST", "\n".join(sorted(inv)[:150])))

    # documents first (README, TODO, notes), then a few recent source files
    docs = sorted(inv.items(), key=lambda kv: _doc_score(*kv), reverse=True)
    doc_budget = int(budget * 0.7)
    used = 0
    todo_samples: list[str] = []
    for rel, _ in docs:
        score = _doc_score(rel, 0)[0]
        text = read_text(root / rel, 4000 if score else 1500)
        if text is None:
            continue
        todo_count += len(TODO_RE.findall(text))
        for m in re.finditer(r"^.*(?:TODO|FIXME|XXX|\[ \]).*$", text, re.M):
            if len(todo_samples) < 25:
                todo_samples.append(f"{rel}: {m.group(0).strip()[:120]}")
        if score == 0 or used >= doc_budget:
            continue
        text, n = redact(text)
        redactions += n
        take = text[: max(0, doc_budget - used)]
        used += len(take)
        sections.append((f"FILE {rel}", take))
    if todo_samples:
        sections.append(("TODO / OPEN-CHECKBOX LINES", "\n".join(todo_samples)))

    src_budget = budget - used
    shown = 0
    for rel, _ in by_recent:
        if shown >= 3 or src_budget < 400:
            break
        if _doc_score(rel, 0)[0]:
            continue
        text = read_text(root / rel, min(1500, src_budget))
        if not text:
            continue
        text, n = redact(text)
        redactions += n
        src_budget -= len(text)
        shown += 1
        sections.append((f"SOURCE (head) {rel}", text))

    activity = [last_commit_ts(root)] + [(root / f).stat().st_mtime for f in fp.dirty if (root / f).exists()]
    return RepoContext(
        sections=sections,
        allowed_paths=set(inv),
        fingerprint=fp,
        todo_count=todo_count,
        redactions=redactions,
        last_activity=max((a for a in activity if a), default=None),
    )


def _ago(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def repo_last_activity(root: Path, rules: IgnoreRules) -> float | None:
    """Latest commit time or latest mtime of an uncommitted, non-ignored file."""
    stamps = [last_commit_ts(root)]
    for f in dirty_files(root):
        if rules.is_ignored(f):
            continue
        try:
            stamps.append((root / f).stat().st_mtime)
        except OSError:
            pass
    return max((s for s in stamps if s), default=None)
