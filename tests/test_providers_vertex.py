import json
import pytest
import respx
import httpx
from unittest.mock import patch, MagicMock

import src.backend.providers.vertex as vertex_mod

FAKE_PROJECT = "test-project"
FAKE_REGION = "us-south1"
FAKE_TOKEN = "fake-token"


@pytest.fixture(autouse=True)
def set_vertex_env(monkeypatch):
    monkeypatch.setattr(vertex_mod, "_PROJECT_OVERRIDE", FAKE_PROJECT)
    monkeypatch.setattr(vertex_mod, "_REGION_OVERRIDE", FAKE_REGION)
    monkeypatch.setattr(vertex_mod, "_ENDPOINT_OVERRIDE", "")


@pytest.fixture(autouse=True)
def mock_token(monkeypatch):
    monkeypatch.setattr(vertex_mod, "_get_token", lambda: FAKE_TOKEN)


def _predict_url() -> str:
    return (
        f"https://{FAKE_REGION}-aiplatform.googleapis.com/v1"
        f"/projects/{FAKE_PROJECT}/locations/{FAKE_REGION}"
        f"/publishers/{vertex_mod.PUBLISHER}/models/{vertex_mod.MODEL_NAME}:rawPredict"
    )


def _stream_url() -> str:
    return (
        f"https://{FAKE_REGION}-aiplatform.googleapis.com/v1"
        f"/projects/{FAKE_PROJECT}/locations/{FAKE_REGION}"
        f"/publishers/{vertex_mod.PUBLISHER}/models/{vertex_mod.MODEL_NAME}:streamRawPredict"
    )


def _endpoint_predict_url(endpoint_id: str) -> str:
    return (
        f"https://{FAKE_REGION}-aiplatform.googleapis.com/v1"
        f"/projects/{FAKE_PROJECT}/locations/{FAKE_REGION}"
        f"/endpoints/{endpoint_id}:rawPredict"
    )


def _endpoint_stream_url(endpoint_id: str) -> str:
    return (
        f"https://{FAKE_REGION}-aiplatform.googleapis.com/v1"
        f"/projects/{FAKE_PROJECT}/locations/{FAKE_REGION}"
        f"/endpoints/{endpoint_id}:streamRawPredict"
    )


# --- URL construction ---

def test_publisher_url_when_no_endpoint_id():
    assert vertex_mod._predict_url() == _predict_url()
    assert vertex_mod._stream_url() == _stream_url()


def test_endpoint_url_when_endpoint_id_set(monkeypatch):
    monkeypatch.setattr(vertex_mod, "_ENDPOINT_OVERRIDE", "123456789")
    assert vertex_mod._predict_url() == _endpoint_predict_url("123456789")
    assert vertex_mod._stream_url() == _endpoint_stream_url("123456789")


# --- health_check ---

@respx.mock
async def test_health_check_success():
    respx.post(_predict_url()).respond(200, json={"choices": []})
    assert await vertex_mod.health_check() is True


@respx.mock
async def test_health_check_404_is_unhealthy():
    # 404 = quota pending / model not accessible; treated as unhealthy
    respx.post(_predict_url()).respond(404, json={"error": {"code": 404}})
    assert await vertex_mod.health_check() is False


@respx.mock
async def test_health_check_403_is_unhealthy():
    respx.post(_predict_url()).respond(403, json={})
    assert await vertex_mod.health_check() is False


@respx.mock
async def test_health_check_400_is_healthy():
    # 400 = model up, bad request (e.g. empty messages) — still reachable
    respx.post(_predict_url()).respond(400, json={})
    assert await vertex_mod.health_check() is True


@respx.mock
async def test_health_check_500_is_unhealthy():
    respx.post(_predict_url()).respond(500, json={})
    assert await vertex_mod.health_check() is False


@respx.mock
async def test_health_check_network_error():
    respx.post(_predict_url()).mock(side_effect=httpx.ConnectError("refused"))
    assert await vertex_mod.health_check() is False


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
    respx.post(_stream_url()).respond(
        200, content=body, headers={"content-type": "text/event-stream"}
    )

    chunks = []
    async for chunk in vertex_mod.stream_chat("", [{"role": "user", "content": "hi"}]):
        chunks.append(chunk)

    deltas = [c for c in chunks if c["type"] == "delta"]
    usage  = [c for c in chunks if c["type"] == "usage"]
    assert [d["content"] for d in deltas] == ["Hello", " world"]
    assert usage[0]["prompt_tokens"] == 10
    assert usage[0]["completion_tokens"] == 5


@respx.mock
async def test_stream_chat_http_error():
    respx.post(_stream_url()).respond(400, content=b"bad request")

    chunks = []
    async for chunk in vertex_mod.stream_chat("", []):
        chunks.append(chunk)

    assert chunks[0]["type"] == "error"
    assert "400" in chunks[0]["message"]


@respx.mock
async def test_stream_chat_network_error():
    respx.post(_stream_url()).mock(side_effect=httpx.ConnectError("refused"))

    chunks = []
    async for chunk in vertex_mod.stream_chat("", []):
        chunks.append(chunk)

    assert chunks[0]["type"] == "error"


@respx.mock
async def test_stream_chat_skips_non_data_lines():
    body = b": keepalive\n\ndata: [DONE]\n\n"
    respx.post(_stream_url()).respond(
        200, content=body, headers={"content-type": "text/event-stream"}
    )
    chunks = []
    async for chunk in vertex_mod.stream_chat("", []):
        chunks.append(chunk)
    assert not any(c["type"] == "delta" for c in chunks)


@respx.mock
async def test_stream_chat_500_falls_back_to_non_streaming():
    fallback_body = {
        "choices": [{"message": {"content": "fallback response"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3},
    }
    # First call (streaming) returns 500; second call (rawPredict fallback) returns 200
    respx.post(_stream_url()).respond(500, content=b"error")
    respx.post(_predict_url()).respond(200, json=fallback_body)

    chunks = []
    async for chunk in vertex_mod.stream_chat("", [{"role": "user", "content": "hi"}]):
        chunks.append(chunk)

    deltas = [c for c in chunks if c["type"] == "delta"]
    assert deltas[0]["content"] == "fallback response"


# --- call_with_tools ---

@respx.mock
async def test_call_with_tools_returns_message():
    msg = {"role": "assistant", "content": "result", "tool_calls": None}
    respx.post(_predict_url()).respond(200, json={"choices": [{"message": msg}]})

    result = await vertex_mod.call_with_tools("", [], [])
    assert result["content"] == "result"


@respx.mock
async def test_call_with_tools_raises_on_error():
    respx.post(_predict_url()).respond(500, content=b"server error")

    with pytest.raises(RuntimeError, match="500"):
        await vertex_mod.call_with_tools("", [], [])
