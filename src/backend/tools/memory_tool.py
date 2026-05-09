"""
Structured memory tool — subject/predicate/object triples with:
  - Optional TTL (expires_at): facts decay after N hours unless pinned
  - Pinning: pinned=True exempts a fact from expiry
  - Vector embeddings: each triple is embedded so semantic search works
    (e.g. "morning" finds "user hates mornings" even without that keyword)
  - Keyword fallback: search_memories_keyword for when embeddings aren't ready

Schema creates two tables:
  memories              — the S/P/O triples + metadata
  memory_embeddings     — vec0 virtual table, one row per memory
"""
import sqlite3
import struct
import uuid
from datetime import datetime, timezone, timedelta


# --- Schema ---

MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id              TEXT PRIMARY KEY,
    subject         TEXT NOT NULL,
    predicate       TEXT NOT NULL,
    object          TEXT NOT NULL,
    source_conv_id  TEXT,
    pinned          INTEGER NOT NULL DEFAULT 0,
    expires_at      TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_memories_subject   ON memories(subject);
CREATE INDEX IF NOT EXISTS idx_memories_predicate ON memories(predicate);
CREATE INDEX IF NOT EXISTS idx_memories_expires   ON memories(expires_at);
CREATE VIRTUAL TABLE IF NOT EXISTS memory_embeddings USING vec0(
    id          TEXT PRIMARY KEY,
    embedding   float[1536]
);
"""


# --- Helpers ---

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _expires_iso(ttl_hours: float) -> str:
    dt = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _pack(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def _prune_expired(conn: sqlite3.Connection) -> None:
    """Delete non-pinned memories whose expires_at is in the past."""
    now = _now_iso()
    expired_ids = [
        row["id"] for row in conn.execute(
            "SELECT id FROM memories WHERE pinned = 0 AND expires_at IS NOT NULL AND expires_at < ?",
            (now,),
        ).fetchall()
    ]
    for mid in expired_ids:
        conn.execute("DELETE FROM memory_embeddings WHERE id = ?", (mid,))
        conn.execute("DELETE FROM memories WHERE id = ?", (mid,))
    if expired_ids:
        conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["pinned"] = bool(d.get("pinned", 0))
    return d


# --- Core CRUD ---

def store_memory(
    conn: sqlite3.Connection,
    subject: str,
    predicate: str,
    object_: str,
    source_conv_id: str | None = None,
    ttl_hours: float | None = 24.0,
    pinned: bool = False,
) -> dict:
    """
    Upsert a memory triple. One fact per (subject, predicate) pair.
    - ttl_hours: lifetime in hours; None means no expiry. Default 24h.
    - pinned: if True, the memory never expires regardless of ttl_hours.
    Embedding is NOT done here (it requires async); call embed_memory() after.
    """
    _prune_expired(conn)
    existing = conn.execute(
        "SELECT id FROM memories WHERE subject = ? AND predicate = ?",
        (subject, predicate),
    ).fetchone()

    now = _now_iso()
    expires_at = None if (pinned or ttl_hours is None) else _expires_iso(ttl_hours)

    if existing:
        mem_id = existing["id"]
        conn.execute(
            """UPDATE memories
               SET object = ?, source_conv_id = ?, pinned = ?, expires_at = ?, updated_at = ?
               WHERE id = ?""",
            (object_, source_conv_id, int(pinned), expires_at, now, mem_id),
        )
    else:
        mem_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO memories
               (id, subject, predicate, object, source_conv_id, pinned, expires_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (mem_id, subject, predicate, object_, source_conv_id, int(pinned), expires_at, now, now),
        )

    conn.commit()
    row = conn.execute("SELECT * FROM memories WHERE id = ?", (mem_id,)).fetchone()
    return _row_to_dict(row)


async def embed_memory(conn: sqlite3.Connection, mem_id: str, subject: str, predicate: str, object_: str) -> None:
    """Embed the memory triple text and store in memory_embeddings. Idempotent."""
    from ..providers import azure
    text = f"{subject} {predicate}: {object_}"
    try:
        vector = await azure.get_embedding(text)
        conn.execute(
            "INSERT OR REPLACE INTO memory_embeddings (id, embedding) VALUES (?, ?)",
            (mem_id, _pack(vector)),
        )
        conn.commit()
    except Exception:
        pass  # embedding failure is non-fatal; keyword search still works


async def search_memories(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 10,
) -> list[dict]:
    """
    Semantic vector search over memory triples. Falls back to keyword LIKE
    search if no embeddings exist yet. Always filters out expired memories.
    """
    from ..providers import azure
    _prune_expired(conn)
    now = _now_iso()

    # Try vector search first
    try:
        query_vec = await azure.get_embedding(query)
        packed = _pack(query_vec)
        rows = conn.execute(
            """
            SELECT m.id, m.subject, m.predicate, m.object,
                   m.source_conv_id, m.pinned, m.expires_at, m.created_at, m.updated_at,
                   vec_distance_cosine(me.embedding, ?) AS distance
            FROM memory_embeddings me
            JOIN memories m ON m.id = me.id
            WHERE (m.expires_at IS NULL OR m.expires_at > ?)
            ORDER BY distance ASC
            LIMIT ?
            """,
            (packed, now, limit),
        ).fetchall()
        if rows:
            return [_row_to_dict(r) for r in rows]
    except Exception:
        pass

    # Fallback: keyword search
    return search_memories_keyword(conn, query, limit)


def search_memories_keyword(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 10,
) -> list[dict]:
    """Keyword LIKE search across subject, predicate, and object."""
    _prune_expired(conn)
    now = _now_iso()
    pattern = f"%{query}%"
    rows = conn.execute(
        """
        SELECT id, subject, predicate, object, source_conv_id, pinned, expires_at, created_at, updated_at
        FROM memories
        WHERE (subject LIKE ? OR predicate LIKE ? OR object LIKE ?)
          AND (expires_at IS NULL OR expires_at > ?)
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (pattern, pattern, pattern, now, limit),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_memories(conn: sqlite3.Connection, limit: int = 200) -> list[dict]:
    """Return all non-expired memories, pinned first then by subject/predicate."""
    _prune_expired(conn)
    now = _now_iso()
    rows = conn.execute(
        """
        SELECT id, subject, predicate, object, source_conv_id, pinned, expires_at, created_at, updated_at
        FROM memories
        WHERE (expires_at IS NULL OR expires_at > ?)
        ORDER BY pinned DESC, subject ASC, predicate ASC
        LIMIT ?
        """,
        (now, limit),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def set_pinned(conn: sqlite3.Connection, memory_id: str, pinned: bool) -> dict | None:
    """Toggle pinned status. Clears expires_at when pinning; restores 24h decay when unpinning."""
    row = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
    if not row:
        return None
    now = _now_iso()
    expires_at = None if pinned else _expires_iso(24.0)
    conn.execute(
        "UPDATE memories SET pinned = ?, expires_at = ?, updated_at = ? WHERE id = ?",
        (int(pinned), expires_at, now, memory_id),
    )
    conn.commit()
    updated = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
    return _row_to_dict(updated)


def delete_memory(conn: sqlite3.Connection, memory_id: str) -> bool:
    conn.execute("DELETE FROM memory_embeddings WHERE id = ?", (memory_id,))
    cursor = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
    conn.commit()
    return cursor.rowcount > 0


def get_all_as_text(conn: sqlite3.Connection) -> str:
    """
    Render all live memories as a compact block for system prompt injection.
    Pinned facts are marked with ★.
    """
    rows = list_memories(conn)
    if not rows:
        return ""
    lines = []
    for r in rows:
        pin = "★ " if r["pinned"] else ""
        lines.append(f"- {pin}{r['subject']} {r['predicate']}: {r['object']}")
    return "What I know:\n" + "\n".join(lines)
