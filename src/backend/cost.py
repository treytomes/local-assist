import sqlite3
from .database import transaction

# Seed data: (provider, model, input_cost_per_1k, output_cost_per_1k)
# Prices in USD. Azure AI Foundry list prices as of 2025-H1.
PRICING_SEED = [
    ("azure", "gpt-5.3-chat",    0.002,  0.008),
    ("azure", "Mistral-Large-3", 0.002,  0.006),
    ("azure", "gpt-4o",          0.005,  0.015),
    ("ollama", "gemma3:1b",      0.0,    0.0),
]


def seed_pricing(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """
        INSERT OR IGNORE INTO pricing (provider, model, input_cost_per_1k, output_cost_per_1k)
        VALUES (?, ?, ?, ?)
        """,
        PRICING_SEED,
    )
    conn.commit()


def get_price(conn: sqlite3.Connection, provider: str, model: str) -> tuple[float, float]:
    row = conn.execute(
        "SELECT input_cost_per_1k, output_cost_per_1k FROM pricing WHERE provider = ? AND model = ?",
        (provider, model),
    ).fetchone()
    if row:
        return row["input_cost_per_1k"], row["output_cost_per_1k"]
    return 0.0, 0.0


def compute_cost(input_tokens: int, output_tokens: int, input_per_1k: float, output_per_1k: float) -> float:
    return (input_tokens / 1000.0) * input_per_1k + (output_tokens / 1000.0) * output_per_1k


def record_usage(
    conn: sqlite3.Connection,
    usage_id: str,
    conv_id: str,
    msg_id: str | None,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    in_price, out_price = get_price(conn, provider, model)
    cost = compute_cost(prompt_tokens, completion_tokens, in_price, out_price)
    with transaction(conn):
        conn.execute(
            """
            INSERT INTO usage (id, conversation_id, message_id, provider, model,
                               prompt_tokens, completion_tokens, cost_usd)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (usage_id, conv_id, msg_id, provider, model, prompt_tokens, completion_tokens, cost),
        )
    return cost


def get_conversation_cost(conn: sqlite3.Connection, conv_id: str) -> dict:
    row = conn.execute(
        """
        SELECT
            SUM(prompt_tokens)     AS prompt_tokens,
            SUM(completion_tokens) AS completion_tokens,
            SUM(cost_usd)          AS total_cost
        FROM usage WHERE conversation_id = ?
        """,
        (conv_id,),
    ).fetchone()
    return dict(row) if row else {"prompt_tokens": 0, "completion_tokens": 0, "total_cost": 0.0}


def get_daily_costs(conn: sqlite3.Connection, days: int = 30) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            strftime('%Y-%m-%d', timestamp) AS day,
            provider,
            model,
            SUM(prompt_tokens)              AS prompt_tokens,
            SUM(completion_tokens)          AS completion_tokens,
            SUM(cost_usd)                   AS total_cost
        FROM usage
        WHERE timestamp >= strftime('%Y-%m-%dT%H:%M:%fZ', 'now', ? || ' days')
        GROUP BY day, provider, model
        ORDER BY day ASC
        """,
        (f"-{days}",),
    ).fetchall()
    return [dict(r) for r in rows]


def get_model_comparison(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            provider,
            model,
            COUNT(DISTINCT conversation_id) AS conversations,
            SUM(prompt_tokens)              AS total_prompt_tokens,
            SUM(completion_tokens)          AS total_completion_tokens,
            SUM(cost_usd)                   AS total_cost,
            AVG(cost_usd)                   AS avg_cost_per_call
        FROM usage
        GROUP BY provider, model
        ORDER BY total_cost DESC
        """,
    ).fetchall()
    return [dict(r) for r in rows]
