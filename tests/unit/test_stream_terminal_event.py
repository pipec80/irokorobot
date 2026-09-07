"""Unit tests for streaming.guarantee_terminal_event (Plan 0041).

The wrapper is the single boundary applied to every stream producer at the
router: whatever the inner generator does, exactly one `done` or `error`
terminal event must reach the client, followed by EOF — never a raised
exception that truncates the connection.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import pytest
from server.exceptions import TTSError
from server.streaming import guarantee_terminal_event

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


async def _lines(*items: str) -> AsyncIterator[str]:
    for item in items:
        yield item


def _events(text: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in text.strip().split("\n") if line.strip()]


@pytest.mark.unit
async def test_a_normal_stream_passes_through_unchanged() -> None:
    """No failure at all: the wrapper must not alter a single byte."""
    done_line = '{"type":"done","stt_ms":1,"llm_ms":1,"tts_ms":1,"total_ms":3}\n'
    lines = [
        line async for line in guarantee_terminal_event(_lines('{"type":"emotion"}\n', done_line))
    ]

    assert lines == ['{"type":"emotion"}\n', done_line]


@pytest.mark.unit
async def test_a_tts_failure_emits_one_error_event_instead_of_raising() -> None:
    async def _failing() -> AsyncIterator[str]:
        yield '{"type":"emotion"}\n'
        raise TTSError("piper down")

    lines = [line async for line in guarantee_terminal_event(_failing())]
    events = _events("".join(lines))

    assert [e["type"] for e in events] == ["emotion", "error"]
    assert events[-1]["code"] == "tts_failed"
    assert events[-1]["retryable"] is True
    assert "piper" not in str(events[-1]["detail"])  # never the raw provider exception text


@pytest.mark.unit
async def test_an_unexpected_exception_emits_a_generic_internal_error_event() -> None:
    """A genuinely unforeseen bug must still close the stream with one terminal."""

    async def _broken() -> AsyncIterator[str]:
        yield '{"type":"emotion"}\n'
        raise RuntimeError("secret internal detail")

    lines = [line async for line in guarantee_terminal_event(_broken())]
    events = _events("".join(lines))

    assert [e["type"] for e in events] == ["emotion", "error"]
    assert events[-1]["code"] == "internal_error"
    assert events[-1]["retryable"] is False
    assert "secret internal detail" not in "".join(lines)
    assert "RuntimeError" not in "".join(lines)


@pytest.mark.unit
async def test_cancellation_propagates_untouched_and_emits_nothing() -> None:
    """A client disconnect must never trigger an emit into a dead transport."""

    async def _cancelled() -> AsyncIterator[str]:
        yield '{"type":"emotion"}\n'
        raise asyncio.CancelledError

    collected: list[str] = []
    with pytest.raises(asyncio.CancelledError):  # noqa: PT012 — must collect lines before it raises
        async for line in guarantee_terminal_event(_cancelled()):
            collected.append(line)

    assert collected == ['{"type":"emotion"}\n']


@pytest.mark.unit
async def test_done_then_producer_exception_emits_only_done() -> None:
    """A producer that raises AFTER its terminal event must not get a second one."""

    async def _done_then_raises() -> AsyncIterator[str]:
        yield '{"type":"emotion"}\n'
        yield '{"type":"done","stt_ms":1,"llm_ms":1,"tts_ms":1,"total_ms":3}\n'
        raise RuntimeError("producer bug after done")

    lines = [line async for line in guarantee_terminal_event(_done_then_raises())]
    events = _events("".join(lines))

    assert [e["type"] for e in events] == ["emotion", "done"]


@pytest.mark.unit
async def test_tts_error_after_done_appends_no_second_terminal() -> None:
    """A post-terminal TTSError is logged and swallowed, never a second `error`."""

    async def _done_then_tts_error() -> AsyncIterator[str]:
        yield '{"type":"done","stt_ms":1,"llm_ms":1,"tts_ms":1,"total_ms":3}\n'
        raise TTSError("piper died on cleanup")

    lines = [line async for line in guarantee_terminal_event(_done_then_tts_error())]
    events = _events("".join(lines))

    assert [e["type"] for e in events] == ["done"]


@pytest.mark.unit
async def test_a_line_after_done_is_dropped_not_forwarded() -> None:
    """Once the terminal event passed, further producer lines are dropped."""

    async def _done_then_extra_line() -> AsyncIterator[str]:
        yield '{"type":"done","stt_ms":1,"llm_ms":1,"tts_ms":1,"total_ms":3}\n'
        yield '{"type":"audio","text":"x","audio_base64":"","duration_ms":0}\n'

    lines = [line async for line in guarantee_terminal_event(_done_then_extra_line())]
    events = _events("".join(lines))

    assert [e["type"] for e in events] == ["done"]


@pytest.mark.unit
async def test_error_then_producer_exception_emits_only_error() -> None:
    """A producer that emits its own `error` then raises keeps exactly that one."""

    async def _error_then_raises() -> AsyncIterator[str]:
        yield '{"type":"error","code":"tts_failed","detail":"x","retryable":true}\n'
        raise RuntimeError("producer bug after error")

    lines = [line async for line in guarantee_terminal_event(_error_then_raises())]
    events = _events("".join(lines))

    assert [e["type"] for e in events] == ["error"]
    assert events[0]["code"] == "tts_failed"


@pytest.mark.unit
async def test_a_non_json_line_is_forwarded_without_crashing() -> None:
    """A malformed producer line is passed through, not treated as terminal."""

    async def _malformed_then_done() -> AsyncIterator[str]:
        yield "not json at all\n"
        yield '{"type":"done","stt_ms":0,"llm_ms":0,"tts_ms":0,"total_ms":0}\n'

    lines = [line async for line in guarantee_terminal_event(_malformed_then_done())]

    assert lines[0] == "not json at all\n"
    assert _events(lines[1])[-1]["type"] == "done"


@pytest.mark.unit
async def test_a_generator_that_ends_without_any_terminal_still_gets_one() -> None:
    """Defensive check: an orchestration bug that forgets to emit done/error
    must not truncate the stream either."""
    lines = [line async for line in guarantee_terminal_event(_lines('{"type":"emotion"}\n'))]
    events = _events("".join(lines))

    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "internal_error"
