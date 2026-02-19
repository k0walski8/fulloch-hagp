"""Web search tool using external SearXNG with optional OpenRouter summarization."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from typing import List

import requests
from bs4 import BeautifulSoup

from .tool_registry import tool, tool_registry

logger = logging.getLogger(__name__)

DEFAULT_SEARXNG_URL = "http://192.168.50.153:30053"
SEARXNG_URL = os.getenv(
    "SEARCH_SEARXNG_URL",
    DEFAULT_SEARXNG_URL,
)

OPENROUTER_WEB_SEARCH_ENABLED = os.getenv("OPENROUTER_WEB_SEARCH_ENABLED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "").strip()
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip().rstrip("/")


def searxng_search(query: str, num_results: int = 3) -> List[str]:
    """Run query against external SearXNG and return top URLs."""
    payload = {
        "q": query,
        "format": "json",
        "categories": "general",
    }
    response = requests.get(SEARXNG_URL, params=payload, timeout=10)
    response.raise_for_status()
    results = response.json().get("results", [])
    return [result.get("url", "") for result in results[:num_results] if result.get("url")]


def extract_main_text(html: str) -> str:
    """Extract visible text from a web page."""
    soup = BeautifulSoup(html, "html.parser")
    for bad in soup(["script", "style", "noscript", "footer", "header", "nav", "aside", "form"]):
        bad.decompose()

    paragraph_texts = [
        p.get_text(" ", strip=True)
        for p in soup.find_all("p")
        if len(p.get_text(strip=True)) > 40
    ]

    text = "\n".join(paragraph_texts) if paragraph_texts else soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text)


def fetch_website_summary(url: str, max_length: int = 3000) -> str:
    """Fetch and extract readable text from a URL."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return extract_main_text(response.text)[:max_length]
    except Exception:
        return ""


def _openrouter_enabled() -> bool:
    """Whether OpenRouter summarization is configured for web search."""
    return OPENROUTER_WEB_SEARCH_ENABLED and bool(OPENROUTER_API_KEY) and bool(OPENROUTER_MODEL)


def openrouter_web_summary(query: str, snippets: List[str]) -> str:
    """Use OpenRouter model to produce final answer from snippets."""
    if not snippets:
        return ""

    url = f"{OPENROUTER_BASE_URL}/chat/completions"
    today = datetime.now().strftime("%B %d, %Y")
    snippets_block = "\n\n".join(snippets)

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a web-search answer assistant. "
                    "Use only the provided snippets and answer in 2-4 concise sentences. "
                    "If snippets conflict, mention that briefly. Do not invent facts."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Today is {today}.\n\n"
                    f"Question: {query}\n\n"
                    f"Web snippets:\n{snippets_block}\n\n"
                    "Provide the final answer now."
                ),
            },
        ],
        "temperature": 0.2,
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        return (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
    except Exception as exc:
        logger.error(f"OpenRouter web summary failed: {exc}")
        return ""


@tool(
    name="external_information",
    description="Retrieve news and current event information through web search",
    aliases=["web_search", "current_events", "fact_search"],
)
def external_information(query: str = "get me the latest news stories") -> str:
    """
    Get latest information regarding news, facts and current events using SearXNG.

    If OPENROUTER_WEB_SEARCH_ENABLED + OPENROUTER_API_KEY + OPENROUTER_MODEL are set,
    web snippets are summarized via OpenRouter and returned directly.
    """
    website_snippets: List[str] = []

    try:
        top_urls = searxng_search(query, num_results=3)
        for url in top_urls:
            snippet = fetch_website_summary(url)
            if snippet:
                website_snippets.append(f"From {url}: {snippet}...")
    except Exception as exc:
        logger.error(f"Unable to search web: {exc}")

    if _openrouter_enabled():
        answer = openrouter_web_summary(query, website_snippets)
        if answer:
            return answer

    today = datetime.now().strftime("%B %d, %Y")

    lines = [f"Today is {today}.", ""]
    if website_snippets:
        lines.append("A web search has retrieved the following information:")
        lines.extend(website_snippets)
        lines.append("")
    else:
        lines.append("No web snippets were retrieved.")
        lines.append("")

    lines.append("User question:")
    lines.append(query)

    return "\n".join(lines)


if __name__ == "__main__":
    print("Web Search")

    print("\nAvailable tools:")
    for schema in tool_registry.get_all_schemas():
        print(f"  {schema.name}: {schema.description}")
        for param in schema.parameters:
            print(f"    - {param.name} ({param.type.value}): {param.description}")

    print("\nTesting function calling:")
    test_queries = [
        "who is the current us president",
        "who is top of the formula 1 driver championship",
        "summarise the latest research on autism",
    ]

    for query_text in test_queries:
        result = tool_registry.execute_tool("external_information", kwargs={"query": query_text})
        print(f"Query: {query_text}, Result: {result}")
