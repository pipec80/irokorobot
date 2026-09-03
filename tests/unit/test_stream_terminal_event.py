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
async def test_a_generator_that_ends_without_any_terminal_still_gets_one() -> None:
    """Defensive check: an orchestration bug that forgets to emit done/error
    must not truncate the stream either."""
    lines = [line async for line in guarantee_terminal_event(_lines('{"type":"emotion"}\n'))]
    events = _events("".join(lines))

    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "internal_error"
