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
    """Default: Azure healthy, stream returns GOOD_STREAM, tool probe returns no tool calls."""
    async def fake_stream_chat(model, messages, max_tokens=2048, temperature=0.7):
        return "azure", model, _fake_stream(GOOD_STREAM)

    async def fake_call_with_tools(model, messages, tools, max_tokens=2048):
        return "azure", model, {"role": "assistant", "content": None, "tool_calls": []}

    monkeypatch.setattr(router_mod, "stream_chat", fake_stream_chat)
    monkeypatch.setattr(router_mod, "call_with_tools", fake_call_with_tools)
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


async def test_patch_conversation_title(async_client):
    create_resp = await async_client.post("/v1/conversations", json={"title": "Old"})
    conv_id = create_resp.json()["id"]
    resp = await async_client.patch(f"/v1/conversations/{conv_id}", json={"title": "New"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "New"


async def test_patch_conversation_model(async_client):
    create_resp = await async_client.post("/v1/conversations", json={"title": "Chat"})
    conv_id = create_resp.json()["id"]
    resp = await async_client.patch(f"/v1/conversations/{conv_id}", json={"model": "Mistral-Large-3"})
    assert resp.status_code == 200
    assert resp.json()["model"] == "Mistral-Large-3"


async def test_patch_conversation_not_found(async_client):
    resp = await async_client.patch("/v1/conversations/bad-id", json={"title": "x"})
    assert resp.status_code == 404


async def test_patch_conversation_no_fields(async_client):
    create_resp = await async_client.post("/v1/conversations", json={"title": "Unchanged"})
    conv_id = create_resp.json()["id"]
    resp = await async_client.patch(f"/v1/conversations/{conv_id}", json={})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Unchanged"


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


async def test_chat_rolling_context_window(async_client, monkeypatch):
    """Messages beyond context_window are truncated before being sent to the model."""
    captured = {}

    async def capturing_stream(model, messages, max_tokens=2048, temperature=0.7):
        captured["messages"] = messages
        return "azure", model, _fake_stream(GOOD_STREAM)

    monkeypatch.setattr(router_mod, "stream_chat", capturing_stream)

    # Send 5 messages but set context_window=2
    msgs = [{"role": "user", "content": f"msg {i}"} for i in range(5)]
    with patch("src.backend.main.retrieve_context", new=AsyncMock(return_value=[])):
        await async_client.post("/v1/chat/completions", json={
            "messages": msgs,
            "stream": False,
            "context_window": 2,
        })
    # +2 for the synthetic reactions injection (tool_call + tool_result)
    assert len(captured["messages"]) == 4


async def test_chat_rolling_window_preserves_system_message(async_client, monkeypatch):
    """A leading system message is always preserved when truncating."""
    captured = {}

    async def capturing_stream(model, messages, max_tokens=2048, temperature=0.7):
        captured["messages"] = messages
        return "azure", model, _fake_stream(GOOD_STREAM)

    monkeypatch.setattr(router_mod, "stream_chat", capturing_stream)

    msgs = [{"role": "system", "content": "sys"}] + [
        {"role": "user", "content": f"msg {i}"} for i in range(5)
    ]
    with patch("src.backend.main.retrieve_context", new=AsyncMock(return_value=[])):
        await async_client.post("/v1/chat/completions", json={
            "messages": msgs,
            "stream": False,
            "context_window": 3,
        })
    assert captured["messages"][0]["role"] == "system"
    # +2 for the synthetic reactions injection (tool_call + tool_result)
    assert len(captured["messages"]) == 5


async def test_chat_rag_context_injected(async_client, monkeypatch):
    """RAG chunks are prepended as a system message when retrieve_context returns results."""
    captured = {}

    async def capturing_stream(model, messages, max_tokens=2048, temperature=0.7):
        captured["messages"] = messages
        return "azure", model, _fake_stream(GOOD_STREAM)

    monkeypatch.setattr(router_mod, "stream_chat", capturing_stream)

    rag_chunks = [{"chunk_text": "Relevant fact from the past."}]
    with patch("src.backend.main.retrieve_context", new=AsyncMock(return_value=rag_chunks)):
        await async_client.post("/v1/chat/completions", json={
            "messages": [{"role": "user", "content": "what do you know?"}],
            "stream": False,
        })

    system_msgs = [m for m in captured["messages"] if m["role"] == "system"]
    assert any("Relevant fact" in m["content"] for m in system_msgs)


async def test_chat_no_rag_when_no_chunks(async_client, monkeypatch):
    """No extra system message is injected when retrieve_context returns nothing."""
    captured = {}

    async def capturing_stream(model, messages, max_tokens=2048, temperature=0.7):
        captured["messages"] = messages
        return "azure", model, _fake_stream(GOOD_STREAM)

    monkeypatch.setattr(router_mod, "stream_chat", capturing_stream)

    with patch("src.backend.main.retrieve_context", new=AsyncMock(return_value=[])):
        await async_client.post("/v1/chat/completions", json={
            "messages": [{"role": "user", "content": "hello"}],
            "stream": False,
        })
    assert not any(
        "past conversations" in (m.get("content") or "") for m in captured["messages"]
    )


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


# --- /v1/pricing ---

async def test_list_pricing(async_client):
    resp = await async_client.get("/v1/pricing")
    assert resp.status_code == 200
    rows = resp.json()
    assert isinstance(rows, list)
    assert len(rows) > 0
    models = {r["model"] for r in rows}
    assert "gpt-5.3-chat" in models


async def test_get_pricing_known(async_client):
    resp = await async_client.get("/v1/pricing/azure/gpt-4o")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "azure"
    assert data["model"] == "gpt-4o"
    assert data["input_cost_per_1k"] == 0.0025


async def test_get_pricing_not_found(async_client):
    resp = await async_client.get("/v1/pricing/azure/nonexistent-model")
    assert resp.status_code == 404


async def test_upsert_pricing_creates(async_client):
    resp = await async_client.post("/v1/pricing/azure/new-test-model", json={
        "input_cost_per_1k": 0.001,
        "output_cost_per_1k": 0.005,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["model"] == "new-test-model"
    assert data["input_cost_per_1k"] == 0.001


async def test_upsert_pricing_updates(async_client):
    await async_client.post("/v1/pricing/azure/gpt-5.3-chat", json={
        "input_cost_per_1k": 0.099,
        "output_cost_per_1k": 0.199,
    })
    resp = await async_client.get("/v1/pricing/azure/gpt-5.3-chat")
    assert resp.json()["input_cost_per_1k"] == 0.099


async def test_upsert_pricing_model_with_slash(async_client):
    """Model names containing colons/slashes (e.g. Ollama) should be routable."""
    resp = await async_client.post("/v1/pricing/ollama/gemma3:1b", json={
        "input_cost_per_1k": 0.0,
        "output_cost_per_1k": 0.0,
    })
    assert resp.status_code == 200
    assert resp.json()["model"] == "gemma3:1b"


# --- /v1/tools ---

async def test_tools_endpoint_returns_list(async_client):
    resp = await async_client.get("/v1/tools")
    assert resp.status_code == 200
    tools = resp.json()
    assert isinstance(tools, list)
    assert len(tools) > 0


async def test_tools_endpoint_shape(async_client):
    resp = await async_client.get("/v1/tools")
    tools = resp.json()
    for t in tools:
        assert "name" in t
        assert "description" in t
        assert "parameters" in t
        assert isinstance(t["parameters"], list)
        assert "required" in t
        assert isinstance(t["required"], list)


async def test_tools_endpoint_includes_expected_tools(async_client):
    resp = await async_client.get("/v1/tools")
    names = {t["name"] for t in resp.json()}
    assert "web_search" in names
    assert "get_datetime" in names
    assert "get_weather" in names


# --- /v1/search/usage ---

async def test_search_usage_endpoint_shape(async_client):
    resp = await async_client.get("/v1/search/usage")
    assert resp.status_code == 200
    data = resp.json()
    assert "calls_used" in data
    assert "limit" in data
    assert "calls_remaining" in data
    assert "days_until_reset" in data
    assert "reset_date" in data


async def test_search_usage_starts_at_zero(async_client):
    resp = await async_client.get("/v1/search/usage")
    data = resp.json()
    assert data["calls_used"] == 0
    assert data["limit"] == 1000
    assert data["calls_remaining"] == 1000


# --- is_retry deduplication ---

async def test_is_retry_does_not_persist_duplicate_user_message(async_client, monkeypatch):
    """When is_retry=True, the user message should not be inserted again."""
    create_resp = await async_client.post("/v1/conversations", json={"title": "Retry test"})
    conv_id = create_resp.json()["id"]

    with patch("src.backend.main.retrieve_context", new=AsyncMock(return_value=[])):
        # First send — persists the user message
        await async_client.post("/v1/chat/completions", json={
            "conversation_id": conv_id,
            "messages": [{"role": "user", "content": "hello"}],
            "stream": False,
        })
        conv_after_first = (await async_client.get(f"/v1/conversations/{conv_id}")).json()
        user_count_after_first = sum(1 for m in conv_after_first["messages"] if m["role"] == "user")

        # Retry — same user message, is_retry=True; must not add another user row
        await async_client.post("/v1/chat/completions", json={
            "conversation_id": conv_id,
            "messages": [{"role": "user", "content": "hello"}],
            "stream": False,
            "is_retry": True,
        })
        conv_after_retry = (await async_client.get(f"/v1/conversations/{conv_id}")).json()
        user_count_after_retry = sum(1 for m in conv_after_retry["messages"] if m["role"] == "user")

    assert user_count_after_retry == user_count_after_first


async def test_is_retry_false_does_persist_user_message(async_client, monkeypatch):
    """Sanity check: is_retry=False (default) always persists the user message."""
    create_resp = await async_client.post("/v1/conversations", json={"title": "Retry false test"})
    conv_id = create_resp.json()["id"]

    with patch("src.backend.main.retrieve_context", new=AsyncMock(return_value=[])):
        await async_client.post("/v1/chat/completions", json={
            "conversation_id": conv_id,
            "messages": [{"role": "user", "content": "first"}],
            "stream": False,
        })
        await async_client.post("/v1/chat/completions", json={
            "conversation_id": conv_id,
            "messages": [{"role": "user", "content": "second"}],
            "stream": False,
        })
        conv = (await async_client.get(f"/v1/conversations/{conv_id}")).json()
        user_msgs = [m for m in conv["messages"] if m["role"] == "user"]

    assert len(user_msgs) == 2
