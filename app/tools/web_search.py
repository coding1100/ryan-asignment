from __future__ import annotations

import logging
from datetime import datetime, timezone

from duckduckgo_search import DDGS

from app.tools.base import Tool

logger = logging.getLogger(__name__)


class WebSearchTool(Tool):
    """Performs real web search using DuckDuckGo and returns results."""

    name = "web_search"
    description = (
        "Performs a real web search using DuckDuckGo and returns summary snippets with titles and URLs."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query string"},
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default: 5)",
                "default": 5
            }
        },
        "required": ["query"],
    }

    async def run(self, query: str, max_results: int = 5) -> dict:
        """Execute real web search and return results."""
        if not query or not query.strip():
            raise ValueError("Query must be a non-empty string")
        
        if max_results < 1 or max_results > 20:
            max_results = 5  # Sane default

        try:
            # Perform real search using DuckDuckGo
            with DDGS() as ddgs:
                search_results = list(ddgs.text(
                    keywords=query,
                    max_results=max_results
                ))
            
            # Format results
            results = []
            for result in search_results:
                results.append({
                    "title": result.get("title", "No title"),
                    "snippet": result.get("body", "No description available"),
                    "url": result.get("href", ""),
                })
            
            timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
            
            return {
                "success": True,
                "data": {
                    "results": results,
                    "count": len(results),
                    "query": query,
                    "source": "DuckDuckGo",
                    "timestamp": timestamp
                },
                "message": f"Found {len(results)} search results for '{query}'"
            }
        
        except Exception as e:
            logger.error(f"Web search failed for query '{query}': {e}")
            # Return error but don't crash
            return {
                "success": False,
                "data": {
                    "results": [],
                    "count": 0,
                    "query": query,
                    "error": str(e)
                },
                "message": f"Search failed: {str(e)}"
            }

