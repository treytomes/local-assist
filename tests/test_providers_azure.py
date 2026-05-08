import json
import pytest
import respx
import httpx

import src.backend.providers.azure as azure_mod

FAKE_BASE = "https://fake.cognitiveservices.azure.com"
FAKE_API_VER = "2024-08-01-preview"


@pytest.fixture(autouse=True)
def set_azure_env(monkeypatch):
    monkeypatch.setattr(azure_mod, "_INFERENCE_BASE", FAKE_BASE)
    monkeypatch.setattr(azure_mod, "API_KEY", "test-key")
    monkeypatch.setattr(azure_mod, "API_VER", FAKE_API_VER)


def _chat_url(model: str) -> str:
    return f"{FAKE_BASE}/openai/deployments/{model}/chat/completions?api-version={FAKE_API_VER}"


def _embed_url() -> str:
    return f"{FAKE_BASE}/openai/deployments/{azure_mod.EMBEDDING_MODEL}/embeddings?api-version={FAKE_API_VER}"


# --- health_check ---

@respx.mock
async def test_health_check_success():
    respx.post(_chat_url("gpt-5.3-chat")).respond(200, json={})
    assert await azure_mod.health_check() is True


@respx.mock
async def test_health_check_4xx_is_reachable():
    # A 4xx (e.g. rate limit, bad request) still means Azure is up
    respx.post(_chat_url("gpt-5.3-chat")).respond(400, json={})
    assert await azure_mod.health_check() is True


@respx.mock
async def test_health_check_5xx_returns_false():
    respx.post(_chat_url("gpt-5.3-chat")).respond(500, json={})
    assert await azure_mod.health_check() is False


@respx.mock
async def test_health_check_network_error():
    respx.post(_chat_url("gpt-5.3-chat")).mock(side_effect=httpx.ConnectError("refused"))
    assert await azure_mod.health_check() is False


# --- stream_chat ---

def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _make_sse_body(deltas: list[str], usage: dict) -> bytes:
    lines = []
    for text in deltas:
        lines.append(_sse({"choices": [{"delta": {"content": text}}]}))
    lines.append(_sse({"usage": usage}))
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


@respx.mock
async def test_stream_chat_yields_deltas_and_usage():
    body = _make_sse_body(["Hello", " world"], {"prompt_tokens": 10, "completion_tokens": 5})
    respx.post(_chat_url("gpt-5.3-chat")).respond(
        200, content=body, headers={"content-type": "text/event-stream"}
    )

    chunks = []
    async for chunk in azure_mod.stream_chat("gpt-5.3-chat", [{"role": "user", "content": "hi"}]):
        chunks.append(chunk)

    deltas = [c for c in chunks if c["type"] == "delta"]
    usage  = [c for c in chunks if c["type"] == "usage"]
    assert [d["content"] for d in deltas] == ["Hello", " world"]
    assert usage[0]["prompt_tokens"] == 10
    assert usage[0]["completion_tokens"] == 5


@respx.mock
async def test_stream_chat_http_error():
    respx.post(_chat_url("gpt-5.3-chat")).respond(500, content=b"Internal Server Error")

    chunks = []
    async for chunk in azure_mod.stream_chat("gpt-5.3-chat", []):
        chunks.append(chunk)

    assert chunks[0]["type"] == "error"
    assert "500" in chunks[0]["message"]


@respx.mock
async def test_stream_chat_network_error():
    respx.post(_chat_url("gpt-5.3-chat")).mock(side_effect=httpx.ConnectError("refused"))

    chunks = []
    async for chunk in azure_mod.stream_chat("gpt-5.3-chat", []):
        chunks.append(chunk)

    assert chunks[0]["type"] == "error"


@respx.mock
async def test_stream_chat_skips_malformed_json():
    body = b"data: not-json\n\ndata: [DONE]\n\n"
    respx.post(_chat_url("gpt-5.3-chat")).respond(
        200, content=body, headers={"content-type": "text/event-stream"}
    )
    chunks = []
    async for chunk in azure_mod.stream_chat("gpt-5.3-chat", []):
        chunks.append(chunk)
    assert not any(c["type"] == "delta" for c in chunks)


@respx.mock
async def test_stream_chat_skips_non_data_lines():
    body = b": comment\n\ndata: [DONE]\n\n"
    respx.post(_chat_url("gpt-5.3-chat")).respond(
        200, content=body, headers={"content-type": "text/event-stream"}
    )
    chunks = []
    async for chunk in azure_mod.stream_chat("gpt-5.3-chat", []):
        chunks.append(chunk)
    assert chunks == []


# --- get_embedding ---

@respx.mock
async def test_get_embedding_returns_vector():
    vector = [0.1] * 1536
    respx.post(_embed_url()).respond(200, json={"data": [{"embedding": vector}]})
    result = await azure_mod.get_embedding("test text")
    assert result == vector
    assert len(result) == 1536
