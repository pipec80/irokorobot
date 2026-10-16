"""Start-up probe: say so when Ollama is unreachable (Plan 0064, D-6).

The server starts before Ollama more often than not on a development machine, and the first
turn then answers with the fallback phrase without any hint of why. One ``GET /api/tags`` at
start-up turns that silence into a warning in the log. It only warns: it never raises and never
waits longer than its own timeout.

It does **not** detect the cold-start failure seen in the Plan 0063 acceptance: a model that is
still loading answers ``/api/tags`` while its first generation fails. The operator manual says to
warm the model with one ordinary sentence after the start.
"""

import logging

import httpx

logger = logging.getLogger(__name__)

_PROBE_TIMEOUT_SECONDS = 3.0
_TAGS_PATH = "/api/tags"


async def probe_ollama(client: httpx.AsyncClient, base_url: str) -> bool:
    """Check once that Ollama answers, logging one warning when it does not.

    Args:
        client: The lifecycle-owned HTTP client.
        base_url: Ollama's base URL (``settings.ollama_url``).

    Returns:
        ``True`` when ``GET /api/tags`` answers with a success status; ``False`` after
        logging one warning that names only the exception class.
    """
    try:
        response = await client.get(
            f"{base_url.rstrip('/')}{_TAGS_PATH}", timeout=_PROBE_TIMEOUT_SECONDS
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning(
            "Ollama is not reachable at start-up (%s): replies use the fallback phrase "
            "until it answers",
            type(exc).__name__,
        )
        return False
    return True
