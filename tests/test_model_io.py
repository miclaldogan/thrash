import httpx
import pytest

from thrash.config import Config
from thrash.extract import sanitize
from thrash.ollama_client import ModelMissing, OllamaUnavailable, check_ready
from thrash.process_image import ImageError, parse_model_json

GOOD = '{"program_counter":{"task":"rig jaw","confidence":0.9},"registers":{"engine":"undecided"},"stack":["a"],"next_action":"rig jaw"}'


def test_parse_good_and_fenced():
    assert parse_model_json(GOOD).program_counter.task == "rig jaw"
    assert parse_model_json("here you go:\n```json\n" + GOOD + "\n```").next_action == "rig jaw"


def test_parse_tolerates_small_model_shapes():
    out = parse_model_json('{"program_counter":"x","registers":[{"name":"a","value":"b"}],"decisions":["d"],"stack":"one","next_action":"n"}')
    assert out.registers == {"a": "b"} and out.decisions[0].text == "d" and out.stack == ["one"]


def test_confidence_clamped():
    assert parse_model_json(GOOD.replace("0.9", "7")).program_counter.confidence == 1.0


@pytest.mark.parametrize("raw", ["", "no json here", "{broken", "[1,2]", '{"stack": []}', '{"program_counter":{"task":""},"next_action":""}'])
def test_malformed_rejected(raw):
    with pytest.raises(ImageError):
        parse_model_json(raw)


def test_sanitize_drops_invented_paths():
    out = parse_model_json('{"program_counter":{"task":"t"},"open_handles":["real.md","ghost.md"],'
                           '"decisions":[{"text":"d","source":"ghost.md"}],"next_action":"n"}')
    out, dropped = sanitize(out, {"real.md"})
    assert out.open_handles == ["real.md"] and dropped == 2
    assert out.decisions[0].source == "" and out.decisions[0].explicit is False


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ollama_down():
    def boom(req):
        raise httpx.ConnectError("refused")
    with pytest.raises(OllamaUnavailable, match="did not respond"):
        check_ready(Config(), _client(boom))


def test_model_missing():
    c = _client(lambda req: httpx.Response(200, json={"models": [{"name": "llama3:8b"}]}))
    with pytest.raises(ModelMissing):
        check_ready(Config(model="gemma3:4b"), c)


def test_model_present():
    c = _client(lambda req: httpx.Response(200, json={"models": [{"name": "gemma3:4b"}]}))
    check_ready(Config(model="gemma3:4b"), c)
