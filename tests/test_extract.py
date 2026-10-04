import pytest

from conftest import make_repo
from thrash import extract
from thrash.config import Config
from thrash.git_context import gather_context
from thrash.ollama_client import Reply
from thrash.privacy import IgnoreRules
from thrash.process_image import ImageError

GOOD = ('{"program_counter":{"task":"rig jaw","confidence":0.9},"open_handles":["README.md","ghost.md"],'
        '"next_action":"rig jaw"}')


@pytest.fixture
def ctx(tmp_path):
    return gather_context(make_repo(tmp_path / "r"), Config(), IgnoreRules(), 1e9)


def _patch(monkeypatch, replies):
    calls = []

    def fake(cfg, system, messages, schema=None, client=None):
        calls.append(messages)
        return Reply(replies[min(len(calls) - 1, len(replies) - 1)], 0.1)

    monkeypatch.setattr(extract, "chat_json", fake)
    return calls


def test_valid_first_try(monkeypatch, ctx):
    calls = _patch(monkeypatch, [GOOD])
    img = extract.ollama_extractor(Config())("proj", ctx, None, 1e9)
    assert img.project == "proj" and img.open_handles == ["README.md"] and img.meta.dropped_paths == 1
    assert len(calls) == 1


def test_one_repair_attempt_then_success(monkeypatch, ctx):
    calls = _patch(monkeypatch, ["sorry, here is some prose", GOOD])
    img = extract.ollama_extractor(Config())("proj", ctx, None, 1e9)
    assert img.program_counter.task == "rig jaw"
    assert len(calls) == 2 and "rejected" in calls[1][-1]["content"]


def test_garbage_twice_raises_and_stores_nothing(monkeypatch, ctx):
    _patch(monkeypatch, ["nope", "{still not json"])
    with pytest.raises(ImageError):
        extract.ollama_extractor(Config())("proj", ctx, None, 1e9)


def test_prompt_contains_alias_not_path(monkeypatch, ctx):
    calls = _patch(monkeypatch, [GOOD])
    extract.ollama_extractor(Config())("game-alpha", ctx, None, 1e9)
    user = calls[0][0]["content"]
    assert "game-alpha" in user and "/tmp/" not in user


def test_invalid_output_keeps_previous_image(kernel, repos, clock):
    from conftest import commit
    kernel.register_project(repos["alpha"], "alpha")
    first = kernel.reg.resolve("alpha")
    commit(repos["alpha"], "more", {"x.md": "y"})

    def bad(*a, **k):
        raise ImageError("model output is not valid JSON")

    kernel._extractor = bad
    snap = kernel.snapshot(first)
    assert snap.error_kind == "invalid" and snap.image is not None  # previous image survives
    assert kernel.load_context(first).image.program_counter.task == "work on alpha"
