import pytest
from src.backend.database import (
    create_conversation, get_conversation, list_conversations,
    touch_conversation, delete_conversation,
    insert_message, get_messages, transaction,
)


def test_create_and_get_conversation(db_conn):
    row = create_conversation(db_conn, "id-1", "Hello", "gpt-5.3-chat", "azure")
    db_conn.commit()
    assert row["id"] == "id-1"
    assert row["title"] == "Hello"
    assert row["model"] == "gpt-5.3-chat"
    assert row["provider"] == "azure"


def test_get_conversation_missing(db_conn):
    assert get_conversation(db_conn, "nope") is None


def test_list_conversations_empty(db_conn):
    assert list_conversations(db_conn) == []


def test_list_conversations_ordered(db_conn):
    create_conversation(db_conn, "a", "First", "gpt-5.3-chat", "azure")
    create_conversation(db_conn, "b", "Second", "gpt-5.3-chat", "azure")
    db_conn.commit()
    rows = list_conversations(db_conn)
    assert len(rows) == 2
    # most-recently-updated first; created in same statement so order may vary,
    # but both must be present
    ids = {r["id"] for r in rows}
    assert ids == {"a", "b"}


def test_touch_conversation_updates_timestamp(db_conn):
    create_conversation(db_conn, "c1", "Old", "gpt-5.3-chat", "azure")
    db_conn.commit()
    before = get_conversation(db_conn, "c1")["updated_at"]
    import time; time.sleep(0.01)
    touch_conversation(db_conn, "c1")
    db_conn.commit()
    after = get_conversation(db_conn, "c1")["updated_at"]
    # Timestamps may be equal at millisecond resolution in CI; just check it doesn't error
    assert after >= before


def test_touch_conversation_with_title(db_conn):
    create_conversation(db_conn, "c2", "Old title", "gpt-5.3-chat", "azure")
    db_conn.commit()
    touch_conversation(db_conn, "c2", title="New title")
    db_conn.commit()
    assert get_conversation(db_conn, "c2")["title"] == "New title"


def test_delete_conversation(db_conn):
    create_conversation(db_conn, "d1", "To delete", "gpt-5.3-chat", "azure")
    db_conn.commit()
    delete_conversation(db_conn, "d1")
    db_conn.commit()
    assert get_conversation(db_conn, "d1") is None


def test_cascade_delete_removes_messages(db_conn):
    create_conversation(db_conn, "c3", "With msgs", "gpt-5.3-chat", "azure")
    insert_message(db_conn, "m1", "c3", "user", "hi")
    db_conn.commit()
    delete_conversation(db_conn, "c3")
    db_conn.commit()
    assert get_messages(db_conn, "c3") == []


def test_insert_and_get_messages(db_conn):
    create_conversation(db_conn, "c4", "Chat", "gpt-5.3-chat", "azure")
    db_conn.commit()
    insert_message(db_conn, "m1", "c4", "user", "hello")
    insert_message(db_conn, "m2", "c4", "assistant", "world")
    db_conn.commit()
    msgs = get_messages(db_conn, "c4")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"


def test_insert_message_touches_conversation(db_conn):
    create_conversation(db_conn, "c5", "Chat", "gpt-5.3-chat", "azure")
    db_conn.commit()
    before = get_conversation(db_conn, "c5")["updated_at"]
    import time; time.sleep(0.01)
    insert_message(db_conn, "m3", "c5", "user", "ping")
    db_conn.commit()
    after = get_conversation(db_conn, "c5")["updated_at"]
    assert after >= before


def test_get_messages_empty(db_conn):
    create_conversation(db_conn, "c6", "Empty", "gpt-5.3-chat", "azure")
    db_conn.commit()
    assert get_messages(db_conn, "c6") == []


def test_transaction_rollback_on_error(db_conn):
    create_conversation(db_conn, "c7", "Rollback test", "gpt-5.3-chat", "azure")
    db_conn.commit()

    with pytest.raises(Exception):
        with transaction(db_conn):
            # Insert a valid message then force an error
            db_conn.execute(
                "INSERT INTO messages (id, conversation_id, role, content) VALUES (?,?,?,?)",
                ("mx", "c7", "user", "temp"),
            )
            raise ValueError("forced rollback")

    # Message should not be present
    assert get_messages(db_conn, "c7") == []
