"""
End-to-end integration tests against a live FastAPI server backed by Ollama.

The server is started once per session against a temporary database so no
user data is touched.  All tests in this module are skipped automatically
if Ollama is not reachable.
"""
import json
import uuid

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.ollama]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_sse(text: str) -> list[dict]:
    """Parse SSE response body into a list of data payloads."""
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health_reports_ollama_up(live_server, require_ollama):
    r = httpx.get(f"{live_server}/v1/health", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert data["ollama"] is True
    # Azure endpoint is intentionally broken in the live_server fixture
    assert data["azure"] is False
    assert data["active_provider"] == "ollama"


# ---------------------------------------------------------------------------
# Conversation lifecycle
# ---------------------------------------------------------------------------

def test_create_list_delete_conversation(live_server, require_ollama):
    base = live_server

    # Create
    r = httpx.post(f"{base}/v1/conversations", json={"title": "E2E test", "model": "gpt-5.3-chat"})
    assert r.status_code == 201
    conv = r.json()
    conv_id = conv["id"]
    assert conv["title"] == "E2E test"

    # List
    r = httpx.get(f"{base}/v1/conversations")
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()]
    assert conv_id in ids

    # Get
    r = httpx.get(f"{base}/v1/conversations/{conv_id}")
    assert r.status_code == 200
    assert r.json()["id"] == conv_id
    assert r.json()["messages"] == []

    # Delete
    r = httpx.delete(f"{base}/v1/conversations/{conv_id}")
    assert r.status_code == 204

    r = httpx.get(f"{base}/v1/conversations/{conv_id}")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Non-streaming chat (uses Ollama gemma3:1b as fallback)
# ---------------------------------------------------------------------------

def test_non_streaming_chat_returns_reply(live_server, require_ollama):
    r = httpx.post(
        f"{live_server}/v1/chat/completions",
        json={
            "model": "gpt-5.3-chat",
            "messages": [{"role": "user", "content": "Reply with the single word: yes"}],
            "stream": False,
            "max_tokens": 16,
        },
        timeout=60,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["provider"] == "ollama"
    assert data["message"]["role"] == "assistant"
    assert len(data["message"]["content"]) > 0
    assert "conversation_id" in data
    assert data["usage"]["prompt_tokens"] > 0
    assert data["usage"]["completion_tokens"] > 0
    assert data["usage"]["cost_usd"] == 0.0  # Ollama is free


def test_non_streaming_chat_persists_messages(live_server, require_ollama):
    r = httpx.post(
        f"{live_server}/v1/chat/completions",
        json={
            "model": "gpt-5.3-chat",
            "messages": [{"role": "user", "content": "Say exactly: pong"}],
            "stream": False,
            "max_tokens": 16,
        },
        timeout=60,
    )
    assert r.status_code == 200
    conv_id = r.json()["conversation_id"]

    r = httpx.get(f"{live_server}/v1/conversations/{conv_id}")
    msgs = r.json()["messages"]
    roles = [m["role"] for m in msgs]
    assert "user" in roles
    assert "assistant" in roles


def test_non_streaming_chat_resumes_existing_conversation(live_server, require_ollama):
    # Create a conversation first
    r = httpx.post(f"{live_server}/v1/conversations", json={"title": "Resume test"})
    conv_id = r.json()["id"]

    # Send two turns
    for content in ["First message", "Second message"]:
        r = httpx.post(
            f"{live_server}/v1/chat/completions",
            json={
                "conversation_id": conv_id,
                "model": "gpt-5.3-chat",
                "messages": [{"role": "user", "content": content}],
                "stream": False,
                "max_tokens": 16,
            },
            timeout=60,
        )
        assert r.status_code == 200

    r = httpx.get(f"{live_server}/v1/conversations/{conv_id}")
    msgs = r.json()["messages"]
    user_msgs = [m for m in msgs if m["role"] == "user"]
    assert len(user_msgs) == 2


# ---------------------------------------------------------------------------
# Streaming chat
# ---------------------------------------------------------------------------

def test_streaming_chat_yields_sse_events(live_server, require_ollama):
    r = httpx.post(
        f"{live_server}/v1/chat/completions",
        json={
            "model": "gpt-5.3-chat",
            "messages": [{"role": "user", "content": "Reply with the single word: hi"}],
            "stream": True,
            "max_tokens": 16,
        },
        timeout=60,
    )
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")

    events = parse_sse(r.text)
    types = [e["type"] for e in events]
    assert "delta" in types
    assert "done" in types


def test_streaming_chat_done_event_has_usage(live_server, require_ollama):
    r = httpx.post(
        f"{live_server}/v1/chat/completions",
        json={
            "model": "gpt-5.3-chat",
            "messages": [{"role": "user", "content": "One word reply: ok"}],
            "stream": True,
            "max_tokens": 16,
        },
        timeout=60,
    )
    events = parse_sse(r.text)
    done = next(e for e in events if e["type"] == "done")
    assert done["provider"] == "ollama"
    assert done["usage"]["prompt_tokens"] > 0
    assert done["usage"]["cost_usd"] == 0.0


def test_streaming_chat_persists_assistant_reply(live_server, require_ollama):
    r = httpx.post(
        f"{live_server}/v1/chat/completions",
        json={
            "model": "gpt-5.3-chat",
            "messages": [{"role": "user", "content": "Say: stream-persisted"}],
            "stream": True,
            "max_tokens": 32,
        },
        timeout=60,
    )
    events = parse_sse(r.text)
    done = next(e for e in events if e["type"] == "done")
    conv_id = done["conversation_id"]

    r = httpx.get(f"{live_server}/v1/conversations/{conv_id}")
    msgs = r.json()["messages"]
    assert any(m["role"] == "assistant" for m in msgs)


# ---------------------------------------------------------------------------
# Usage endpoints
# ---------------------------------------------------------------------------

def test_usage_summary_after_chat(live_server, require_ollama):
    httpx.post(
        f"{live_server}/v1/chat/completions",
        json={
            "model": "gpt-5.3-chat",
            "messages": [{"role": "user", "content": "ping"}],
            "stream": False,
            "max_tokens": 8,
        },
        timeout=60,
    )
    r = httpx.get(f"{live_server}/v1/usage")
    assert r.status_code == 200
    data = r.json()
    assert len(data["daily"]) >= 1
    assert len(data["by_model"]) >= 1
    assert data["by_model"][0]["provider"] == "ollama"


def test_conversation_usage_reflects_tokens(live_server, require_ollama):
    r = httpx.post(
        f"{live_server}/v1/chat/completions",
        json={
            "model": "gpt-5.3-chat",
            "messages": [{"role": "user", "content": "ping"}],
            "stream": False,
            "max_tokens": 8,
        },
        timeout=60,
    )
    conv_id = r.json()["conversation_id"]

    r = httpx.get(f"{live_server}/v1/usage/{conv_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["prompt_tokens"] > 0
    assert data["completion_tokens"] > 0


# ---------------------------------------------------------------------------
# gemma3:1b — direct Ollama model request
# ---------------------------------------------------------------------------

def test_direct_ollama_model_chat(live_server, require_ollama):
    """Request gemma3:1b by name (not as a fallback) to test the Ollama-native path."""
    r = httpx.post(
        f"{live_server}/v1/chat/completions",
        json={
            "model": "gemma3:1b",
            "messages": [{"role": "user", "content": "Reply with one word: hello"}],
            "stream": False,
            "max_tokens": 16,
        },
        timeout=60,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["provider"] == "ollama"
    assert data["model"] == "gemma3:1b"
    assert len(data["message"]["content"]) > 0
    assert data["usage"]["cost_usd"] == 0.0


def test_direct_ollama_model_streaming(live_server, require_ollama):
    r = httpx.post(
        f"{live_server}/v1/chat/completions",
        json={
            "model": "gemma3:1b",
            "messages": [{"role": "user", "content": "One word: ok"}],
            "stream": True,
            "max_tokens": 16,
        },
        timeout=60,
    )
    assert r.status_code == 200
    events = parse_sse(r.text)
    done = next((e for e in events if e["type"] == "done"), None)
    assert done is not None
    assert done["provider"] == "ollama"
    assert done["model"] == "gemma3:1b"


def test_direct_ollama_model_usage_is_free(live_server, require_ollama):
    r = httpx.post(
        f"{live_server}/v1/chat/completions",
        json={
            "model": "gemma3:1b",
            "messages": [{"role": "user", "content": "ping"}],
            "stream": False,
            "max_tokens": 8,
        },
        timeout=60,
    )
    assert r.json()["usage"]["cost_usd"] == 0.0


# ---------------------------------------------------------------------------
# Isolation: no bleed between test conversations
# ---------------------------------------------------------------------------

def test_conversations_are_isolated(live_server, require_ollama):
    ids = []
    for _ in range(2):
        r = httpx.post(f"{live_server}/v1/conversations", json={"title": "Isolated"})
        ids.append(r.json()["id"])

    r0 = httpx.get(f"{live_server}/v1/conversations/{ids[0]}")
    r1 = httpx.get(f"{live_server}/v1/conversations/{ids[1]}")
    assert r0.json()["messages"] == []
    assert r1.json()["messages"] == []
