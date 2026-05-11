import json
import pytest
import respx
import httpx
from unittest.mock import patch, MagicMock

import src.backend.providers.ollama as ollama_mod
from src.backend.providers.ollama import _normalize_messages


@pytest.fixture(autouse=True)
def reset_base(monkeypatch):
    monkeypatch.setattr(ollama_mod, "OLLAMA_BASE", "http://localhost:11434")


# --- health_check ---

@respx.mock
async def test_health_check_success():
    respx.get("http://localhost:11434/api/tags").respond(200, json={})
    assert await ollama_mod.health_check() is True


@respx.mock
async def test_health_check_failure():
    respx.get("http://localhost:11434/api/tags").respond(500)
    assert await ollama_mod.health_check() is False


@respx.mock
async def test_health_check_network_error():
    respx.get("http://localhost:11434/api/tags").mock(side_effect=httpx.ConnectError("refused"))
    assert await ollama_mod.health_check() is False


# --- ensure_model ---

@respx.mock
async def test_ensure_model_already_present():
    respx.get("http://localhost:11434/api/tags").respond(
        200, json={"models": [{"name": "gemma3:1b"}]}
    )
    # Should return without calling Popen
    with patch("src.backend.providers.ollama.subprocess.Popen") as mock_popen:
        await ollama_mod.ensure_model("gemma3:1b")
        mock_popen.assert_not_called()


@respx.mock
async def test_ensure_model_triggers_pull_when_missing():
    respx.get("http://localhost:11434/api/tags").respond(200, json={"models": []})
    with patch("src.backend.providers.ollama.subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock()
        await ollama_mod.ensure_model("gemma3:1b")
        mock_popen.assert_called_once()


@respx.mock
async def test_ensure_model_silences_errors():
    respx.get("http://localhost:11434/api/tags").mock(side_effect=httpx.ConnectError("refused"))
    # Should not raise
    await ollama_mod.ensure_model("gemma3:1b")


# --- stream_chat ---

def _ollama_chunks(texts: list[str]) -> bytes:
    lines = []
    for i, t in enumerate(texts):
        done = i == len(texts) - 1
        chunk = {
            "message": {"content": t},
            "done": done,
        }
        if done:
            chunk["prompt_eval_count"] = 8
            chunk["eval_count"] = 4
        lines.append(json.dumps(chunk) + "\n")
    return "".join(lines).encode()


@respx.mock
async def test_stream_chat_yields_deltas_and_usage():
    body = _ollama_chunks(["Hi", " there"])
    respx.post("http://localhost:11434/api/chat").respond(
        200, content=body, headers={"content-type": "application/x-ndjson"}
    )

    chunks = []
    async for chunk in ollama_mod.stream_chat("gemma3:1b", [{"role": "user", "content": "hello"}]):
        chunks.append(chunk)

    deltas = [c for c in chunks if c["type"] == "delta"]
    usage  = [c for c in chunks if c["type"] == "usage"]
    assert [d["content"] for d in deltas] == ["Hi", " there"]
    assert usage[0]["prompt_tokens"] == 8
    assert usage[0]["completion_tokens"] == 4


@respx.mock
async def test_stream_chat_http_error():
    respx.post("http://localhost:11434/api/chat").respond(500, content=b"error")

    chunks = []
    async for chunk in ollama_mod.stream_chat("gemma3:1b", []):
        chunks.append(chunk)

    assert chunks[0]["type"] == "error"
    assert "500" in chunks[0]["message"]


@respx.mock
async def test_stream_chat_network_error():
    respx.post("http://localhost:11434/api/chat").mock(side_effect=httpx.ConnectError("refused"))

    chunks = []
    async for chunk in ollama_mod.stream_chat("gemma3:1b", []):
        chunks.append(chunk)

    assert chunks[0]["type"] == "error"


@respx.mock
async def test_stream_chat_skips_empty_lines():
    body = b"\n\n" + _ollama_chunks(["ok"])
    respx.post("http://localhost:11434/api/chat").respond(200, content=body)

    chunks = []
    async for chunk in ollama_mod.stream_chat("gemma3:1b", []):
        chunks.append(chunk)

    deltas = [c for c in chunks if c["type"] == "delta"]
    assert deltas[0]["content"] == "ok"


@respx.mock
async def test_stream_chat_no_content_in_delta():
    body = json.dumps({"message": {"content": ""}, "done": True,
                       "prompt_eval_count": 1, "eval_count": 1}) + "\n"
    respx.post("http://localhost:11434/api/chat").respond(200, content=body.encode())

    chunks = []
    async for chunk in ollama_mod.stream_chat("gemma3:1b", []):
        chunks.append(chunk)

    assert not any(c["type"] == "delta" for c in chunks)
    assert any(c["type"] == "usage" for c in chunks)


# --- _normalize_messages ---

def test_normalize_null_content_becomes_empty_string():
    msgs = [{"role": "assistant", "content": None, "tool_calls": []}]
    result = _normalize_messages(msgs)
    assert result[0]["content"] == ""


def test_normalize_string_arguments_become_dict():
    msgs = [{
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": "tc1",
            "type": "function",
            "function": {"name": "get_datetime", "arguments": '{"timezone": "UTC"}'},
        }],
    }]
    result = _normalize_messages(msgs)
    args = result[0]["tool_calls"][0]["function"]["arguments"]
    assert isinstance(args, dict)
    assert args == {"timezone": "UTC"}


def test_normalize_dict_arguments_unchanged():
    msgs = [{
        "role": "assistant",
        "content": "",
        "tool_calls": [{
            "id": "tc1",
            "type": "function",
            "function": {"name": "foo", "arguments": {"key": "val"}},
        }],
    }]
    result = _normalize_messages(msgs)
    assert result[0]["tool_calls"][0]["function"]["arguments"] == {"key": "val"}


def test_normalize_invalid_json_arguments_become_empty_dict():
    msgs = [{
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": "tc1", "type": "function",
                        "function": {"name": "foo", "arguments": "not-json"}}],
    }]
    result = _normalize_messages(msgs)
    assert result[0]["tool_calls"][0]["function"]["arguments"] == {}


def test_normalize_does_not_mutate_original():
    original = {"role": "assistant", "content": None, "tool_calls": []}
    _normalize_messages([original])
    assert original["content"] is None  # untouched


# --- call_with_tools ---

@respx.mock
async def test_call_with_tools_returns_message_with_string_args():
    # Ollama returns arguments as a dict; call_with_tools must re-serialize to string
    msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{
            "id": "tc1",
            "type": "function",
            "function": {"name": "get_datetime", "arguments": {"timezone": "UTC"}},
        }],
    }
    respx.post("http://localhost:11434/api/chat").respond(200, json={"message": msg})

    result = await ollama_mod.call_with_tools("gemma3:1b", [], [])
    args = result["tool_calls"][0]["function"]["arguments"]
    assert isinstance(args, str)
    assert json.loads(args) == {"timezone": "UTC"}


@respx.mock
async def test_call_with_tools_http_error():
    respx.post("http://localhost:11434/api/chat").respond(500, content=b"error")
    with pytest.raises(RuntimeError, match="500"):
        await ollama_mod.call_with_tools("gemma3:1b", [], [])
