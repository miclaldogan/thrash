import os
import subprocess
from pathlib import Path

import pytest

from thrash.config import Config
from thrash.process_image import ImageMeta, ProcessImage
from thrash.scheduler import Kernel


class Clock:
    def __init__(self, t=None):
        self.t = t if t is not None else __import__("time").time()

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def fake_extractor(alias, ctx, previous, now):
    return ProcessImage(
        project=alias,
        program_counter={"task": f"work on {alias}", "confidence": 0.8},
        registers={"engine": "undecided"},
        stack=["a", "b"],
        open_handles=[p for p in ("README.md", "notes.md") if p in ctx.allowed_paths],
        decisions=[{"text": "keep it small", "source": "notes.md"}],
        unresolved=["engine choice"],
        next_action=f"do the next thing in {alias}",
        meta=ImageMeta(created_at=now, model="fake", head=ctx.fingerprint.head, todo_count=ctx.todo_count, ctx_units=100),
    )


def make_repo(path: Path, files=None):
    path.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "-C", str(path), "init", "-q", "-b", "main"], check=True, env=env)
    for name, body in (files or {"README.md": "# demo\n", "notes.md": "- [ ] todo\n"}).items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text(body)
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True, env=env)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "init"], check=True, env=env)
    return path


def commit(path: Path, msg: str, files: dict):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for name, body in files.items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text(body)
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True, env=env)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", msg], check=True, env=env)


@pytest.fixture
def cfg(tmp_path):
    c = Config(data_dir=tmp_path / "data")
    c.ensure_dirs()
    return c


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def kernel(cfg, clock):
    return Kernel(cfg, extractor=fake_extractor, clock=clock)


@pytest.fixture
def repos(tmp_path):
    return {n: make_repo(tmp_path / "work" / n) for n in ("alpha", "beta", "gamma")}


@pytest.fixture
def kernel3(kernel, repos):
    for n, p in repos.items():
        kernel.register_project(p, n)
    return kernel
