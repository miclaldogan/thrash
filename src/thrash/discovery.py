"""Read-only project discovery. Never resolve links or enter excluded roots."""
from pathlib import Path
import stat

from .privacy import IgnoreRules, ScanPolicy, absolute, scan_safe


def discover_projects(base: Path, policy: ScanPolicy | None = None, max_depth: int = 4) -> list[Path]:
    policy = policy or ScanPolicy()
    base = absolute(base)
    policy.require_root(base)
    rules = IgnoreRules.load(base, policy=policy)
    found = []
    pending = [base]
    while pending:
        root = pending.pop()
        if not policy.allows(root):
            continue
        children = scan_safe(root, policy)
        # Stop at project roots, including plain directories with a project marker.
        # Never enter .git, and don't treat linked markers as evidence.
        markers = {"readme.md", "readme.rst", "pyproject.toml", "package.json", "cargo.toml", "go.mod"}
        if root != base and any((name == ".git" and stat.S_ISDIR(info.st_mode)) or
                                (name.lower() in markers and stat.S_ISREG(info.st_mode))
                                for name, info in children):
            found.append(root)
            continue
        for name, info in children:
            path = root / name
            if not stat.S_ISDIR(info.st_mode):
                continue
            if len(path.relative_to(base).parts) > max_depth:
                continue
            rel = path.relative_to(base).as_posix() + "/"
            if rules.is_ignored(rel):
                continue
            pending.append(path)
    return sorted(found)
