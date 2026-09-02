"""Unit tests for the per-request correlation context (Plan 0032).

The middleware is pure ASGI on purpose: `BaseHTTPMiddleware` would buffer the
NDJSON stream that `POST /transcribe/stream` depends on.
"""

from concurrent.futures import ThreadPoolExecutor
import logging
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from server.request_context import (
    ABSENT_REQUEST_ID,
    RequestContextMiddleware,
    RequestIdFilter,
    current_request_id,
    run_in_executor_with_context,
)

_HEADER = "X-Request-ID"


def _app_echoing_context() -> FastAPI:
    """Build a minimal app whose route reports the ambient request id."""
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/probe")
    async def probe() -> dict[str, str | None]:
        return {"seen": current_request_id()}

    return app


@pytest.mark.unit
def test_response_carries_a_generated_uuid_when_none_is_supplied() -> None:
    """A caller that sends no correlation header still gets one back."""
    with TestClient(_app_echoing_context()) as client:
        response = client.get("/probe")

    assert response.status_code == 200
    UUID(response.headers[_HEADER])  # raises if it is not a real UUID


@pytest.mark.unit
def test_a_valid_inbound_uuid_is_preserved() -> None:
    """An upstream correlation id must survive so one turn stays traceable."""
    supplied = "3f8b7d16-2c4a-4f5e-9a1b-8c7d6e5f4a3b"

    with TestClient(_app_echoing_context()) as client:
        response = client.get("/probe", headers={_HEADER: supplied})

    assert response.headers[_HEADER] == supplied
    assert response.json()["seen"] == supplied


@pytest.mark.unit
@pytest.mark.parametrize(
    "supplied",
    ["not-a-uuid", "", "../../etc/passwd", "a" * 4096, "<script>alert(1)</script>"],
    ids=["malformed", "empty", "traversal", "oversized", "injection"],
)
def test_an_untrusted_inbound_value_is_replaced_not_echoed(supplied: str) -> None:
    """The header is client-controlled, so a non-UUID is discarded entirely."""
    with TestClient(_app_echoing_context()) as client:
        response = client.get("/probe", headers={_HEADER: supplied})

    returned = response.headers[_HEADER]
    UUID(returned)
    assert returned != supplied


@pytest.mark.unit
def test_the_route_sees_the_same_id_the_response_reports() -> None:
    """A log line written inside the request must correlate with the response."""
    with TestClient(_app_echoing_context()) as client:
        response = client.get("/probe")

    assert response.json()["seen"] == response.headers[_HEADER]


@pytest.mark.unit
def test_context_is_reset_after_the_request_completes() -> None:
    """A leaked ContextVar would misattribute later work to a finished request."""
    with TestClient(_app_echoing_context()) as client:
        client.get("/probe")

    assert current_request_id() is None


@pytest.mark.unit
def test_sequential_requests_never_share_an_id() -> None:
    """Two turns must be distinguishable in the log stream."""
    with TestClient(_app_echoing_context()) as client:
        first = client.get("/probe").headers[_HEADER]
        second = client.get("/probe").headers[_HEADER]

    assert first != second


@pytest.mark.unit
def test_context_is_reset_even_when_the_route_raises() -> None:
    """A failing turn must not leave its id bound to the next one."""
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/boom")
    async def boom() -> dict[str, str]:
        raise RuntimeError("route failed")

    with TestClient(app, raise_server_exceptions=False) as client:
        client.get("/boom")

    assert current_request_id() is None


@pytest.mark.unit
def test_completion_event_reports_metadata_only(caplog: pytest.LogCaptureFixture) -> None:
    """The access line carries method, path, status and duration — never content."""
    with caplog.at_level(logging.INFO), TestClient(_app_echoing_context()) as client:
        client.get("/probe")

    completions = [r for r in caplog.records if getattr(r, "event", None) == "http.request"]
    assert len(completions) == 1
    record: Any = completions[0]
    assert record.method == "GET"
    assert record.path == "/probe"
    assert record.status == 200
    assert record.duration_ms >= 0


@pytest.mark.unit
def test_the_filter_stamps_records_written_during_a_request() -> None:
    """Correlating STT, LLM and TTS lines for one turn is the whole point."""
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    stamped: list[str] = []

    @app.get("/emit")
    async def emit() -> dict[str, str]:
        record = logging.LogRecord("t", logging.INFO, __file__, 1, "work", None, None)
        RequestIdFilter().filter(record)
        stamped.append(getattr(record, "request_id"))  # noqa: B009 — injected by the filter
        return {"ok": "yes"}

    with TestClient(app) as client:
        response = client.get("/emit")

    assert stamped == [response.headers[_HEADER]]


@pytest.mark.unit
def test_the_filter_marks_records_written_outside_any_request() -> None:
    """Startup and the retention job have no request; they must not look like one."""
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "background", None, None)

    kept = RequestIdFilter().filter(record)

    assert kept is True, "the filter enriches records, it must never drop them"
    assert getattr(record, "request_id") == ABSENT_REQUEST_ID  # noqa: B009 — injected


@pytest.mark.unit
def test_context_reaches_work_dispatched_to_a_thread_executor() -> None:
    """STT, TTS and face detection run in executors — the slowest part of a turn.

    `loop.run_in_executor` does not copy the ambient context into the worker
    thread, so without an explicit copy every log line emitted by Whisper or
    Piper is orphaned from the request that caused it. Observed live on
    2026-09-02: `faster_whisper` and `server.stt` logged under `-` while the
    rest of the same turn carried its id.
    """
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    executor = ThreadPoolExecutor(max_workers=1)
    seen: list[str | None] = []

    def blocking_work() -> str | None:
        return current_request_id()

    @app.get("/offload")
    async def offload() -> dict[str, str]:
        seen.append(await run_in_executor_with_context(executor, blocking_work))
        return {"ok": "yes"}

    try:
        with TestClient(app) as client:
            response = client.get("/offload")
    finally:
        executor.shutdown(wait=True)

    assert seen == [response.headers[_HEADER]]
