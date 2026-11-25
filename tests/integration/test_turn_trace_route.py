"""Plan 0089 D-13: a streaming turn's lines share the robot's id, from its start to its timing."""

from collections.abc import Iterator
import logging
from unittest.mock import AsyncMock
from uuid import UUID

from fastapi.testclient import TestClient
import pytest
from server.request_context import RequestIdFilter

from server import stt, system_memory

pytestmark = pytest.mark.integration

_TURN_ID = "8f1f2c34-0089-4d13-9a00-0000000000aa"
_TRACE_EVENTS = ("turn.start", "turn.decision", "pipeline.timing")


@pytest.fixture
def traced(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    """Capture INFO records with the request id the server's own handlers would print."""
    id_filter = RequestIdFilter()
    caplog.handler.addFilter(id_filter)
    with caplog.at_level(logging.INFO):
        yield caplog
    caplog.handler.removeFilter(id_filter)


def _post(client: TestClient, audio: bytes, request_id: str) -> None:
    response = client.post(
        "/transcribe/stream",
        files={"audio": ("a.wav", audio, "audio/wav")},
        headers={"X-Request-ID": request_id},
    )
    assert response.status_code == 200


def _trace(caplog: pytest.LogCaptureFixture) -> dict[str, logging.LogRecord]:
    return {
        str(r.__dict__["event"]): r
        for r in caplog.records
        if r.__dict__.get("event") in _TRACE_EVENTS
    }


def test_a_stream_turn_carries_the_robot_s_id_free_memory_and_decision_time(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
    traced: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value="¿Qué ves?"))
    monkeypatch.setattr(system_memory, "available_ram_mb", lambda: 4321)

    _post(client, silence_wav_bytes, _TURN_ID)

    trace = _trace(traced)
    assert set(trace) == set(_TRACE_EVENTS)
    assert {r.request_id for r in trace.values()} == {_TURN_ID}  # type: ignore[attr-defined]
    assert trace["turn.start"].ram_free_mb == 4321  # type: ignore[attr-defined]
    assert trace["pipeline.timing"].ram_free_mb == 4321  # type: ignore[attr-defined]
    decide_ms = trace["turn.decision"].decide_ms  # type: ignore[attr-defined]
    assert isinstance(decide_ms, int)
    assert decide_ms >= 0


def test_a_client_id_that_is_not_a_uuid_is_replaced_by_the_server_s(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
    traced: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value="¿Qué ves?"))

    _post(client, silence_wav_bytes, "not-a-uuid")

    (request_id,) = {r.request_id for r in _trace(traced).values()}  # type: ignore[attr-defined]
    assert request_id != "not-a-uuid"
    UUID(request_id)  # raises if the server did not put its own UUID
