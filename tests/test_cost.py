import uuid
import pytest
from src.backend.cost import (
    seed_pricing, get_price, compute_cost, record_usage,
    get_conversation_cost, get_daily_costs, get_model_comparison,
    upsert_pricing, get_pricing, list_pricing,
    PRICING_SEED,
)
from src.backend.database import create_conversation


def test_seed_pricing_inserts_all_rows(db_conn):
    rows = db_conn.execute("SELECT * FROM pricing").fetchall()
    assert len(rows) == len(PRICING_SEED)


def test_seed_pricing_idempotent(db_conn):
    seed_pricing(db_conn)  # second call; INSERT OR IGNORE
    rows = db_conn.execute("SELECT * FROM pricing").fetchall()
    assert len(rows) == len(PRICING_SEED)


def test_get_price_known_model(db_conn):
    inp, out = get_price(db_conn, "azure", "gpt-5.3-chat")
    assert inp == 0.002
    assert out == 0.008


def test_get_price_unknown_model(db_conn):
    inp, out = get_price(db_conn, "azure", "nonexistent")
    assert inp == 0.0
    assert out == 0.0


def test_get_price_ollama_free(db_conn):
    inp, out = get_price(db_conn, "ollama", "gemma3:1b")
    assert inp == 0.0
    assert out == 0.0


def test_compute_cost_zero():
    assert compute_cost(0, 0, 0.002, 0.008) == 0.0


def test_compute_cost_basic():
    # 1000 input tokens at $0.002/1k + 500 output tokens at $0.008/1k = 0.002 + 0.004
    cost = compute_cost(1000, 500, 0.002, 0.008)
    assert abs(cost - 0.006) < 1e-9


def test_record_usage_returns_cost(db_conn):
    create_conversation(db_conn, "conv-1", "Test", "gpt-5.3-chat", "azure")
    db_conn.commit()
    cost = record_usage(db_conn, str(uuid.uuid4()), "conv-1", None, "azure", "gpt-5.3-chat", 1000, 500)
    assert abs(cost - 0.006) < 1e-9


def test_record_usage_with_message_id(db_conn):
    from src.backend.database import insert_message
    create_conversation(db_conn, "conv-2", "Test", "gpt-5.3-chat", "azure")
    insert_message(db_conn, "msg-1", "conv-2", "assistant", "hello")
    db_conn.commit()
    cost = record_usage(db_conn, str(uuid.uuid4()), "conv-2", "msg-1", "azure", "gpt-5.3-chat", 100, 50)
    assert cost > 0


def test_get_conversation_cost_empty(db_conn):
    create_conversation(db_conn, "conv-3", "Test", "gpt-5.3-chat", "azure")
    db_conn.commit()
    result = get_conversation_cost(db_conn, "conv-3")
    # All-NULL SUM returns a row; values are None or 0 depending on SQLite version
    assert result["total_cost_usd"] is None or result["total_cost_usd"] == 0.0


def test_get_conversation_cost_with_usage(db_conn):
    create_conversation(db_conn, "conv-4", "Test", "gpt-5.3-chat", "azure")
    db_conn.commit()
    record_usage(db_conn, str(uuid.uuid4()), "conv-4", None, "azure", "gpt-5.3-chat", 1000, 1000)
    record_usage(db_conn, str(uuid.uuid4()), "conv-4", None, "azure", "gpt-5.3-chat", 500, 500)
    result = get_conversation_cost(db_conn, "conv-4")
    assert result["prompt_tokens"] == 1500
    assert result["completion_tokens"] == 1500
    assert result["total_cost_usd"] > 0


def test_get_daily_costs_empty(db_conn):
    assert get_daily_costs(db_conn) == []


def test_get_daily_costs_returns_data(db_conn):
    create_conversation(db_conn, "conv-5", "Test", "gpt-5.3-chat", "azure")
    db_conn.commit()
    record_usage(db_conn, str(uuid.uuid4()), "conv-5", None, "azure", "gpt-5.3-chat", 100, 100)
    rows = get_daily_costs(db_conn)
    assert len(rows) >= 1
    assert "day" in rows[0]
    assert rows[0]["provider"] == "azure"


def test_get_model_comparison_empty(db_conn):
    assert get_model_comparison(db_conn) == []


def test_get_model_comparison_aggregates(db_conn):
    create_conversation(db_conn, "conv-6", "Test", "gpt-5.3-chat", "azure")
    create_conversation(db_conn, "conv-7", "Test", "Mistral-Large-3", "azure")
    db_conn.commit()
    record_usage(db_conn, str(uuid.uuid4()), "conv-6", None, "azure", "gpt-5.3-chat", 1000, 1000)
    record_usage(db_conn, str(uuid.uuid4()), "conv-7", None, "azure", "Mistral-Large-3", 1000, 1000)
    rows = get_model_comparison(db_conn)
    models = {r["model"] for r in rows}
    assert "gpt-5.3-chat" in models
    assert "Mistral-Large-3" in models


# --- upsert_pricing / get_pricing / list_pricing ---

def test_upsert_pricing_inserts_new(db_conn):
    result = upsert_pricing(db_conn, "azure", "new-model", 0.001, 0.005)
    assert result["provider"] == "azure"
    assert result["model"] == "new-model"
    assert result["input_cost_per_1k"] == 0.001
    assert result["output_cost_per_1k"] == 0.005
    assert "last_updated" in result


def test_upsert_pricing_updates_existing(db_conn):
    upsert_pricing(db_conn, "azure", "gpt-5.3-chat", 0.999, 0.999)
    inp, out = get_price(db_conn, "azure", "gpt-5.3-chat")
    assert inp == 0.999
    assert out == 0.999


def test_upsert_pricing_updates_last_updated(db_conn):
    r1 = upsert_pricing(db_conn, "azure", "gpt-5.3-chat", 0.001, 0.002)
    r2 = upsert_pricing(db_conn, "azure", "gpt-5.3-chat", 0.003, 0.004)
    assert r2["last_updated"] >= r1["last_updated"]


def test_get_pricing_known(db_conn):
    row = get_pricing(db_conn, "azure", "gpt-4o")
    assert row is not None
    assert row["input_cost_per_1k"] == 0.0025


def test_get_pricing_unknown(db_conn):
    assert get_pricing(db_conn, "azure", "nonexistent") is None


def test_list_pricing_returns_all(db_conn):
    rows = list_pricing(db_conn)
    assert len(rows) == len(PRICING_SEED)
    assert all("provider" in r and "model" in r for r in rows)


def test_list_pricing_ordered(db_conn):
    rows = list_pricing(db_conn)
    keys = [(r["provider"], r["model"]) for r in rows]
    assert keys == sorted(keys)
