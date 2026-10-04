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
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from pathspec import GitIgnoreSpec

DEFAULT_PATTERNS = [
    ".env*", "*.pem", "*.key", "key.*", "*_key.*", "*-key.*", "*.p12", "*.pfx", "id_rsa*", "id_ed25519*",
    "*credential*", "*secret*", "*token*", "*password*", "*.kdbx",
    "*.crt", "*.cer", "*.der", "*.p7b", "*.p7c", "*.jks", "*.keystore",
    "*.cert", "*.csr", "*.pub", "*.p8", "*.keytab", ".direnv/", ".config/",
    ".kube/", ".azure/", ".docker/", ".terraform/",
    "certificates/", "certs/", "keys/", ".ssh/", ".aws/", ".gnupg/",
    ".npmrc", ".pypirc", ".netrc", "*.tfstate*", "*.tfvars*",
    "config.json", "config.yaml", "config.yml", "settings.json", "settings.yaml",
    "settings.yml", "appsettings*.json", "*.sqlite*", "*.db",
    "*config.*", "settings.*", "config/", "configs/", "configuration/", "settings/",
    "*certificate*", "*private-key*", "*private_key*", "*access-key*", "*access_key*",
    "node_modules/", ".venv/", "venv/", "dist/", "build/", "__pycache__/",
    ".git/", ".thrash/", "target/", ".idea/", ".vscode/",
    ".cache/", ".next/", ".nuxt/", "vendor/", ".tox/", ".mypy_cache/",
    ".pytest_cache/", ".ruff_cache/", "coverage/", "site-packages/",
]

_SECRET_ASSIGN = re.compile(
    r"""(?ix)
    (?P<key>[\w.-]*(?:api[_-]?key|secret|token|passwd|password|private[_-]?key)[\w.-]*)
    (?P<sep>["']?\s*[:=]\s*)
    (?P<val>"[^"\n]*"|'[^'\n]*'|[^\s,;}]+)
    """
)
_PRIVATE_BLOCK = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_TOKEN_SHAPES = re.compile(r"\b(?:AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{20,}|xox[bp]-[A-Za-z0-9-]{20,})\b")


def absolute(path: Path) -> Path:
    """Normalize lexically; never resolve a symlink or inspect its target."""
    return Path(os.path.abspath(path.expanduser()))


@dataclass(frozen=True)
class ScanPolicy:
    excluded_roots: tuple[Path, ...] = ()

    def excluded(self, path: Path) -> bool:
        path = absolute(path)
        return any(path.is_relative_to(absolute(root)) for root in self.excluded_roots)

    def allows(self, path: Path) -> bool:
        path = absolute(path)
        # This check must precede even lstat on an excluded directory.
        if self.excluded(path):
            return False
        current = Path(path.anchor)
        for part in path.parts[1:]:
            current /= part
            try:
                if stat.S_ISLNK(current.lstat().st_mode):
                    return False
            except FileNotFoundError:
                return True  # deleted paths can still be drift evidence
            except OSError:
                return False
        return True

    def require_root(self, root: Path) -> None:
        if not self.allows(root) or not root.is_dir():
            raise ValueError("excluded or unsafe project root")


def read_safe(path: Path, limit: int, policy: ScanPolicy | None = None) -> bytes | None:
    """Bounded regular-file read. On POSIX each component is opened without following links."""
    policy = policy or ScanPolicy()
    path = absolute(path)
    if not policy.allows(path):
        return None
    descriptors = []
    try:
        if os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW"):
            fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
            descriptors.append(fd)
            for part in path.parts[1:-1]:
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                descriptors.append(fd)
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        else:
            # No safe no-follow primitive: fail closed rather than read a link target.
            return None
        descriptors.append(fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 200_000:
            return None
        return os.read(fd, limit)
    except OSError:
        return None
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def scan_safe(path: Path, policy: ScanPolicy) -> list[tuple[str, os.stat_result]]:
    """List directory metadata through a no-follow descriptor, including race protection."""
    path = absolute(path)
    if not policy.allows(path) or os.open not in os.supports_dir_fd or not hasattr(os, "O_NOFOLLOW"):
        return []
    descriptors = []
    try:
        fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
        descriptors.append(fd)
        for part in path.parts[1:]:
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            descriptors.append(fd)
        result = []
        with os.scandir(fd) as entries:
            for entry in entries:
                if policy.excluded(path / entry.name):
                    continue  # do not even lstat an excluded child
                try:
                    result.append((entry.name, entry.stat(follow_symlinks=False)))
                except OSError:
                    continue
        return sorted(result, key=lambda item: item[0])
    except OSError:
        return []
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


_ABS_PATH = re.compile(r"(?<![\w:/])(?:/[\w.~-][^\s\"'<>\]\[),;]*|~/[^\s\"'<>\]\[),;]+|[A-Za-z]:[\\/][^\s\"'<>\]\[),;]+)")


def public_text(text: str) -> str:
    """Never render machine-local absolute paths or recognizable secrets."""
    return _ABS_PATH.sub("[local path]", redact(text)[0])


class IgnoreRules:
    def __init__(self, patterns: list[str] | None = None):
        self.patterns = list(DEFAULT_PATTERNS if patterns is None else patterns)
        self.root: Path | None = None
        self.policy = ScanPolicy()
        self._git_specs: dict[Path, GitIgnoreSpec] = {}

    @classmethod
    def load(cls, project_root: Path, global_file: Path | None = None,
             policy: ScanPolicy | None = None) -> "IgnoreRules":
        policy = policy or ScanPolicy()
        policy.require_root(project_root)
        patterns = list(DEFAULT_PATTERNS)
        for f in (global_file, project_root / ".thrashignore"):
            data = read_safe(f, 200_000, policy) if f else None
            if data is not None:
                for line in data.decode("utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        patterns.append(line)
        rules = cls(patterns)
        rules.root, rules.policy = absolute(project_root), policy
        return rules

    def is_ignored(self, relpath: str) -> bool:
        rel = relpath.replace("\\", "/").removeprefix("./")
        parts = [p for p in rel.split("/") if p]
        if rel.startswith("/") or ".." in parts:
            return True
        if self.root and not self.policy.allows(self.root / rel):
            return True
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
                if any(fnmatch.fnmatch(p.lower(), pat.lower()) for p in parts):
                    return True
        if self.root:
            # Walk prefixes in order: an ignored parent cannot be re-included by
            # a nested ignore file, and we never open that parent's ignore file.
            specs = []
            for i, part in enumerate(parts):
                directory = self.root.joinpath(*parts[:i])
                if directory not in self._git_specs:
                    data = read_safe(directory / ".gitignore", 200_000, self.policy)
                    self._git_specs[directory] = GitIgnoreSpec.from_lines(
                        data.decode("utf-8", errors="replace").splitlines() if data else [])
                specs.append((i, self._git_specs[directory]))
                is_dir = i < len(parts) - 1 or rel.endswith("/")
                ignored = False
                for offset, spec in specs:
                    candidate = "/".join(parts[offset:i + 1]) + ("/" if is_dir else "")
                    match = spec.check_file(candidate)
                    if match.include is not None:
                        ignored = match.include
                if ignored:
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
