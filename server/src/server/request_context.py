"""Per-request correlation context shared by every log line of one turn.

Plan 0032 removes raw household content from the logs. What replaces it is
correlation: a single request id lets an operator follow one turn through
identity, STT, cognition, memory and TTS without any line carrying what was
said.

The middleware is deliberately pure ASGI rather than Starlette's
``BaseHTTPMiddleware``: that base class buffers the response body, which would
defeat the sentence-by-sentence NDJSON stream ``POST /transcribe/stream``
depends on.

The ASGI types are declared locally instead of imported from Starlette, so this
module adds no new direct dependency (see ADR 0010).
"""

from collections.abc import Awaitable, Callable, MutableMapping
from contextvars import ContextVar
import logging
import time
from typing import Any
from uuid import UUID, uuid4

# Minimal ASGI type aliases per the ASGI 3.0 specification.
# Any: an ASGI scope/message is an open, protocol-defined mapping.
type Scope = MutableMapping[str, Any]
type Message = MutableMapping[str, Any]
type Receive = Callable[[], Awaitable[Message]]
type Send = Callable[[Message], Awaitable[None]]
type ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

REQUEST_ID_HEADER = "X-Request-ID"
_HEADER_KEY = REQUEST_ID_HEADER.lower().encode("latin-1")
ABSENT_REQUEST_ID = "-"

logger = logging.getLogger(__name__)

_request_id_var: ContextVar[str | None] = ContextVar("iroko_request_id", default=None)


def current_request_id() -> str | None:
    """Return the correlation id of the request being served, if any.

    Returns:
        The current request's id, or ``None`` outside a request — for example
        in the retention background job or at startup.
    """
    return _request_id_var.get()


def _inbound_request_id(scope: Scope) -> str | None:
    """Extract a trustworthy correlation id from the request headers.

    The header is client-controlled, so an arbitrary value is never echoed
    back: only a syntactically valid UUID is preserved, which keeps the field
    useless as an injection or unbounded-length vector.

    Args:
        scope: ASGI connection scope for one HTTP request.

    Returns:
        The supplied id when it parses as a UUID, otherwise ``None``.
    """
    for raw_key, raw_value in scope.get("headers", []):
        if raw_key != _HEADER_KEY:
            continue
        candidate: str = raw_value.decode("latin-1", errors="replace")
        try:
            UUID(candidate)
        except ValueError:
            return None
        return candidate
    return None


class RequestIdFilter(logging.Filter):
    """Attach the ambient request id to every record that passes through.

    Installed on the handlers rather than on one logger so that records from
    the application, Uvicorn and third-party libraries are all correlatable.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Set ``record.request_id`` and always keep the record.

        Args:
            record: Record about to be emitted by a handler.

        Returns:
            Always ``True`` — this filter enriches, it never suppresses.
        """
        record.request_id = current_request_id() or ABSENT_REQUEST_ID
        return True


class RequestContextMiddleware:
    """Bind one correlation id to each HTTP request and report its outcome.

    Attributes:
        app: The next ASGI application in the stack.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Wrap the downstream ASGI application.

        Args:
            app: Next application in the ASGI stack.
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Serve one connection with a request id bound to the context.

        Args:
            scope: ASGI connection scope.
            receive: ASGI receive channel.
            send: ASGI send channel.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _inbound_request_id(scope) or str(uuid4())
        token = _request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500

        async def send_with_request_id(message: Message) -> None:
            """Stamp the header on the response start, then pass it through."""
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
                headers = list(message.get("headers", []))
                headers.append((_HEADER_KEY, request_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            _log_completion(scope, status, started)
            _request_id_var.reset(token)


def _log_completion(scope: Scope, status: int, started: float) -> None:
    """Emit one metadata-only line describing how the request ended.

    Never records query strings, headers or body: those carry household
    content, which is exactly what this plan removes from the logs.

    Args:
        scope: ASGI connection scope for the finished request.
        status: HTTP status code sent to the client.
        started: ``time.perf_counter()`` reading taken when the request began.
    """
    duration_ms = int((time.perf_counter() - started) * 1000)
    method = str(scope.get("method", "-"))
    path = str(scope.get("path", "-"))
    logger.info(
        "Request: %s %s -> %d (%d ms)",
        method,
        path,
        status,
        duration_ms,
        extra={
            "event": "http.request",
            "method": method,
            "path": path,
            "status": status,
            "duration_ms": duration_ms,
        },
    )
