"""Shared LLM API client singletons.

Both the conversation path (llm.py) and the consolidation path
(memory/consolidation.py) talk to Anthropic; the client is created once
and shared so connection pools and configuration stay in one place.
"""

import anthropic

from server.settings import settings

_anthropic_client: anthropic.AsyncAnthropic | None = None


def get_anthropic_client() -> anthropic.AsyncAnthropic:
    """Return the singleton Anthropic async client, creating it on first call."""
    global _anthropic_client  # noqa: PLW0603
    if _anthropic_client is None:
        _anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client
