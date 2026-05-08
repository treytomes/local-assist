"""
Integration tests for the database layer using a real SQLite file.

These verify behaviour that in-memory tests cannot: WAL journal mode,
directory auto-creation, persistence across connections, and foreign-key
cascade across a real file.
"""
import sqlite3
import uuid

import pytest
import sqlite_vec

from src.backend.database import (
    init_db, get_conversation, create_conversation, delete_conversation,
    insert_message, get_messages, list_conversations, touch_conversation,
    transaction,
)
from src.backend.cost import seed_pricing, record_usage, get_conversation_cost, get_daily_costs


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# WAL and basic file properties
# ---------------------------------------------------------------------------

def test_wal_mode_is_active(integration_db):
    row = integration_db.execute("PRAGMA journal_mode").fetchone()
    assert row[0] == "wal"


def test_db_file_is_created_on_disk(integration_db_path, integration_db):
    assert integration_db_path.exists()
    assert integration_db_path.stat().st_size > 0


def test_schema_tables_exist(integration_db):
    tables = {
        r[0] for r in integration_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"conversations", "messages", "usage", "pricing"}.issubset(tables)


def test_sqlite_vec_extension_loaded(integration_db):
    # If sqlite-vec loaded correctly, vec_version() should be callable
    row = integration_db.execute("SELECT vec_version()").fetchone()
    assert row[0]  # non-empty version string


# ---------------------------------------------------------------------------
# Persistence across connections
# ---------------------------------------------------------------------------

def test_data_persists_across_reconnect(integration_db_path, integration_db):
    conv_id = str(uuid.uuid4())
    create_conversation(integration_db, conv_id, "Persistent", "gpt-5.3-chat", "azure")
    integration_db.commit()
    integration_db.close()

    # Open a brand-new connection to the same file
    conn2 = sqlite3.connect(str(integration_db_path), check_same_thread=False)
    conn2.row_factory = sqlite3.Row
    conn2.load_extension(sqlite_vec.loadable_path())
    try:
        row = conn2.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        assert row is not None
        assert row["title"] == "Persistent"
    finally:
        conn2.close()


def test_messages_persist_across_reconnect(integration_db_path, integration_db):
    conv_id = str(uuid.uuid4())
    create_conversation(integration_db, conv_id, "Msg test", "gpt-5.3-chat", "azure")
    insert_message(integration_db, str(uuid.uuid4()), conv_id, "user", "hello there")
    integration_db.commit()
    integration_db.close()

    conn2 = sqlite3.connect(str(integration_db_path), check_same_thread=False)
    conn2.row_factory = sqlite3.Row
    conn2.load_extension(sqlite_vec.loadable_path())
    try:
        rows = conn2.execute(
            "SELECT * FROM messages WHERE conversation_id = ?", (conv_id,)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["content"] == "hello there"
    finally:
        conn2.close()


# ---------------------------------------------------------------------------
# Directory auto-creation via get_connection
# ---------------------------------------------------------------------------

def test_get_connection_creates_directory(tmp_path, monkeypatch):
    deep_path = tmp_path / "a" / "b" / "c" / "test.db"
    import src.backend.database as db_mod
    monkeypatch.setattr(db_mod, "DB_PATH", deep_path)
    conn = db_mod.get_connection()
    try:
        assert deep_path.parent.exists()
        assert deep_path.exists()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Foreign key enforcement on real file
# ---------------------------------------------------------------------------

def test_foreign_key_prevents_orphan_message(integration_db):
    with pytest.raises(sqlite3.IntegrityError):
        integration_db.execute(
            "INSERT INTO messages (id, conversation_id, role, content) VALUES (?,?,?,?)",
            (str(uuid.uuid4()), "nonexistent-conv", "user", "orphan"),
        )
        integration_db.commit()


def test_cascade_delete_removes_messages_on_file(integration_db):
    conv_id = str(uuid.uuid4())
    create_conversation(integration_db, conv_id, "Cascade", "gpt-5.3-chat", "azure")
    insert_message(integration_db, str(uuid.uuid4()), conv_id, "user", "hi")
    insert_message(integration_db, str(uuid.uuid4()), conv_id, "assistant", "yo")
    integration_db.commit()

    delete_conversation(integration_db, conv_id)
    integration_db.commit()

    msgs = integration_db.execute(
        "SELECT * FROM messages WHERE conversation_id = ?", (conv_id,)
    ).fetchall()
    assert msgs == []


def test_cascade_delete_removes_usage_on_file(integration_db):
    conv_id = str(uuid.uuid4())
    create_conversation(integration_db, conv_id, "Usage cascade", "gpt-5.3-chat", "azure")
    integration_db.commit()
    record_usage(integration_db, str(uuid.uuid4()), conv_id, None,
                 "azure", "gpt-5.3-chat", 100, 50)

    delete_conversation(integration_db, conv_id)
    integration_db.commit()

    rows = integration_db.execute(
        "SELECT * FROM usage WHERE conversation_id = ?", (conv_id,)
    ).fetchall()
    assert rows == []


# ---------------------------------------------------------------------------
# Cost recording on file DB
# ---------------------------------------------------------------------------

def test_record_and_retrieve_cost_on_file(integration_db):
    conv_id = str(uuid.uuid4())
    create_conversation(integration_db, conv_id, "Cost test", "gpt-5.3-chat", "azure")
    integration_db.commit()

    cost = record_usage(integration_db, str(uuid.uuid4()), conv_id, None,
                        "azure", "gpt-5.3-chat", 2000, 1000)
    assert cost > 0

    summary = get_conversation_cost(integration_db, conv_id)
    assert summary["prompt_tokens"] == 2000
    assert summary["completion_tokens"] == 1000
    assert abs(summary["total_cost"] - cost) < 1e-9


def test_daily_costs_span_correct_window(integration_db):
    conv_id = str(uuid.uuid4())
    create_conversation(integration_db, conv_id, "Daily", "gpt-5.3-chat", "azure")
    integration_db.commit()

    for _ in range(3):
        record_usage(integration_db, str(uuid.uuid4()), conv_id, None,
                     "azure", "gpt-5.3-chat", 100, 50)

    rows = get_daily_costs(integration_db, days=1)
    assert len(rows) == 1
    assert rows[0]["prompt_tokens"] == 300


# ---------------------------------------------------------------------------
# Transaction rollback on file DB
# ---------------------------------------------------------------------------

def test_transaction_rollback_on_file(integration_db):
    conv_id = str(uuid.uuid4())
    create_conversation(integration_db, conv_id, "Rollback", "gpt-5.3-chat", "azure")
    integration_db.commit()

    with pytest.raises(RuntimeError):
        with transaction(integration_db):
            insert_message(integration_db, str(uuid.uuid4()), conv_id, "user", "temp")
            raise RuntimeError("abort")

    assert get_messages(integration_db, conv_id) == []


# ---------------------------------------------------------------------------
# init_db idempotency
# ---------------------------------------------------------------------------

def test_init_db_is_idempotent(integration_db):
    # Running init_db a second time on an existing schema must not raise
    init_db(integration_db)
    tables = {
        r[0] for r in integration_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "conversations" in tables
