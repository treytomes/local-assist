"""
Tavily web search tool with monthly usage tracking.
Usage is stored in the search_calls table and exposed via get_usage().
"""
import os
import datetime
import sqlite3

import httpx

TAVILY_MONTHLY_LIMIT = 1000
TAVILY_API_URL = "https://api.tavily.com/search"


def get_usage(conn: sqlite3.Connection) -> dict:
    """Return current-month search call count and reset info."""
    now = datetime.datetime.utcnow()
    if now.month == 12:
        reset = datetime.datetime(now.year + 1, 1, 1)
    else:
        reset = datetime.datetime(now.year, now.month + 1, 1)
    days_until_reset = (reset.date() - now.date()).days

    month_start = datetime.datetime(now.year, now.month, 1).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM search_calls WHERE called_at >= ?",
        (month_start,),
    ).fetchone()
    calls_used = row["cnt"] if row else 0

    return {
        "calls_used": calls_used,
        "limit": TAVILY_MONTHLY_LIMIT,
        "calls_remaining": max(0, TAVILY_MONTHLY_LIMIT - calls_used),
        "days_until_reset": days_until_reset,
        "reset_date": reset.strftime("%Y-%m-%d"),
    }


async def web_search(conn: sqlite3.Connection, query: str, max_results: int = 5) -> dict:
    """
    Search the web via Tavily. Records each call before executing so quota is
    accurate even on network failure.
    Returns: {query, results: [{title, url, content, score}], error?}
    """
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        return {"query": query, "results": [], "error": "TAVILY_API_KEY not configured"}

    conn.execute(
        "INSERT INTO search_calls (query) VALUES (?)",
        (query,),
    )
    conn.commit()

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                TAVILY_API_URL,
                json={
                    "api_key": api_key,
                    "query": query,
                    "max_results": min(max(1, max_results), 10),
                    "search_depth": "basic",
                    "include_answer": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", "")[:600],
                    "score": round(r.get("score", 0.0), 4),
                }
                for r in data.get("results", [])
            ]
            return {"query": query, "results": results}
    except httpx.HTTPStatusError as exc:
        return {"query": query, "results": [], "error": f"Tavily HTTP {exc.response.status_code}"}
    except Exception as exc:
        return {"query": query, "results": [], "error": str(exc)}
