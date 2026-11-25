"""Plan 0089 D-13: one turn is traced from its start to its background jobs, with numbers only.

The free memory is a double; the store and the models are doubles; canaries only.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import time
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from server.cognition.models import CognitiveEvent
from server.cognition.response_plan import TextTurnPayload, scene_unavailable_plan
from server.exceptions import LLMError
from server.memory import conversation_capture, conversation_jobs
from server.memory.candidate_proposal import propose_candidates
from server.memory.candidate_types import CandidateChannel
from server.memory.conversation_capture import CaptureOutcome, capture_turn
from server.settings import settings
from server.streaming_render import StreamState, _log_stream_metrics

from server import pipeline, system_memory, turn_log

if TYPE_CHECKING:
    import httpx

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 11, 24, 12, tzinfo=UTC)
_CANARY = "qqprivadoqq"


def _records(caplog: pytest.LogCaptureFixture, event: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.__dict__.get("event") == event]


@pytest.fixture
def free_memory(monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(system_memory, "available_ram_mb", lambda: 4321)
    return 4321


def test_a_turn_start_logs_the_free_memory(
    free_memory: int, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        turn_log.log_start("stream")

    (record,) = _records(caplog, "turn.start")
    assert record.channel == "stream"  # type: ignore[attr-defined]  # set through ``extra``
    assert record.ram_free_mb == free_memory  # type: ignore[attr-defined]


def test_a_decision_logs_how_long_it_took(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        turn_log.log_decision("stream", scene_unavailable_plan(), decide_ms=42)
        turn_log.log_decision("stream", None, decide_ms=7)
        turn_log.log_decision("chat", None)

    assert [r.decide_ms for r in _records(caplog, "turn.decision")] == [42, 7, None]  # type: ignore[attr-defined]


def test_the_timing_line_logs_the_free_memory_at_the_end(
    free_memory: int, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        pipeline._log_pipeline_timing("stream.current_perception", 900, 0, 300, 1500)

    (record,) = _records(caplog, "pipeline.timing")
    assert record.ram_free_mb == free_memory  # type: ignore[attr-defined]
    assert (record.stt_ms, record.total_ms) == (900, 1500)  # type: ignore[attr-defined]


def test_stream_done_carries_its_numbers_as_fields(caplog: pytest.LogCaptureFixture) -> None:
    state = StreamState(request_start=time.perf_counter())
    state.audio_chunks = 3
    state.first_audio_ms = 2100
    state.tts_ms_total = 800

    with caplog.at_level(logging.INFO):
        _log_stream_metrics(state, 5000)

    (record,) = _records(caplog, "stream.done")
    assert record.outcome == "ok"  # type: ignore[attr-defined]
    assert record.chunks == 3  # type: ignore[attr-defined]
    assert record.first_audio_ms == 2100  # type: ignore[attr-defined]
    assert record.tts_ms == 800  # type: ignore[attr-defined]
    assert record.total_ms == 5000  # type: ignore[attr-defined]


# --- the conversation job: what each piece of work cost, joined to its row ---


@pytest.fixture
def naming_job(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "conversation_record_enabled", True)
    monkeypatch.setattr(settings, "pending_topics_enabled", True)
    monkeypatch.setattr(settings, "conversation_episodes_enabled", False)
    monkeypatch.setattr(settings, "recall_enabled", False)
    monkeypatch.setattr(settings, "documents_enabled", False)
    monkeypatch.setattr(settings, "household_timezone", "America/Santiago")
    monkeypatch.setattr(settings, "consolidation_model", "qqmodeloqq:4b")
    monkeypatch.setattr(conversation_jobs, "close_idle_records", AsyncMock(return_value=0))
    monkeypatch.setattr(conversation_jobs, "has_open_record", AsyncMock(return_value=False))
    monkeypatch.setattr(conversation_jobs, "delete_expired", AsyncMock(return_value=0))
    monkeypatch.setattr(conversation_jobs, "set_topic", AsyncMock(return_value=True))
    monkeypatch.setattr(conversation_jobs, "count_naming_failure", AsyncMock(return_value=1))
    monkeypatch.setattr(conversation_jobs, "drop", AsyncMock())


async def test_a_named_topic_logs_its_piece_row_model_and_time(
    naming_job: None,
    monkeypatch: pytest.MonkeyPatch,
    http_client: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(conversation_jobs, "next_unnamed", AsyncMock(return_value=(5, _CANARY)))
    monkeypatch.setattr(conversation_jobs, "name_topic", AsyncMock(return_value="el banco"))

    with caplog.at_level(logging.INFO):
        await conversation_jobs.run_once(http_client, _NOW)

    (record,) = _records(caplog, "conversation.job")
    assert record.piece == "pending_naming"  # type: ignore[attr-defined]
    assert record.row_id == 5  # type: ignore[attr-defined]
    assert record.model == "qqmodeloqq:4b"  # type: ignore[attr-defined]
    assert record.outcome == "ok"  # type: ignore[attr-defined]
    assert isinstance(record.elapsed_ms, int)  # type: ignore[attr-defined]
    assert record.error_type is None  # type: ignore[attr-defined]


async def test_a_piece_that_raises_logs_its_class_and_the_tick_still_never_raises(
    naming_job: None,
    monkeypatch: pytest.MonkeyPatch,
    http_client: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(
        conversation_jobs, "next_unnamed", AsyncMock(side_effect=RuntimeError(_CANARY))
    )

    with caplog.at_level(logging.INFO):
        await conversation_jobs.run_once(http_client, _NOW)

    (record,) = _records(caplog, "conversation.job")
    assert record.piece == "pending_naming"  # type: ignore[attr-defined]
    assert record.outcome == "failed"  # type: ignore[attr-defined]
    assert record.error_type == "RuntimeError"  # type: ignore[attr-defined]
    assert record.row_id is None  # type: ignore[attr-defined]
    assert all(_CANARY not in str(r.__dict__) for r in caplog.records)


async def test_a_naming_model_failure_is_ok_for_the_piece_and_keeps_its_row(
    naming_job: None,
    monkeypatch: pytest.MonkeyPatch,
    http_client: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(conversation_jobs, "next_unnamed", AsyncMock(return_value=(9, _CANARY)))
    monkeypatch.setattr(conversation_jobs, "name_topic", AsyncMock(side_effect=LLMError("down")))

    with caplog.at_level(logging.INFO):
        await conversation_jobs.run_once(http_client, _NOW)

    (job,) = _records(caplog, "conversation.job")
    assert job.row_id == 9  # type: ignore[attr-defined]
    (named,) = _records(caplog, "pending.named")
    assert named.error_type == "LLMError"  # type: ignore[attr-defined]


# --- the capture names the row it wrote; the proposal says what it cost ---


def _event() -> CognitiveEvent[TextTurnPayload]:
    return CognitiveEvent(
        event_id=UUID(int=1),
        schema_version=1,
        event_type="text.turn",
        occurred_at=_NOW,
        recorded_at=_NOW,
        source="audio.transcribe",
        correlation_id=UUID(int=89),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message=_CANARY, conversation_id="canary-scope"),
    )


async def test_a_capture_logs_the_record_id_it_wrote(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "conversation_record_enabled", True)
    monkeypatch.setattr(conversation_capture, "append_turn", AsyncMock(return_value=77))

    with caplog.at_level(logging.INFO):
        outcome = await capture_turn(
            _CANARY,
            _CANARY,
            None,
            wav_bytes=b"RIFF-canary",
            event=_event(),
            at=_NOW,
            verify=AsyncMock(return_value=None),
            owner=AsyncMock(return_value=7),
            consented=AsyncMock(return_value=True),
            clock=lambda: _NOW,
        )

    assert outcome is CaptureOutcome.RECORDED
    (record,) = _records(caplog, "conversation.capture")
    assert record.record_id == 77  # type: ignore[attr-defined]  # set through ``extra``


async def test_a_capture_that_wrote_nothing_logs_no_record_id(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "memory_enabled", False)

    with caplog.at_level(logging.INFO):
        await capture_turn(
            _CANARY,
            _CANARY,
            None,
            wav_bytes=None,
            event=_event(),
            at=_NOW,
            clock=lambda: _NOW,
        )

    (record,) = _records(caplog, "conversation.capture")
    assert record.record_id is None  # type: ignore[attr-defined]


async def test_a_proposal_logs_its_model_and_time(
    monkeypatch: pytest.MonkeyPatch,
    http_client: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
    monkeypatch.setattr(settings, "consolidation_model", "qqmodeloqq:4b")

    with caplog.at_level(logging.INFO):
        await propose_candidates(
            http_client,
            _CANARY,
            None,  # type: ignore[arg-type]  # the switch is off: the actor is never read
            event=_event(),
            wav_bytes=None,
            channel=CandidateChannel.VOICE_STREAM,
        )

    (record,) = _records(caplog, "memory.proposal")
    assert record.model == "qqmodeloqq:4b"  # type: ignore[attr-defined]
    assert isinstance(record.elapsed_ms, int)  # type: ignore[attr-defined]
    assert record.stored == 0  # type: ignore[attr-defined]
    assert record.correlation_id == str(UUID(int=89))  # type: ignore[attr-defined]
    assert all(_CANARY not in str(r.__dict__) for r in caplog.records)
