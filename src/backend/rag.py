"""
RAG: embed conversation summaries at close, retrieve top-k at new conversation start.
Uses sqlite-vec for vector storage + Azure embeddings (text-embedding-3-small, dim=1536).
"""
import sqlite3
import struct
import uuid

from .providers import azure

EMBEDDING_DIM = 1536
TOP_K = 5


def _pack(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


async def embed_conversation(conn: sqlite3.Connection, conv_id: str) -> None:
    """
    Chunk all assistant messages for a conversation, embed, and store.
    Called when a conversation is considered 'closed' (e.g., at app shutdown or
    explicit close action).
    """
    rows = conn.execute(
        "SELECT content FROM messages WHERE conversation_id = ? AND role = 'assistant' ORDER BY timestamp ASC",
        (conv_id,),
    ).fetchall()
    if not rows:
        return

    # Simple chunking: join all assistant turns, split into ~500-char chunks.
    full_text = "\n".join(r["content"] for r in rows)
    chunks = _chunk_text(full_text, chunk_size=500, overlap=50)

    for chunk in chunks:
        embedding = await azure.get_embedding(chunk)
        vec_id = str(uuid.uuid4())
        conn.execute(
            "INSERT OR REPLACE INTO embeddings (id, conversation_id, chunk_text, embedding) VALUES (?, ?, ?, ?)",
            (vec_id, conv_id, chunk, _pack(embedding)),
        )
    conn.commit()


async def retrieve_context(conn: sqlite3.Connection, query: str, exclude_conv_id: str | None = None) -> list[dict]:
    """
    Embed the query and return the top-k most similar chunks from past conversations.
    """
    query_vec = await azure.get_embedding(query)
    packed = _pack(query_vec)

    if exclude_conv_id:
        rows = conn.execute(
            """
            SELECT e.id, e.conversation_id, e.chunk_text,
                   vec_distance_cosine(e.embedding, ?) AS distance
            FROM embeddings e
            WHERE e.conversation_id != ?
            ORDER BY distance ASC
            LIMIT ?
            """,
            (packed, exclude_conv_id, TOP_K),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT e.id, e.conversation_id, e.chunk_text,
                   vec_distance_cosine(e.embedding, ?) AS distance
            FROM embeddings e
            ORDER BY distance ASC
            LIMIT ?
            """,
            (packed, TOP_K),
        ).fetchall()

    return [dict(r) for r in rows]


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    if len(text) <= chunk_size:
        return [text] if text.strip() else []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return [c for c in chunks if c.strip()]
