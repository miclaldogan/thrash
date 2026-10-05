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


def test_generation_requests_resume_fields_without_breaking_old_images(monkeypatch, ctx):
    from thrash.process_image import ProcessImage, ImageMeta
    legacy = ProcessImage(project='game-alpha', program_counter={'task':'resume'},
                          meta=ImageMeta(created_at=1, model='old'))
    def fake(cfg, system, messages, schema=None):
        assert {'summary', 'completed', 'decisions', 'next_action'} <= set(schema['required'])
        assert 'reason' in schema['$defs']['Decision']['required']
        return Reply(GOOD, .1)
    monkeypatch.setattr(extract, 'chat_json', fake)
    image = extract.ollama_extractor(Config())('game-alpha', ctx, legacy, 2)
    assert image.meta.context_version == 2
    assert image.completed == []  # missing evidence is never invented


@pytest.mark.parametrize('choice,reason', [
    ('Reject the remote dependency', 'The device must work disconnected'),
    ('Defer the adapter rewrite', 'The existing adapter is still under review'),
    ('Keep the small enclosure', ''),
])
def test_recorded_intent_survives_model_boundary(monkeypatch,tmp_path,choice,reason):
    """Check the actual extraction boundary, not a simulated semantic score."""
    import json
    root=make_repo(tmp_path/'intent', {'notes.md':f'DECISION: {choice}\nWHY: {reason}\nNEXT: Inspect the prototype\n'})
    context=gather_context(root,Config(),IgnoreRules.load(root),1e9)
    def reply(cfg,system,messages,schema=None):
        user=messages[0]['content']
        assert choice in user and reason in user
        assert 'OUTPUT SCHEMA' in user and 'Supporting file path' in user
        assert 'intentional deferral' in system and 'Do not invent decisions' in system
        return Reply(json.dumps({'program_counter':{'task':'Inspect prototype'},
            'decisions':[{'text':choice,'reason':reason,'source':'notes.md','explicit':True}]}),.1)
    monkeypatch.setattr(extract,'chat_json',reply)
    image=extract.ollama_extractor(Config())('intent',context,None,1e9)
    assert image.decisions[0].text==choice and image.decisions[0].reason==reason
    assert image.decisions[0].explicit


def test_empty_evidence_is_not_populated_by_schema(monkeypatch,ctx):
    import json
    _patch(monkeypatch,[json.dumps({'program_counter':{'task':'Inspect evidence'},'decisions':[],
                                  'completed':[],'last_useful_state':''})])
    image=extract.ollama_extractor(Config())('no-evidence',ctx,None,1e9)
    assert not image.decisions and not image.completed and not image.last_useful_state
