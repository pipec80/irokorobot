"""Start-up probe: say so when Ollama is unreachable (Plan 0064, D-6).

The server starts before Ollama more often than not on a development machine, and the first
turn then answers with the fallback phrase without any hint of why. One ``GET /api/tags`` at
start-up turns that silence into a warning in the log. It only warns: it never raises and never
waits longer than its own deadline. The HTTP call itself lives in ``llm_transport`` (the one
seam to Ollama, ``tests/unit/test_ollama_seam.py``); this module owns the policy.

It does **not** detect the cold-start failure seen in the Plan 0063 acceptance: a model that is
still loading answers ``/api/tags`` while its first generation fails. The operator manual says to
warm the model with one ordinary sentence after the start.
"""

import asyncio
import logging

import httpx

from server import llm_transport

logger = logging.getLogger(__name__)

# A total deadline, not httpx's per-phase timeout: a host that accepts the connection and then
# stalls must not delay the start by connect + read.
_PROBE_TIMEOUT_SECONDS = 3.0


async def probe_ollama(client: httpx.AsyncClient) -> bool:
    """Check once that Ollama answers, logging one warning when it does not.

    Args:
        client: The lifecycle-owned HTTP client.

    Returns:
        ``True`` when ``GET /api/tags`` answers with a success status within the deadline;
        ``False`` after logging one warning that names only the exception class. Nothing
        propagates, including a malformed ``OLLAMA_URL`` or a stalled host.
    """
    try:
        async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):
            await llm_transport.check_reachable(client)
    except (httpx.HTTPError, httpx.InvalidURL, ValueError, TimeoutError) as exc:
        logger.warning(
            "Ollama is not reachable at start-up (%s): replies use the fallback phrase "
            "until it answers",
            type(exc).__name__,
        )
        return False
    return True
