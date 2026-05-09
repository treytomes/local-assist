"""
RAG: embed assistant messages progressively, retrieve across all conversations.
Uses sqlite-vec for vector storage + Azure embeddings (text-embedding-3-small, dim=1536).

Chunk IDs use the format "{msg_id}:{chunk_index}" for messages embedded via
embed_message(), enabling idempotent upserts and exclusion by message ID.
Legacy chunks from embed_conversation() use random UUIDs and are never excluded.
"""
import sqlite3
import struct
import uuid

from .providers import azure

EMBEDDING_DIM = 1536
TOP_K = 6


def _pack(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


async def embed_message(conn: sqlite3.Connection, conv_id: str, msg_id: str, content: str) -> None:
    """
    Embed a single assistant message and store it. Idempotent — uses structured
    chunk IDs "{msg_id}:{n}" so re-calling with the same msg_id overwrites in place.
    """
    if not content.strip():
        return
    chunks = _chunk_text(content, chunk_size=500, overlap=50)
    for i, chunk in enumerate(chunks):
        embedding = await azure.get_embedding(chunk)
        conn.execute(
            "INSERT OR REPLACE INTO embeddings (id, conversation_id, chunk_text, embedding) VALUES (?, ?, ?, ?)",
            (f"{msg_id}:{i}", conv_id, chunk, _pack(embedding)),
        )
    conn.commit()


async def embed_conversation(conn: sqlite3.Connection, conv_id: str) -> None:
    """
    Bulk-embed all assistant messages for a conversation. Used by the
    POST /v1/conversations/{id}/embed endpoint for backfilling.
    """
    rows = conn.execute(
        "SELECT id, content FROM messages WHERE conversation_id = ? AND role = 'assistant' ORDER BY timestamp ASC",
        (conv_id,),
    ).fetchall()
    for row in rows:
        await embed_message(conn, conv_id, row["id"], row["content"])


async def retrieve_context(
    conn: sqlite3.Connection,
    query: str,
    exclude_message_ids: set[str] | None = None,
) -> list[dict]:
    """
    Embed the query and return the top-k most similar chunks across all conversations.

    exclude_message_ids: skip chunks whose structured ID starts with one of these
    message IDs (i.e. already present in the sliding window). Chunks with legacy
    UUID-style IDs are never excluded.
    """
    query_vec = await azure.get_embedding(query)
    packed = _pack(query_vec)

    # Fetch extra rows to absorb any that get filtered out by exclude_message_ids.
    fetch_k = TOP_K * 3 if exclude_message_ids else TOP_K
    rows = conn.execute(
        """
        SELECT e.id, e.conversation_id, e.chunk_text,
               vec_distance_cosine(e.embedding, ?) AS distance
        FROM embeddings e
        ORDER BY distance ASC
        LIMIT ?
        """,
        (packed, fetch_k),
    ).fetchall()

    results = []
    for row in rows:
        if exclude_message_ids and ":" in row["id"]:
            msg_id = row["id"].split(":")[0]
            if msg_id in exclude_message_ids:
                continue
        entry = dict(row)
        # Enrich chunk_text with any reactions on this message so Mara sees
        # the emotional signal when the chunk is injected as RAG context.
        if ":" in row["id"]:
            msg_id = row["id"].split(":")[0]
            reaction_rows = conn.execute(
                "SELECT author, emoji FROM reactions WHERE message_id = ? ORDER BY created_at ASC",
                (msg_id,),
            ).fetchall()
            if reaction_rows:
                summary = ", ".join(
                    f"{r['author']}: {r['emoji']}" for r in reaction_rows
                )
                entry["chunk_text"] = entry["chunk_text"] + f"\n[reactions: {summary}]"
        results.append(entry)
        if len(results) >= TOP_K:
            break

    return results


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
