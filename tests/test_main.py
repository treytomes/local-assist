import json
import pytest
from unittest.mock import AsyncMock, patch

import src.backend.router as router_mod


# Helper: build an async generator from a list of chunks
async def _fake_stream(chunks: list[dict]):
    for c in chunks:
        yield c


GOOD_STREAM = [
    {"type": "delta",  "content": "Hello"},
    {"type": "delta",  "content": " world"},
    {"type": "usage",  "prompt_tokens": 10, "completion_tokens": 5},
]

ERROR_STREAM = [
    {"type": "error", "message": "upstream failure"},
]


@pytest.fixture(autouse=True)
def patch_router(monkeypatch):
    """Default: Azure healthy, stream returns GOOD_STREAM."""
    async def fake_stream_chat(model, messages, max_tokens=2048, temperature=0.7):
        return "azure", model, _fake_stream(GOOD_STREAM)

    monkeypatch.setattr(router_mod, "stream_chat", fake_stream_chat)
    monkeypatch.setattr(router_mod, "get_health", AsyncMock(return_value={
        "azure": True, "ollama": False, "active_provider": "azure"
    }))


# --- /v1/health ---

async def test_health_endpoint(async_client):
    resp = await async_client.get("/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "azure" in data
    assert "active_provider" in data


# --- /v1/conversations ---

async def test_list_conversations_empty(async_client):
    resp = await async_client.get("/v1/conversations")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_conversation(async_client):
    resp = await async_client.post("/v1/conversations", json={"title": "My chat", "model": "gpt-5.3-chat"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "My chat"
    assert "id" in data


async def test_create_conversation_defaults(async_client):
    resp = await async_client.post("/v1/conversations", json={})
    assert resp.status_code == 201
    assert resp.json()["title"] == "New conversation"


async def test_get_conversation(async_client):
    create_resp = await async_client.post("/v1/conversations", json={"title": "Details"})
    conv_id = create_resp.json()["id"]
    resp = await async_client.get(f"/v1/conversations/{conv_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == conv_id
    assert "messages" in data


async def test_get_conversation_not_found(async_client):
    resp = await async_client.get("/v1/conversations/nonexistent-id")
    assert resp.status_code == 404


async def test_delete_conversation(async_client):
    create_resp = await async_client.post("/v1/conversations", json={"title": "To delete"})
    conv_id = create_resp.json()["id"]
    resp = await async_client.delete(f"/v1/conversations/{conv_id}")
    assert resp.status_code == 204
    get_resp = await async_client.get(f"/v1/conversations/{conv_id}")
    assert get_resp.status_code == 404


async def test_list_conversations_after_create(async_client):
    await async_client.post("/v1/conversations", json={"title": "A"})
    await async_client.post("/v1/conversations", json={"title": "B"})
    resp = await async_client.get("/v1/conversations")
    assert len(resp.json()) == 2


# --- /v1/conversations/{id}/embed ---

async def test_embed_conv_not_found(async_client):
    resp = await async_client.post("/v1/conversations/bad-id/embed")
    assert resp.status_code == 404


async def test_embed_conv_ok(async_client):
    create_resp = await async_client.post("/v1/conversations", json={"title": "Embed me"})
    conv_id = create_resp.json()["id"]
    with patch("src.backend.main.embed_conversation", new=AsyncMock(return_value=None)):
        resp = await async_client.post(f"/v1/conversations/{conv_id}/embed")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# --- /v1/chat/completions (non-streaming) ---

async def test_chat_non_streaming(async_client):
    resp = await async_client.post("/v1/chat/completions", json={
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"]["content"] == "Hello world"
    assert data["usage"]["prompt_tokens"] == 10
    assert "conversation_id" in data


async def test_chat_non_streaming_with_conv_id(async_client):
    create_resp = await async_client.post("/v1/conversations", json={"title": "Existing"})
    conv_id = create_resp.json()["id"]
    resp = await async_client.post("/v1/chat/completions", json={
        "conversation_id": conv_id,
        "messages": [{"role": "user", "content": "ping"}],
        "stream": False,
    })
    assert resp.status_code == 200
    assert resp.json()["conversation_id"] == conv_id


async def test_chat_non_streaming_error_stream(async_client, monkeypatch):
    async def fake_error_stream(model, messages, max_tokens=2048, temperature=0.7):
        return "azure", model, _fake_stream(ERROR_STREAM)
    monkeypatch.setattr(router_mod, "stream_chat", fake_error_stream)

    resp = await async_client.post("/v1/chat/completions", json={
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
    })
    assert resp.status_code == 502


async def test_chat_no_user_message(async_client):
    resp = await async_client.post("/v1/chat/completions", json={
        "messages": [{"role": "assistant", "content": "I go first"}],
        "stream": False,
    })
    assert resp.status_code == 200


# --- /v1/chat/completions (streaming SSE) ---

async def test_chat_streaming_yields_sse(async_client):
    resp = await async_client.post("/v1/chat/completions", json={
        "messages": [{"role": "user", "content": "stream me"}],
        "stream": True,
    })
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    text = resp.text
    assert "delta" in text
    assert "done" in text


async def test_chat_streaming_error(async_client, monkeypatch):
    async def fake_error_stream(model, messages, max_tokens=2048, temperature=0.7):
        return "azure", model, _fake_stream(ERROR_STREAM)
    monkeypatch.setattr(router_mod, "stream_chat", fake_error_stream)

    resp = await async_client.post("/v1/chat/completions", json={
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
    })
    assert resp.status_code == 200
    assert "error" in resp.text


# --- /v1/usage ---

async def test_usage_summary_empty(async_client):
    resp = await async_client.get("/v1/usage")
    assert resp.status_code == 200
    data = resp.json()
    assert "daily" in data
    assert "by_model" in data


async def test_usage_per_conversation(async_client):
    create_resp = await async_client.post("/v1/conversations", json={"title": "Usage test"})
    conv_id = create_resp.json()["id"]
    resp = await async_client.get(f"/v1/usage/{conv_id}")
    assert resp.status_code == 200


async def test_usage_summary_days_param(async_client):
    resp = await async_client.get("/v1/usage?days=7")
    assert resp.status_code == 200


# --- /v1/context ---

async def test_get_context(async_client):
    with patch("src.backend.main.retrieve_context", new=AsyncMock(return_value=[])):
        resp = await async_client.get("/v1/context?query=hello")
    assert resp.status_code == 200
    assert resp.json()["chunks"] == []


async def test_get_context_with_exclude(async_client):
    with patch("src.backend.main.retrieve_context", new=AsyncMock(return_value=[])) as mock_rc:
        resp = await async_client.get("/v1/context?query=test&exclude_conv_id=abc")
    assert resp.status_code == 200
    call_kwargs = mock_rc.call_args
    assert call_kwargs[0][2] == "abc" or call_kwargs[1].get("exclude_conv_id") == "abc"
