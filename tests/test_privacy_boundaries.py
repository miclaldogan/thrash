"""Synthetic adversarial fixtures only; never use a real project as test data."""
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import commit, fake_extractor, make_repo
from thrash import cli, git_context as gc
from thrash.config import Config
from thrash.privacy import IgnoreRules
from thrash.scheduler import Kernel


def test_todo_secrets_are_redacted_before_context(tmp_path):
    repo = make_repo(tmp_path / "repo", {
        "TODO.md": "TODO token = SYNTHETIC_TODO_VALUE_12345\n",
        "src.py": "# FIXME password: SYNTHETIC_SOURCE_VALUE_12345\n",
    })
    ctx = gc.gather_context(repo, Config(), IgnoreRules.load(repo), 1e9)
    assert "SYNTHETIC_TODO_VALUE" not in ctx.render()
    assert "SYNTHETIC_SOURCE_VALUE" not in ctx.render()
    assert ctx.redactions >= 2


def test_commit_secrets_are_redacted_before_context_and_drift(tmp_path):
    repo = make_repo(tmp_path / "repo")
    commit(repo, "engine token = SYNTHETIC_COMMIT_VALUE_12345", {"engine.md": "scaffold"})
    ctx = gc.gather_context(repo, Config(), IgnoreRules.load(repo), 1e9)
    assert "SYNTHETIC_COMMIT_VALUE" not in ctx.render()
    assert all("SYNTHETIC_COMMIT_VALUE" not in c.subject for c in gc.recent_commits(repo))


def test_symlinks_never_enter_inventory_or_context(tmp_path):
    repo = make_repo(tmp_path / "repo", {"README.md": "demo", ".env": "SYNTHETIC_ENV_CONTENT"})
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "notes.md").write_text("SYNTHETIC_OUTSIDE_CONTENT")
    (repo / "linked.md").symlink_to(repo / ".env")
    (repo / "external.md").symlink_to(outside / "notes.md")
    (repo / "linked-dir").symlink_to(outside, target_is_directory=True)
    ctx = gc.gather_context(repo, Config(), IgnoreRules.load(repo), 1e9)
    assert not {"linked.md", "external.md", "linked-dir"} & ctx.allowed_paths
    assert "SYNTHETIC_ENV_CONTENT" not in ctx.render()
    assert "SYNTHETIC_OUTSIDE_CONTENT" not in ctx.render()


def test_ignore_file_symlink_is_not_read(tmp_path):
    repo = make_repo(tmp_path / "repo")
    private = tmp_path / "private"
    private.write_text("README.md\n")
    (repo / ".thrashignore").symlink_to(private)
    rules = IgnoreRules.load(repo)
    assert not rules.is_ignored("README.md")


def test_gitignore_applies_even_to_tracked_files(tmp_path):
    repo = make_repo(tmp_path / "repo", {"README.md": "demo", "private.md": "SYNTHETIC_TRACKED_PRIVATE"})
    (repo / ".gitignore").write_text("private.md\n")
    ctx = gc.gather_context(repo, Config(), IgnoreRules.load(repo), 1e9)
    assert "private.md" not in ctx.allowed_paths
    assert "SYNTHETIC_TRACKED_PRIVATE" not in ctx.render()


def test_plain_directory_respects_nested_gitignore(tmp_path):
    root = tmp_path / "plain"
    (root / "notes").mkdir(parents=True)
    (root / ".gitignore").write_text("*.private\n")
    (root / "notes/.gitignore").write_text("hidden.md\n")
    (root / "notes/hidden.md").write_text("SYNTHETIC_HIDDEN")
    (root / "notes/secret.private").write_text("SYNTHETIC_PRIVATE")
    (root / "notes/visible.md").write_text("visible")
    ctx = gc.gather_context(root, Config(), IgnoreRules.load(root), 1e9)
    assert "notes/visible.md" in ctx.allowed_paths
    assert "SYNTHETIC_" not in ctx.render()


def test_excluded_roots_are_rejected_before_any_traversal(tmp_path, monkeypatch):
    from thrash.privacy import ScanPolicy
    from thrash.discovery import discover_projects

    base = tmp_path / "projects"
    excluded = base / "excluded-project"
    excluded.mkdir(parents=True)
    (excluded / "README.md").write_text("NEVER_READ")
    make_repo(base / "allowed")
    (base / "shortcut").symlink_to(excluded, target_is_directory=True)
    policy = ScanPolicy(excluded_roots=(excluded,))
    original_scandir = os.scandir
    original_lstat = Path.lstat

    def guarded_scandir(path):
        if not isinstance(path, int):
            assert not Path(path).is_relative_to(excluded), "excluded tree traversed"
        return original_scandir(path)

    def guarded_lstat(path, *args, **kwargs):
        assert not path.is_relative_to(excluded), "excluded tree inspected"
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(os, "scandir", guarded_scandir)
    monkeypatch.setattr(Path, "lstat", guarded_lstat)
    assert discover_projects(base, policy) == [base / "allowed"]
    cfg = Config(excluded_roots=(excluded,))
    with pytest.raises(ValueError, match="excluded|unsafe"):
        gc.gather_context(excluded, cfg, IgnoreRules(), 1e9)


def test_public_output_masks_paths_in_images_drift_and_storage(tmp_path, monkeypatch):
    repo = make_repo(tmp_path / "private-repository")
    cfg = Config(data_dir=tmp_path / "private-state")

    def private_extractor(alias, ctx, previous, now):
        image = fake_extractor(alias, ctx, previous, now)
        image.program_counter.task = f"resume {repo}/notes.md"
        image.next_action = f"edit {repo}/notes.md"
        return image

    monkeypatch.setattr(cli, "get_kernel", lambda: Kernel(cfg, extractor=private_extractor))
    runner = CliRunner()
    commands = [
        ["init", "--path", str(repo), "--alias", "game-alpha"],
        ["switch", "game-alpha"], ["suspend", "game-alpha"],
        ["wake", "game-alpha"], ["status", "game-alpha"],
        ["ps"], ["top"], ["kill", "game-alpha", "--core"],
        ["resurrect", "game-alpha"],
    ]
    for command in commands:
        result = runner.invoke(cli.app, command)
        assert result.exit_code == 0, result.output
        assert str(tmp_path) not in result.output
        assert "private-repository" not in result.output
        assert "private-state" not in result.output


def test_public_output_aliases_project_name_embedded_in_summary(tmp_path):
    from thrash import ui
    from thrash.process_image import ProcessImage, ImageMeta
    from thrash.registry import Process, State
    proc = Process(pid=1, alias="game-alpha", path=str(tmp_path / "private-identity"), registered_at=0)
    image = ProcessImage(project=proc.alias, program_counter="resume private-identity",
                         next_action="test private-identity", meta=ImageMeta(created_at=0, model="fake"))
    with ui.console.capture() as capture:
        ui.render_status(proc, image, State.READY)
    assert "private-identity" not in capture.get()
    assert "game-alpha" in capture.get()


def test_no_sensitive_files_are_opened_even_by_dirty_detection(tmp_path, monkeypatch):
    repo = make_repo(tmp_path / "repo", {"README.md": "demo", ".env": "NEVER_READ",
                                        "credentials.json": "NEVER_READ", "config.yaml": "NEVER_READ"})
    original = os.open
    opened = []

    def checked_open(path, *args, **kwargs):
        opened.append(str(path))
        assert Path(path).name not in {".env", "credentials.json", "config.yaml"}
        return original(path, *args, **kwargs)

    # Preserve the platform capability test used by the no-follow reader.
    monkeypatch.setattr(os, "supports_dir_fd", os.supports_dir_fd | {checked_open})
    monkeypatch.setattr(os, "open", checked_open)
    ctx = gc.gather_context(repo, Config(), IgnoreRules.load(repo), 1e9)
    assert "NEVER_READ" not in ctx.render()
    assert "README.md" in opened


@pytest.mark.parametrize("name", ["token.json", "server.crt", "settings.py", "private_key.txt", ".npmrc", ".ENV", ".envrc", "client.cert", "key.txt"])
def test_sensitive_filenames_are_excluded(name):
    assert IgnoreRules().is_ignored(name)


def test_symlink_replacement_during_open_cannot_escape(tmp_path, monkeypatch):
    from thrash.privacy import read_safe
    safe = tmp_path / "safe"
    safe.mkdir()
    (safe / "notes.md").write_text("safe")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "notes.md").write_text("NEVER_READ")
    original = os.open
    swapped = False

    def race(path, *args, **kwargs):
        nonlocal swapped
        if path == "safe" and not swapped:
            swapped = True
            safe.rename(tmp_path / "old-safe")
            safe.symlink_to(outside, target_is_directory=True)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, "supports_dir_fd", os.supports_dir_fd | {race})
    monkeypatch.setattr(os, "open", race)
    assert read_safe(safe / "notes.md", 100) is None


def test_directory_swap_cannot_redirect_discovery(tmp_path, monkeypatch):
    from thrash.privacy import scan_safe, ScanPolicy
    root = tmp_path / "safe"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "PRIVATE_NAME").write_text("never read")
    original = os.open

    def race(path, *args, **kwargs):
        if path == "safe":
            root.rename(tmp_path / "old-safe")
            root.symlink_to(outside, target_is_directory=True)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, "supports_dir_fd", os.supports_dir_fd | {race})
    monkeypatch.setattr(os, "open", race)
    assert scan_safe(root, ScanPolicy()) == []


@pytest.mark.parametrize("url", ["https://example.invalid", "http://192.0.2.1:11434", "http://localhost.evil.invalid", "http://user:pass@localhost:11434"])
def test_remote_model_endpoint_rejected_without_connecting(url):
    from thrash.ollama_client import ModelError, check_ready, chat_json
    cfg = Config(ollama_url=url)
    with pytest.raises(ModelError, match="local"):
        check_ready(cfg)
    with pytest.raises(ModelError, match="local"):
        chat_json(cfg, "", [])


def test_loopback_requests_ignore_environment_proxies(monkeypatch):
    from thrash import ollama_client
    seen = []

    def client(**kwargs):
        seen.append(kwargs)
        raise RuntimeError("stop before network")

    monkeypatch.setattr(ollama_client.httpx, "Client", client)
    monkeypatch.setenv("HTTP_PROXY", "http://example.invalid:8080")
    with pytest.raises(RuntimeError):
        ollama_client.check_ready(Config())
    with pytest.raises(RuntimeError):
        ollama_client.chat_json(Config(), "", [])
    assert len(seen) == 2 and all(x["trust_env"] is False for x in seen)


def test_cloud_model_name_is_rejected():
    from thrash.ollama_client import ModelError, local_url
    with pytest.raises(ModelError):
        local_url(Config(model="model:cloud"))


def test_discovery_finds_plain_projects_and_obeys_depth_limit(tmp_path):
    from thrash.discovery import discover_projects
    root = tmp_path / "projects"
    (root / "group/plain").mkdir(parents=True)
    (root / "group/plain/README.md").write_text("synthetic")
    (root / "group/deep/hidden").mkdir(parents=True)
    (root / "group/deep/hidden/README.md").write_text("synthetic")
    assert discover_projects(root, max_depth=2) == [root / "group/plain"]


def test_previously_registered_excluded_root_is_not_scanned(tmp_path, monkeypatch):
    from thrash.registry import RegistryError
    root = make_repo(tmp_path / "excluded")
    cfg = Config(data_dir=tmp_path / "state")
    k = Kernel(cfg, extractor=fake_extractor)
    k.register_project(root, "game-alpha")
    cfg.excluded_roots = (root,)
    original = Path.is_dir

    def guarded(path):
        assert not path.is_relative_to(root)
        return original(path)

    monkeypatch.setattr(Path, "is_dir", guarded)
    assert k.table()[0] == []
    with pytest.raises(RegistryError):
        k.kill_plan("game-alpha")


def test_ignored_only_commits_are_not_summarized(tmp_path):
    repo = make_repo(tmp_path / "repo")
    commit(repo, "PRIVATE_ONLY_SUBJECT", {"secrets.txt": "synthetic"})
    ctx = gc.gather_context(repo, Config(), IgnoreRules.load(repo), 1e9)
    assert "PRIVATE_ONLY_SUBJECT" not in ctx.render()


def test_git_detection_from_subdirectory_still_finds_root(tmp_path):
    repo = make_repo(tmp_path / "repo")
    subdir = repo / "src"
    subdir.mkdir()
    assert gc.toplevel(subdir) == repo
