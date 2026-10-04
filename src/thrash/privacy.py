"""What may be shown, and what may reach the model.

Two mechanisms:
  * `.thrashignore` (+ built-in defaults): paths that are never read, listed or sent.
  * redaction: secret-looking assignments inside otherwise-allowed files.

Pattern syntax is a deliberate gitignore subset: `#` comments, `dir/` matches a
directory anywhere, `*.ext` / `name*` glob a path component, patterns containing
`/` are matched against the path relative to the project root. Negation (`!`) is
not supported.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

DEFAULT_PATTERNS = [
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", "id_ed25519*",
    "credentials*", "secrets*", "*.secret", "*.kdbx",
    "node_modules/", ".venv/", "venv/", "dist/", "build/", "__pycache__/",
    ".git/", ".thrash/", "target/", ".idea/", ".vscode/",
]

_SECRET_ASSIGN = re.compile(
    r"""(?ix)
    (?P<key>[\w.-]*(?:api[_-]?key|secret|token|passwd|password|private[_-]?key)[\w.-]*)
    (?P<sep>\s*[:=]\s*)
    (?P<val>["']?[^\s"']{8,}["']?)
    """
)
_PRIVATE_BLOCK = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_TOKEN_SHAPES = re.compile(r"\b(?:AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{20,}|xox[bp]-[A-Za-z0-9-]{20,})\b")


class IgnoreRules:
    def __init__(self, patterns: list[str] | None = None):
        self.patterns = list(DEFAULT_PATTERNS if patterns is None else patterns)

    @classmethod
    def load(cls, project_root: Path, global_file: Path | None = None) -> "IgnoreRules":
        patterns = list(DEFAULT_PATTERNS)
        for f in (global_file, project_root / ".thrashignore"):
            if f and f.is_file():
                for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        patterns.append(line)
        return cls(patterns)

    def is_ignored(self, relpath: str) -> bool:
        rel = relpath.replace("\\", "/").removeprefix("./")
        parts = [p for p in rel.split("/") if p]
        if not parts:
            return False
        for pat in self.patterns:
            if pat.endswith("/"):
                name = pat.rstrip("/")
                dirs = parts[:-1] if "/" not in name else parts
                if "/" in name:
                    if rel == name or rel.startswith(name + "/"):
                        return True
                elif any(fnmatch.fnmatch(d, name) for d in dirs) or (
                    # a path that *is* the directory (git status lists dirs)
                    fnmatch.fnmatch(parts[-1], name)
                    and relpath.endswith("/")
                ):
                    return True
            elif "/" in pat:
                if fnmatch.fnmatch(rel, pat.lstrip("/")):
                    return True
            else:
                if any(fnmatch.fnmatch(p, pat) for p in parts):
                    return True
        return False


def redact(text: str) -> tuple[str, int]:
    """Mask secret-looking values. Returns (clean_text, number_of_redactions)."""
    if _PRIVATE_BLOCK.search(text):
        return "[REDACTED: file contains a private key block]", 1
    count = 0

    def _assign(m: re.Match) -> str:
        nonlocal count
        count += 1
        return f"{m.group('key')}{m.group('sep')}[REDACTED]"

    text = _SECRET_ASSIGN.sub(_assign, text)

    def _tok(_m: re.Match) -> str:
        nonlocal count
        count += 1
        return "[REDACTED]"

    text = _TOKEN_SHAPES.sub(_tok, text)
    return text, count
