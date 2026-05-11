import struct
import pytest
from unittest.mock import AsyncMock, patch

from src.backend.rag import embed_conversation, retrieve_context, _chunk_text, _pack
from src.backend.database import create_conversation, insert_message


FAKE_VECTOR = [0.0] * 1536


# --- _chunk_text ---

def test_chunk_text_short():
    chunks = _chunk_text("hello", chunk_size=500)
    assert chunks == ["hello"]


def test_chunk_text_empty():
    chunks = _chunk_text("", chunk_size=500)
    assert chunks == []


def test_chunk_text_whitespace_only():
    chunks = _chunk_text("   ", chunk_size=500)
    assert chunks == []


def test_chunk_text_splits():
    text = "a" * 1000
    chunks = _chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) > 1
    assert len(chunks[0]) == 500


def test_chunk_text_overlap():
    text = "a" * 600
    chunks = _chunk_text(text, chunk_size=500, overlap=100)
    # First chunk: 0..500, second chunk: 400..600 (len 200)
    assert len(chunks) == 2


# --- _pack ---

def test_pack_returns_bytes():
    v = [1.0, 2.0, 3.0]
    packed = _pack(v)
    assert isinstance(packed, bytes)
    assert len(packed) == 4 * len(v)


def test_pack_roundtrip():
    v = [0.5, -0.5, 1.0]
    packed = _pack(v)
    unpacked = list(struct.unpack(f"{len(v)}f", packed))
    assert [abs(a - b) < 1e-6 for a, b in zip(v, unpacked)]


# --- embed_conversation ---

async def test_embed_conversation_no_assistant_messages(db_conn):
    create_conversation(db_conn, "c1", "Test", "gpt-5.3-chat", "azure")
    insert_message(db_conn, "m1", "c1", "user", "hello")
    db_conn.commit()

    with patch("src.backend.rag.azure.get_embedding", new=AsyncMock()) as mock_embed:
        await embed_conversation(db_conn, "c1")
        mock_embed.assert_not_called()


async def test_embed_conversation_stores_chunks(db_conn):
    create_conversation(db_conn, "c2", "Test", "gpt-5.3-chat", "azure")
    insert_message(db_conn, "m1", "c2", "assistant", "The sky is blue.")
    db_conn.commit()

    with patch("src.backend.rag.azure.get_embedding", new=AsyncMock(return_value=FAKE_VECTOR)):
        await embed_conversation(db_conn, "c2")

    rows = db_conn.execute("SELECT * FROM embeddings WHERE conversation_id = 'c2'").fetchall()
    assert len(rows) >= 1
    assert rows[0]["chunk_text"] == "The sky is blue."


async def test_embed_conversation_long_text_produces_multiple_chunks(db_conn):
    create_conversation(db_conn, "c3", "Test", "gpt-5.3-chat", "azure")
    long_content = "word " * 300  # ~1500 chars
    insert_message(db_conn, "m1", "c3", "assistant", long_content)
    db_conn.commit()

    call_count = 0

    async def fake_embed(text):
        nonlocal call_count
        call_count += 1
        return FAKE_VECTOR

    with patch("src.backend.rag.azure.get_embedding", new=fake_embed):
        await embed_conversation(db_conn, "c3")

    assert call_count > 1


# --- retrieve_context ---

async def test_retrieve_context_empty_db(db_conn):
    with patch("src.backend.rag.azure.get_embedding", new=AsyncMock(return_value=FAKE_VECTOR)):
        results = await retrieve_context(db_conn, "anything")
    assert results == []


async def test_retrieve_context_returns_chunks(db_conn):
    create_conversation(db_conn, "c4", "Test", "gpt-5.3-chat", "azure")
    insert_message(db_conn, "m1", "c4", "assistant", "Python is great.")
    db_conn.commit()

    with patch("src.backend.rag.azure.get_embedding", new=AsyncMock(return_value=FAKE_VECTOR)):
        await embed_conversation(db_conn, "c4")
        results = await retrieve_context(db_conn, "programming language")

    assert len(results) >= 1
    assert "chunk_text" in results[0]
    assert "distance" in results[0]


async def test_retrieve_context_excludes_conv(db_conn):
    create_conversation(db_conn, "c5", "Test", "gpt-5.3-chat", "azure")
    insert_message(db_conn, "m1", "c5", "assistant", "Some content here.")
    db_conn.commit()

    with patch("src.backend.rag.azure.get_embedding", new=AsyncMock(return_value=FAKE_VECTOR)):
        await embed_conversation(db_conn, "c5")
        # embed gives message id "m1", pass that as the exclude set
        results = await retrieve_context(db_conn, "query", exclude_message_ids={"m1"})

    assert all(r["id"].split(":")[0] != "m1" for r in results)
