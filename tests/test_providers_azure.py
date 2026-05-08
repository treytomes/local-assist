import json
import pytest
import respx
import httpx

import src.backend.providers.azure as azure_mod


@pytest.fixture(autouse=True)
def set_azure_env(monkeypatch):
    monkeypatch.setattr(azure_mod, "ENDPOINT", "https://fake.openai.azure.com/openai/v1")
    monkeypatch.setattr(azure_mod, "API_KEY", "test-key")


# --- health_check ---

@respx.mock
async def test_health_check_success():
    respx.get("https://fake.openai.azure.com/openai/v1/models").respond(200, json={})
    assert await azure_mod.health_check() is True


@respx.mock
async def test_health_check_failure_status():
    respx.get("https://fake.openai.azure.com/openai/v1/models").respond(401)
    assert await azure_mod.health_check() is False


@respx.mock
async def test_health_check_network_error():
    respx.get("https://fake.openai.azure.com/openai/v1/models").mock(
        side_effect=httpx.ConnectError("refused")
    )
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
    respx.post("https://fake.openai.azure.com/openai/v1/chat/completions").respond(
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
    respx.post("https://fake.openai.azure.com/openai/v1/chat/completions").respond(
        500, content=b"Internal Server Error"
    )

    chunks = []
    async for chunk in azure_mod.stream_chat("gpt-5.3-chat", []):
        chunks.append(chunk)

    assert chunks[0]["type"] == "error"
    assert "500" in chunks[0]["message"]


@respx.mock
async def test_stream_chat_network_error():
    respx.post("https://fake.openai.azure.com/openai/v1/chat/completions").mock(
        side_effect=httpx.ConnectError("refused")
    )

    chunks = []
    async for chunk in azure_mod.stream_chat("gpt-5.3-chat", []):
        chunks.append(chunk)

    assert chunks[0]["type"] == "error"


@respx.mock
async def test_stream_chat_skips_malformed_json():
    body = b"data: not-json\n\ndata: [DONE]\n\n"
    respx.post("https://fake.openai.azure.com/openai/v1/chat/completions").respond(
        200, content=body, headers={"content-type": "text/event-stream"}
    )
    chunks = []
    async for chunk in azure_mod.stream_chat("gpt-5.3-chat", []):
        chunks.append(chunk)
    assert not any(c["type"] == "delta" for c in chunks)


@respx.mock
async def test_stream_chat_skips_non_data_lines():
    body = b": comment\n\ndata: [DONE]\n\n"
    respx.post("https://fake.openai.azure.com/openai/v1/chat/completions").respond(
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
    respx.post("https://fake.openai.azure.com/openai/v1/embeddings").respond(
        200, json={"data": [{"embedding": vector}]}
    )
    result = await azure_mod.get_embedding("test text")
    assert result == vector
    assert len(result) == 1536
