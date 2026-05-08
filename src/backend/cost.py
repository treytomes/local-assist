import sqlite3
from .database import transaction

# Seed data: (provider, model, input_cost_per_1k, output_cost_per_1k)
# Prices in USD per 1K tokens.
#
# Sources (verified 2026-05-08):
#   gpt-5.3-chat, Mistral-Large-3  — not in public retail API; set from Azure AI
#                                    Foundry documentation / portal estimates.
#                                    Update via POST /v1/pricing when confirmed.
#   gpt-4o (global)                — Azure Retail Prices API, eastus2, gpt-4o-0806-Inp/Outp-glbl
#   gpt-4o-mini (global)           — Azure Retail Prices API, eastus2, gpt-4o-mini-0718-Inp/Outp-glbl
#   text-embedding-3-small (global)— Azure Retail Prices API, eastus2, text-embedding-3-small-glbl
#   gpt-4o-mini-tts (global, audio out) — Azure Retail Prices API, gpt-4o-mini-tts-aud-out-glbl
#                                    Input (text) uses gpt-4o-mini-tts-txt-inp-glbl
#   gpt-4o-transcribe (global)     — audio input: gpt-4o-transcribe-aud-inp-glbl
#                                    text output:  gpt-4o-transcribe-txt-out-glbl
#   gpt-realtime (txt, global)     — gpt-4o-rt-txt-1217 Inp/Outp glbl
#   ollama/gemma3:1b               — free (local inference)
PRICING_SEED = [
    # Chat models (preview — prices estimated, update via /v1/pricing when confirmed)
    ("azure", "gpt-5.3-chat",              0.002,   0.008),
    ("azure", "Mistral-Large-3",           0.002,   0.006),
    # Chat models (from retail API)
    ("azure", "gpt-4o",                    0.0025,  0.010),
    ("azure", "gpt-4o-mini",               0.00015, 0.0006),
    # Embeddings (from retail API)
    ("azure", "text-embedding-3-small",    0.00002, 0.0),
    # TTS: input is text tokens, output is audio tokens (different rates)
    ("azure", "gpt-4o-mini-tts",           0.0006,  0.012),
    # STT: input is audio tokens, output is text tokens
    ("azure", "gpt-4o-transcribe",         0.006,   0.010),
    # Realtime text (input/output text tokens, global deployment)
    ("azure", "gpt-realtime",              0.005,   0.020),
    # Local Ollama — always free
    ("ollama", "gemma3:1b",                0.0,     0.0),
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


def upsert_pricing(
    conn: sqlite3.Connection,
    provider: str,
    model: str,
    input_cost_per_1k: float,
    output_cost_per_1k: float,
) -> dict:
    with transaction(conn):
        conn.execute(
            """
            INSERT INTO pricing (provider, model, input_cost_per_1k, output_cost_per_1k, last_updated)
            VALUES (?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            ON CONFLICT(provider, model) DO UPDATE SET
                input_cost_per_1k  = excluded.input_cost_per_1k,
                output_cost_per_1k = excluded.output_cost_per_1k,
                last_updated       = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (provider, model, input_cost_per_1k, output_cost_per_1k),
        )
    return get_pricing(conn, provider, model)


def get_pricing(conn: sqlite3.Connection, provider: str, model: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM pricing WHERE provider = ? AND model = ?",
        (provider, model),
    ).fetchone()
    return dict(row) if row else None


def list_pricing(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM pricing ORDER BY provider, model"
    ).fetchall()
    return [dict(r) for r in rows]


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
            SUM(cost_usd)          AS total_cost_usd
        FROM usage WHERE conversation_id = ?
        """,
        (conv_id,),
    ).fetchone()
    if not row or row["total_cost_usd"] is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_cost_usd": 0.0}
    return dict(row)


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
