"""
Tavily Search API contract stubs — M5 (Web Search).

These tests are skipped until src/backend/tools/search.py is implemented.
They serve as a spec for the expected behaviour of the Tavily integration.

Activate by removing the pytest.skip() call in each test once M5 lands.

Run with:  ./test.sh --integration  (once implemented)
"""
import os
import pytest

pytestmark = pytest.mark.integration

NOT_IMPLEMENTED = "Tavily search tool not yet implemented (M5)"


@pytest.fixture(scope="session")
def require_tavily():
    """Skip if TAVILY_API_KEY is not set."""
    if not os.getenv("TAVILY_API_KEY"):
        pytest.skip("TAVILY_API_KEY not set — skipping Tavily contract tests")


# ---------------------------------------------------------------------------
# Direct Tavily tool (src/backend/tools/search.py)
# ---------------------------------------------------------------------------

async def test_search_returns_results(require_tavily):
    """
    search(query) should return a list of result dicts, each with at least
    'title', 'url', and 'content' keys.

    Expected tool function:
        async def search(query: str, max_results: int = 5) -> list[dict]
    """
    pytest.skip(NOT_IMPLEMENTED)


async def test_search_result_shape(require_tavily):
    """Each result dict must contain 'title' (str), 'url' (str), 'content' (str)."""
    pytest.skip(NOT_IMPLEMENTED)


async def test_search_respects_max_results(require_tavily):
    """Passing max_results=2 should return no more than 2 results."""
    pytest.skip(NOT_IMPLEMENTED)


async def test_search_empty_query_raises(require_tavily):
    """An empty query string should raise ValueError before hitting the API."""
    pytest.skip(NOT_IMPLEMENTED)


async def test_search_bad_key_raises(require_tavily):
    """
    A deliberately invalid API key should raise an exception with a meaningful
    message (not silently return empty results).
    """
    pytest.skip(NOT_IMPLEMENTED)


# ---------------------------------------------------------------------------
# Chat integration — tool call injected into context (M5 backend wiring)
# ---------------------------------------------------------------------------

async def test_chat_with_search_tool_injects_results(require_tavily):
    """
    When the assistant decides to search, the tool result should appear in
    the conversation context and the final reply should reference it.

    Expected backend behaviour (router.py / main.py M5 additions):
      - Assistant emits a tool_call chunk
      - Backend executes search(), injects result as a tool message
      - Final assistant reply contains information from the search result
    """
    pytest.skip(NOT_IMPLEMENTED)


async def test_search_citation_card_in_sse_stream(require_tavily):
    """
    A search invocation during streaming should yield a dedicated SSE event:
        {"type": "tool_call", "tool": "search", "query": "<query>"}
    followed by the normal delta chunks containing the answer.
    """
    pytest.skip(NOT_IMPLEMENTED)


async def test_search_usage_recorded_in_db(require_tavily):
    """
    After a search-assisted chat turn, the conversation's message list should
    include a message with role='tool' containing the raw search results.
    """
    pytest.skip(NOT_IMPLEMENTED)
