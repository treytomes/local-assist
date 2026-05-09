import sqlite3
import sqlite_vec
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path.home() / ".local" / "share" / "local-assist" / "local-assist.db"

# Module-level singleton — set by main.py lifespan, read by mcp_server.py tools.
_shared_conn: sqlite3.Connection | None = None


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.load_extension(sqlite_vec.loadable_path())
    return conn


def set_shared_connection(conn: sqlite3.Connection) -> None:
    global _shared_conn
    _shared_conn = conn


def shared_connection() -> sqlite3.Connection:
    if _shared_conn is None:
        raise RuntimeError("Database connection not initialised yet")
    return _shared_conn


@contextmanager
def transaction(conn: sqlite3.Connection):
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT 'New conversation',
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    model       TEXT NOT NULL DEFAULT 'gpt-5.3-chat',
    provider    TEXT NOT NULL DEFAULT 'azure'
);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK(role IN ('system','user','assistant','tool')),
    content         TEXT NOT NULL,
    model           TEXT,
    timestamp       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS usage (
    id                TEXT PRIMARY KEY,
    conversation_id   TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    message_id        TEXT REFERENCES messages(id) ON DELETE SET NULL,
    provider          TEXT NOT NULL,
    model             TEXT NOT NULL,
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd          REAL NOT NULL DEFAULT 0.0,
    timestamp         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS pricing (
    provider              TEXT NOT NULL,
    model                 TEXT NOT NULL,
    input_cost_per_1k     REAL NOT NULL,
    output_cost_per_1k    REAL NOT NULL,
    last_updated          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (provider, model)
);

CREATE VIRTUAL TABLE IF NOT EXISTS embeddings USING vec0(
    id              TEXT PRIMARY KEY,
    conversation_id TEXT,
    chunk_text      TEXT,
    embedding       float[1536]
);

CREATE TABLE IF NOT EXISTS search_calls (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    query     TEXT NOT NULL,
    called_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS reactions (
    id         TEXT PRIMARY KEY,
    message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    author     TEXT NOT NULL CHECK(author IN ('user', 'assistant')),
    emoji      TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_usage_conversation    ON usage(conversation_id);
CREATE INDEX IF NOT EXISTS idx_usage_timestamp       ON usage(timestamp);
CREATE INDEX IF NOT EXISTS idx_search_calls_date     ON search_calls(called_at);
CREATE INDEX IF NOT EXISTS idx_reactions_message     ON reactions(message_id);
"""


def init_db(conn: sqlite3.Connection) -> None:
    from .tools.memory_tool import MEMORY_SCHEMA

    # Execute base schema (tables only — indexes and virtual tables come after migrations)
    for stmt in SCHEMA.split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)

    # Column migrations must run before MEMORY_SCHEMA, which creates indexes that
    # reference these columns. ALTER TABLE is a no-op if the column already exists.
    msg_cols = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
    if "model" not in msg_cols:
        conn.execute("ALTER TABLE messages ADD COLUMN model TEXT")

    mem_tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memories'")}
    if mem_tables:
        mem_cols = {row[1] for row in conn.execute("PRAGMA table_info(memories)")}
        if "pinned" not in mem_cols:
            conn.execute("ALTER TABLE memories ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
        if "expires_at" not in mem_cols:
            conn.execute("ALTER TABLE memories ADD COLUMN expires_at TEXT")

    # Now safe to create indexes and virtual tables that reference the migrated columns
    for stmt in MEMORY_SCHEMA.split(";"):
        stmt = stmt.strip()
        if stmt:
            try:
                conn.execute(stmt)
            except Exception:
                pass  # index/table already exists

    conn.commit()


# --- Conversations ---

def create_conversation(conn: sqlite3.Connection, conv_id: str, title: str, model: str, provider: str) -> sqlite3.Row:
    conn.execute(
        "INSERT INTO conversations (id, title, model, provider) VALUES (?, ?, ?, ?)",
        (conv_id, title, model, provider),
    )
    return get_conversation(conn, conv_id)


def get_conversation(conn: sqlite3.Connection, conv_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()


def list_conversations(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM conversations ORDER BY updated_at DESC"
    ).fetchall()


def touch_conversation(conn: sqlite3.Connection, conv_id: str, title: str | None = None) -> None:
    if title:
        conn.execute(
            "UPDATE conversations SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), title = ? WHERE id = ?",
            (title, conv_id),
        )
    else:
        conn.execute(
            "UPDATE conversations SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
            (conv_id,),
        )


def update_conversation(conn: sqlite3.Connection, conv_id: str, title: str | None = None, model: str | None = None) -> sqlite3.Row | None:
    if title is not None:
        conn.execute("UPDATE conversations SET title = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?", (title, conv_id))
    if model is not None:
        conn.execute("UPDATE conversations SET model = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?", (model, conv_id))
    return get_conversation(conn, conv_id)


def delete_conversation(conn: sqlite3.Connection, conv_id: str) -> None:
    conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))


# --- Messages ---

def insert_message(conn: sqlite3.Connection, msg_id: str, conv_id: str, role: str, content: str, model: str | None = None) -> sqlite3.Row:
    conn.execute(
        "INSERT INTO messages (id, conversation_id, role, content, model) VALUES (?, ?, ?, ?, ?)",
        (msg_id, conv_id, role, content, model),
    )
    touch_conversation(conn, conv_id)
    return conn.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()


def get_messages(conn: sqlite3.Connection, conv_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY timestamp ASC",
        (conv_id,),
    ).fetchall()


def delete_message(conn: sqlite3.Connection, msg_id: str) -> bool:
    cursor = conn.execute("DELETE FROM messages WHERE id = ?", (msg_id,))
    return cursor.rowcount > 0


# --- Reactions ---

def get_reactions(conn: sqlite3.Connection, message_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM reactions WHERE message_id = ? ORDER BY created_at ASC",
        (message_id,),
    ).fetchall()


def get_reactions_for_conversation(conn: sqlite3.Connection, conv_id: str, limit: int = 20) -> list[sqlite3.Row]:
    """Return reactions for the most recent `limit` messages in a conversation."""
    return conn.execute(
        """
        SELECT r.*
        FROM reactions r
        JOIN messages m ON m.id = r.message_id
        WHERE m.conversation_id = ?
          AND m.id IN (
              SELECT id FROM messages
              WHERE conversation_id = ?
              ORDER BY timestamp DESC
              LIMIT ?
          )
        ORDER BY m.timestamp ASC, r.created_at ASC
        """,
        (conv_id, conv_id, limit),
    ).fetchall()


def add_reaction(conn: sqlite3.Connection, reaction_id: str, message_id: str, author: str, emoji: str) -> sqlite3.Row:
    conn.execute(
        "INSERT INTO reactions (id, message_id, author, emoji) VALUES (?, ?, ?, ?)",
        (reaction_id, message_id, author, emoji),
    )
    return conn.execute("SELECT * FROM reactions WHERE id = ?", (reaction_id,)).fetchone()


def delete_reaction(conn: sqlite3.Connection, reaction_id: str) -> bool:
    cursor = conn.execute("DELETE FROM reactions WHERE id = ?", (reaction_id,))
    return cursor.rowcount > 0
