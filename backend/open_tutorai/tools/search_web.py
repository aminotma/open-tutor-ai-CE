"""Tool: search the web via DuckDuckGo and return structured snippets.

Subjects: all subjects (fact-checking, recent data)
Exercise types: mcq (fact-check), explain (enrichment), history
"""
from __future__ import annotations

from langchain_core.tools import tool


@tool
def search_web(query: str, max_results: int = 5) -> dict:
    """
    Search the web using DuckDuckGo and return a list of relevant snippets.

    Args:
        query:       Search query string (natural language or keywords).
        max_results: Maximum number of results to return (1–10, default 5).

    Returns:
        dict with keys:
            success (bool)         — True if at least one result was found
            results (list[dict])   — Each item has: title, body, href
            error   (str)          — Error message on failure
    """
    max_results = max(1, min(max_results, 10))

    try:
        from duckduckgo_search import DDGS  # noqa: PLC0415
    except ImportError:
        return {
            "success": False,
            "results": [],
            "error": "duckduckgo-search is not installed.",
        }

    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))

        results = [
            {
                "title": r.get("title", ""),
                "body":  r.get("body", ""),
                "href":  r.get("href", ""),
            }
            for r in raw
        ]

        return {
            "success": bool(results),
            "results": results,
            "error": "" if results else "No results found for this query.",
        }

    except Exception as exc:
        # Never raise an exception — return a structured error
        # to avoid breaking the SSE stream on the Open WebUI side
        return {
            "success": False,
            "results": [],
            "error": f"Search unavailable: {type(exc).__name__}: {exc}",
        }
