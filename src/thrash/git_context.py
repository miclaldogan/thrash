"""Deterministic repository inspection. No model involved.

Everything here goes through the privacy rules first: ignored paths are never
listed, read, or fingerprinted.
"""

from __future__ import annotations

import os
import hashlib
import re
import subprocess
import stat
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .privacy import IgnoreRules, ScanPolicy, absolute, read_safe, scan_safe, redact, public_text
from .process_image import Fingerprint

TODO_RE = re.compile(r"\b(?:TODO|FIXME|XXX)\b|^\s*[-*]\s*\[ \]", re.M)
DOC_HINTS = ("readme", "todo", "notes", "roadmap", "design", "decision", "plan", "changelog", "status")
MAX_FILE_BYTES = 200_000
MAX_INVENTORY = 2000


def git(root: Path, *args: str) -> str | None:
    if not ScanPolicy().allows(root):
        return None
    # Do not follow a linked Git directory or worktree indirection outside the root.
    if (root / ".git").is_symlink() or (root / ".git").is_file():
        return None
    # Do not consult a parent repository for a plain directory, or Git object
    # stores redirected elsewhere (worktrees/alternates are intentionally skipped).
    if not (root / ".git").is_dir():
        return None
    for name in ("HEAD", "config", "index", "objects", "refs", "packed-refs", "objects/info"):
        if not ScanPolicy().allows(root / ".git" / name):
            return None
    if (root / ".git/objects/info/alternates").exists() or (root / ".git/commondir").exists():
        return None
    try:
        r = subprocess.run(
            ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
             "-C", str(root), *args],
            capture_output=True, text=True, timeout=30, check=False,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"},
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def is_git_repo(root: Path) -> bool:
    return git(root, "rev-parse", "--is-inside-work-tree") is not None


def toplevel(path: Path, policy: ScanPolicy | None = None) -> Path | None:
    policy = policy or ScanPolicy()
    path = absolute(path)
    for candidate in (path, *path.parents):
        if not policy.allows(candidate):
            return None
        out = git(candidate, "rev-parse", "--show-toplevel")
        if out:
            return Path(out.strip())
    return None


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
        commits.append(Commit(head[0], float(head[1]), public_text(head[2]), [l for l in lines[1:] if l.strip()]))
    return commits


def commit_count_since(root: Path, sha: str) -> int | None:
    out = git(root, "rev-list", "--count", f"{sha}..HEAD")
    return int(out.strip()) if out and out.strip().isdigit() else None


def files_changed_since(root: Path, sha: str) -> list[str] | None:
    out = git(root, "diff", "--no-ext-diff", "--no-textconv", "--name-only", sha, "HEAD")
    return None if out is None else [l for l in out.splitlines() if l]


def dirty_files(root: Path, rules: IgnoreRules | None = None,
                files: dict[str, float] | None = None) -> list[str]:
    """Compare allowed files to index hashes, without `git status` scanning secrets.

    Git reads index metadata only. File bytes always pass through our no-follow
    reader. Oversized/binary files are not semantically inspected.
    """
    rules = rules or IgnoreRules.load(root)
    rules.policy.require_root(root)
    files = inventory(root, rules) if files is None else files
    index: dict[str, str] = {}
    out = git(root, "ls-files", "--stage", "-z")
    for record in (out or "").split("\0"):
        if "\t" not in record:
            continue
        metadata, rel = record.split("\t", 1)
        fields = metadata.split()
        if len(fields) == 3 and fields[0] in ("100644", "100755") and not rules.is_ignored(rel):
            index[rel] = fields[1]
    dirty = set(files) - set(index)
    dirty.update(rel for rel in index if rel not in files)
    for rel in set(files) & set(index):
        data = read_safe(root / rel, MAX_FILE_BYTES, rules.policy)
        if data is None:
            continue
        header = f"blob {len(data)}\0".encode()
        digest = hashlib.sha256(header + data) if len(index[rel]) == 64 else hashlib.sha1(header + data)
        if digest.hexdigest() != index[rel]:
            dirty.add(rel)
    # Staged differences are between Git trees/index, never working-tree reads.
    staged = git(root, "diff", "--cached", "--no-ext-diff", "--no-textconv", "--ignore-submodules=all", "--name-only", "-z")
    dirty.update(rel for rel in (staged or "").split("\0") if rel and not rules.is_ignored(rel))
    return sorted(dirty)


def inventory(root: Path, rules: IgnoreRules) -> dict[str, float]:
    """Only regular non-ignored files; prune excluded directories before descent."""
    root = absolute(root)
    rules.policy.require_root(root)
    if rules.root is None:
        rules.root = root
    inv: dict[str, float] = {}
    pending = [root]
    while pending and len(inv) < MAX_INVENTORY:
        directory = pending.pop()
        for name, info in scan_safe(directory, rules.policy):
            path = directory / name
            rel = path.relative_to(root).as_posix()
            if rules.is_ignored(rel) or stat.S_ISLNK(info.st_mode):
                continue
            if stat.S_ISDIR(info.st_mode):
                if not rules.is_ignored(rel + "/"):
                    pending.append(path)
            elif stat.S_ISREG(info.st_mode):
                inv[rel] = info.st_mtime
                if len(inv) >= MAX_INVENTORY:
                    break
    return inv


def read_text(path: Path, limit: int, policy: ScanPolicy | None = None) -> str | None:
    data = read_safe(path, limit * 4, policy)
    if data is None:
        return None
    if b"\0" in data[:2048]:
        return None
    return data.decode("utf-8", errors="replace")[:limit]


def current_fingerprint(root: Path, rules: IgnoreRules, now: float) -> Fingerprint:
    rules.policy.require_root(root)
    files = inventory(root, rules)
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    return Fingerprint(
        head=head_sha(root),
        branch=branch.strip() if branch else None,
        taken_at=now,
        dirty=dirty_files(root, rules, files),
        files=files,
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
        return public_text("\n\n".join(f"### {title}\n{body}" for title, body in self.sections if body.strip()))


def _doc_score(rel: str, mtime: float) -> tuple[int, float]:
    low = rel.lower()
    name = os.path.basename(low)
    hinted = any(h in name for h in DOC_HINTS) or any(h in low.split("/")[0] for h in ("docs", "notes"))
    doc = low.endswith((".md", ".txt", ".rst", ".org"))
    return (2 if hinted and doc else 1 if doc else 0, mtime)


def gather_context(root: Path, cfg: Config, rules: IgnoreRules, now: float) -> RepoContext:
    policy = ScanPolicy(tuple(set(cfg.excluded_roots + rules.policy.excluded_roots)))
    policy.require_root(root)
    rules.policy = policy
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
            if c.files and not files:
                continue  # do not summarize work that concerns only ignored files
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
        text = read_text(root / rel, 4000 if score else 1500, policy)
        if text is None:
            continue
        text, n = redact(text)
        redactions += n
        todo_count += len(TODO_RE.findall(text))
        for m in re.finditer(r"^.*(?:TODO|FIXME|XXX|\[ \]).*$", text, re.M):
            if len(todo_samples) < 25:
                todo_samples.append(f"{rel}: {m.group(0).strip()[:120]}")
        if score == 0 or used >= doc_budget:
            continue
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
        text = read_text(root / rel, min(1500, src_budget), policy)
        if not text:
            continue
        text, n = redact(text)
        redactions += n
        src_budget -= len(text)
        shown += 1
        sections.append((f"SOURCE (head) {rel}", text))

    activity = [last_commit_ts(root)] + [inv[f] for f in fp.dirty if f in inv]
    clean_sections = []
    for title, body in sections:
        body, n = redact(body)
        redactions += n
        clean_sections.append((public_text(title), public_text(body)))
    return RepoContext(
        sections=clean_sections,
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
    rules.policy.require_root(root)
    inv = inventory(root, rules)
    stamps = [last_commit_ts(root)]
    for f in dirty_files(root, rules, inv):
        if rules.is_ignored(f):
            continue
        if f in inv:
            stamps.append(inv[f])
    return max((s for s in stamps if s), default=None)
