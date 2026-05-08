"""
Azure contract tests — verify the real Azure endpoints respond in the shape
our code expects.  These make live network calls and cost a small amount of money.

Skipped automatically unless:
  - AZURE_API_KEY and AZURE_OPENAI_ENDPOINT are set in the environment
  - The endpoint does not point to localhost (guard against test overrides)

Run with:  ./test.sh --azure
"""
import os
import pytest

from src.backend.providers import azure as azure_mod

pytestmark = [pytest.mark.integration, pytest.mark.azure]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

async def test_azure_health_check_succeeds(require_azure):
    result = await azure_mod.health_check()
    assert result is True, (
        "Azure health check returned False — check AZURE_API_KEY and AZURE_OPENAI_ENDPOINT"
    )


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

async def test_get_embedding_returns_1536_floats(require_azure):
    vector = await azure_mod.get_embedding("integration test sentence")
    assert isinstance(vector, list), "Expected a list from get_embedding"
    assert len(vector) == 1536, f"Expected 1536 dimensions, got {len(vector)}"
    assert all(isinstance(x, float) for x in vector)


async def test_get_embedding_different_texts_differ(require_azure):
    v1 = await azure_mod.get_embedding("apple")
    v2 = await azure_mod.get_embedding("quantum physics")
    assert v1 != v2, "Different texts should not produce identical embeddings"


# ---------------------------------------------------------------------------
# Streaming chat — gpt-5.3-chat
# ---------------------------------------------------------------------------

async def test_stream_chat_yields_deltas(require_azure):
    chunks = []
    async for chunk in azure_mod.stream_chat(
        "gpt-5.3-chat",
        [{"role": "user", "content": "Reply with the single word: yes"}],
        # gpt-5.3-chat is a reasoning model that consumes tokens internally
        # before emitting output; 200 ensures output is not cut off.
        max_tokens=200,
    ):
        chunks.append(chunk)

    assert not any(c["type"] == "error" for c in chunks), \
        f"Unexpected error chunk: {[c for c in chunks if c['type'] == 'error']}"

    deltas = [c for c in chunks if c["type"] == "delta"]
    assert len(deltas) > 0, "Expected at least one delta chunk"
    full_text = "".join(d["content"] for d in deltas)
    assert len(full_text) > 0


async def test_stream_chat_yields_usage(require_azure):
    chunks = []
    async for chunk in azure_mod.stream_chat(
        "gpt-5.3-chat",
        [{"role": "user", "content": "Hi"}],
        max_tokens=200,
    ):
        chunks.append(chunk)

    usage = [c for c in chunks if c["type"] == "usage"]
    assert len(usage) == 1, "Expected exactly one usage chunk"
    assert usage[0]["prompt_tokens"] > 0
    assert usage[0]["completion_tokens"] > 0


async def test_stream_chat_no_error_chunks(require_azure):
    chunks = []
    async for chunk in azure_mod.stream_chat(
        "gpt-5.3-chat",
        [{"role": "user", "content": "ping"}],
        max_tokens=200,
    ):
        chunks.append(chunk)
    errors = [c for c in chunks if c["type"] == "error"]
    assert errors == [], f"Unexpected errors: {errors}"


# ---------------------------------------------------------------------------
# Streaming chat — Mistral-Large-3
# ---------------------------------------------------------------------------

async def test_mistral_stream_chat_yields_deltas(require_azure):
    chunks = []
    async for chunk in azure_mod.stream_chat(
        "Mistral-Large-3",
        [{"role": "user", "content": "Reply with the single word: ok"}],
        max_tokens=50,
    ):
        chunks.append(chunk)

    deltas = [c for c in chunks if c["type"] == "delta"]
    assert len(deltas) > 0
    assert not any(c["type"] == "error" for c in chunks)


async def test_mistral_usage_chunk_present(require_azure):
    chunks = []
    async for chunk in azure_mod.stream_chat(
        "Mistral-Large-3",
        [{"role": "user", "content": "Hi"}],
        max_tokens=50,
    ):
        chunks.append(chunk)

    usage = [c for c in chunks if c["type"] == "usage"]
    assert len(usage) == 1
    assert usage[0]["prompt_tokens"] > 0


# ---------------------------------------------------------------------------
# Streaming chat — gpt-4o (vision-capable model, text path)
# ---------------------------------------------------------------------------

async def test_gpt4o_stream_chat_yields_deltas(require_azure):
    chunks = []
    async for chunk in azure_mod.stream_chat(
        "gpt-4o",
        [{"role": "user", "content": "Reply with the single word: yes"}],
        max_tokens=50,
    ):
        chunks.append(chunk)

    deltas = [c for c in chunks if c["type"] == "delta"]
    assert len(deltas) > 0
    assert not any(c["type"] == "error" for c in chunks)


async def test_gpt4o_usage_chunk_present(require_azure):
    chunks = []
    async for chunk in azure_mod.stream_chat(
        "gpt-4o",
        [{"role": "user", "content": "Hi"}],
        max_tokens=50,
    ):
        chunks.append(chunk)

    usage = [c for c in chunks if c["type"] == "usage"]
    assert len(usage) == 1
    assert usage[0]["prompt_tokens"] > 0
    assert usage[0]["completion_tokens"] > 0


# ---------------------------------------------------------------------------
# Response shape contracts
# ---------------------------------------------------------------------------

async def test_response_content_is_string(require_azure):
    chunks = []
    async for chunk in azure_mod.stream_chat(
        "gpt-5.3-chat",
        [{"role": "user", "content": "Say: contract"}],
        max_tokens=200,
    ):
        chunks.append(chunk)

    for delta in (c for c in chunks if c["type"] == "delta"):
        assert isinstance(delta["content"], str), \
            f"Delta content should be str, got {type(delta['content'])}"


async def test_chunk_types_are_known_values(require_azure):
    known = {"delta", "usage", "error"}
    chunks = []
    async for chunk in azure_mod.stream_chat(
        "gpt-5.3-chat",
        [{"role": "user", "content": "Hi"}],
        max_tokens=200,
    ):
        chunks.append(chunk)

    for chunk in chunks:
        assert chunk["type"] in known, f"Unknown chunk type: {chunk['type']}"
