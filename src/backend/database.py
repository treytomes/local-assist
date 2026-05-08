import sqlite3
import sqlite_vec
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path.home() / ".local" / "share" / "local-assist" / "local-assist.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.load_extension(sqlite_vec.loadable_path())
    return conn


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

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_usage_conversation    ON usage(conversation_id);
CREATE INDEX IF NOT EXISTS idx_usage_timestamp       ON usage(timestamp);
"""


def init_db(conn: sqlite3.Connection) -> None:
    for stmt in SCHEMA.split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)
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

def insert_message(conn: sqlite3.Connection, msg_id: str, conv_id: str, role: str, content: str) -> sqlite3.Row:
    conn.execute(
        "INSERT INTO messages (id, conversation_id, role, content) VALUES (?, ?, ?, ?)",
        (msg_id, conv_id, role, content),
    )
    touch_conversation(conn, conv_id)
    return conn.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()


def get_messages(conn: sqlite3.Connection, conv_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY timestamp ASC",
        (conv_id,),
    ).fetchall()
