"""Streaming-protocol measurement (Plan 0056, Task 4)."""

from collections.abc import AsyncIterator
import logging
import re
import time
from typing import cast
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from server.exceptions import LLMError
from server.streaming_render import StreamState

from scripts.eval_stream_protocol import (
    StreamOutcome,
    StreamProtocolResult,
    StreamTurn,
    classify_deltas,
    measure_stream_protocol,
    public_turns,
    render_stream_report,
    stream_exit_code,
)
from scripts.stream_fragmentation import reply_fragmentations
from server import streaming, tts

_FENCE = "`" * 3  # built, not written: this file also lives inside a Markdown code fence

_REPLIES = [
    "EMOTION:joy\nHola, ¿cómo estás?",
    "EMOTION:joy\nHola. ¿Cómo estás? Muy bien.",
    "EMOTION:joy\n",
    "EMOTION:joy\n   ",
    "EMOTION:joy",
    "",
    "  \n",
    "Hola sin etiqueta",
    'EMOTION:joy\n{"response": "x"}',
    "EMOTION:joy\n[1]",
    f"EMOTION:joy\n{_FENCE}json\n{{}}\n{_FENCE}",
    "EMOTION:joy\nEMOTION:anger\nhola",
    "EMOTION:unknownemotion\nHola",
    "emotion: joy\nHola",
]


@pytest.mark.unit
@pytest.mark.parametrize(
    "deltas, outcome",
    [
        (["EMOTION:joy\nHola, ¿cómo estás?"], StreamOutcome.VALID),
        (["EMOTION:joy\n"], StreamOutcome.INVALID_PROTOCOL),
        (["EMOTION:joy\n   "], StreamOutcome.INVALID_PROTOCOL),
        (["Hola sin etiqueta"], StreamOutcome.INVALID_PROTOCOL),
        (['EMOTION:joy\n{"response": "x"}'], StreamOutcome.INVALID_PROTOCOL),
        (["EMOTION:joy\nEMOTION:anger\nhola"], StreamOutcome.INVALID_PROTOCOL),
        (["EMOTION:joy"], StreamOutcome.INVALID_PROTOCOL),
        ([], StreamOutcome.EMPTY_STREAM),
        (["  \n"], StreamOutcome.EMPTY_STREAM),
    ],
)
def test_classify_deltas_reports_the_production_outcome(
    deltas: list[str], outcome: StreamOutcome
) -> None:
    assert classify_deltas(deltas) is outcome


@pytest.mark.unit
def test_the_outcome_depends_on_how_the_reply_is_fragmented_exactly_as_in_production() -> None:
    """Production stops validating once the body start is accepted ("EMO" is not a tag)."""
    reply = "EMOTION:joy\nEMOTION:anger\nhola"

    assert classify_deltas([reply]) is StreamOutcome.INVALID_PROTOCOL
    assert classify_deltas(["EMOTION:joy\nEMO", "TION:anger\nhola"]) is StreamOutcome.VALID


async def _production_result(
    fragments: list[str], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> tuple[bool, str | None]:
    """Run the real streaming consumer and return (fell back, logged fallback reason)."""

    async def deltas(_client: object, _inputs: object) -> AsyncIterator[str]:
        for fragment in fragments:
            yield fragment

    monkeypatch.setattr(streaming, "_text_deltas", deltas)
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("QQ==", 10)))
    state = StreamState(request_start=time.perf_counter())
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="server.streaming_render"):
        async for _line in streaming._consume_llm_stream(
            cast("httpx.AsyncClient", Mock()), cast("streaming.PreparedTextTurn", None), state
        ):
            pass
    match = re.search(r"reason=(\w+)", caplog.text)
    return state.recordable is False, match.group(1) if match else None


@pytest.mark.unit
@pytest.mark.parametrize("reply", _REPLIES)
async def test_the_evaluator_agrees_with_production_for_every_fragmentation(
    reply: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Equivalence: the measured rate is the rate production would have lived."""
    expected = {
        None: StreamOutcome.VALID,
        "invalid_protocol": StreamOutcome.INVALID_PROTOCOL,
        "empty_stream": StreamOutcome.EMPTY_STREAM,
    }
    for fragments in reply_fragmentations(reply):
        fell_back, reason = await _production_result(fragments, monkeypatch, caplog)

        assert fell_back == (reason is not None)
        assert classify_deltas(fragments) is expected[reason], fragments


async def _production_after_a_provider_error(
    fragments: list[str], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> str:
    """Run the real consumer on a stream that fails after its fragments."""

    async def deltas(_client: object, _inputs: object) -> AsyncIterator[str]:
        for fragment in fragments:
            yield fragment
        raise LLMError("provider failed")

    monkeypatch.setattr(streaming, "_text_deltas", deltas)
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("QQ==", 10)))
    state = StreamState(request_start=time.perf_counter())
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="server.streaming_render"):
        try:
            async for _line in streaming._consume_llm_stream(
                cast("httpx.AsyncClient", Mock()), cast("streaming.PreparedTextTurn", None), state
            ):
                pass
        except LLMError:
            return "provider_error"
    match = re.search(r"reason=(\w+)", caplog.text)
    return match.group(1) if match else "ok"


async def _evaluator_after_a_provider_error(fragments: list[str]) -> str:
    """Measure one stream that fails after its fragments and name the single outcome."""

    async def generate(
        _client: httpx.AsyncClient, _text: str, **_kwargs: object
    ) -> AsyncIterator[str]:
        for fragment in fragments:
            yield fragment
        raise LLMError("provider failed")

    result = await measure_stream_protocol([_turn()], client=_client(), runs=1, generate=generate)
    if result.errors:
        return "provider_error"
    return "invalid_protocol" if result.invalid_protocol else "other"


@pytest.mark.unit
@pytest.mark.parametrize(
    "fragments, expected",
    [
        (["EMOTION:joy\n{"], "invalid_protocol"),
        (["EMOTION:joy\n", "[1]"], "invalid_protocol"),
        (["EMOTION:joy\nHola"], "provider_error"),
        (["EMOTION:joy\n"], "provider_error"),
        (["Hola sin etiqueta"], "provider_error"),
        ([], "provider_error"),
    ],
)
async def test_a_provider_error_after_production_decided_is_not_an_error(
    fragments: list[str],
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Production stops at an invalid start, so a later provider error never happens live."""
    assert await _production_after_a_provider_error(fragments, monkeypatch, caplog) == expected
    assert await _evaluator_after_a_provider_error(fragments) == expected


@pytest.mark.unit
async def test_the_evaluator_stops_and_closes_the_stream_when_production_would_stop() -> None:
    closed: list[bool] = []
    resumed: list[bool] = []

    async def generate(
        _client: httpx.AsyncClient, _text: str, **_kwargs: object
    ) -> AsyncIterator[str]:
        try:
            yield "EMOTION:joy\n{"
            resumed.append(True)
            yield "never consumed"
        finally:
            closed.append(True)

    result = await measure_stream_protocol([_turn()], client=_client(), runs=1, generate=generate)

    assert result.invalid_protocol == 1
    assert resumed == []
    assert closed == [True]


def _client() -> httpx.AsyncClient:
    return cast("httpx.AsyncClient", Mock(spec=httpx.AsyncClient))


def _turn(source: str = "public") -> StreamTurn:
    return StreamTurn(
        label="t", source=source, text="hola", context=None, history=None, active_person=None
    )


def _generator(replies: list[str | Exception]):
    queue = list(replies)

    async def generate(
        _client: httpx.AsyncClient, _text: str, **_kwargs: object
    ) -> AsyncIterator[str]:
        reply = queue.pop(0)
        if isinstance(reply, Exception):
            raise reply
        midpoint = len(reply) // 2
        for piece in (reply[:midpoint], reply[midpoint:]):
            if piece:
                yield piece

    return generate


@pytest.mark.unit
async def test_measure_counts_each_outcome_and_keeps_errors_out_of_the_rate() -> None:
    result = await measure_stream_protocol(
        [_turn(), _turn(), _turn(), _turn(), _turn()],
        client=_client(),
        runs=1,
        generate=_generator(
            ["EMOTION:joy\nHola", "sin etiqueta", "", "EMOTION:joy\n", LLMError("boom")]
        ),
    )

    assert (result.valid, result.invalid_protocol, result.empty_stream, result.errors) == (
        1,
        2,
        1,
        1,
    )
    assert result.graded == 4
    assert result.fallback_rate == pytest.approx(3 / 4)


@pytest.mark.unit
async def test_measure_splits_the_counts_by_turn_source() -> None:
    result = await measure_stream_protocol(
        [_turn("context"), _turn("public")],
        client=_client(),
        runs=2,
        generate=_generator(
            ["EMOTION:joy\nHola", "EMOTION:joy\nHola", "sin etiqueta", "sin etiqueta"]
        ),
    )

    assert result.by_source["context"].fallback_rate == 0.0
    assert result.by_source["public"].fallback_rate == 1.0


@pytest.mark.unit
def test_the_fallback_rate_is_none_when_nothing_was_graded() -> None:
    assert StreamProtocolResult.none().fallback_rate is None


@pytest.mark.unit
def test_public_turns_are_synthetic_and_context_free() -> None:
    turns = public_turns()

    assert len(turns) == 12
    assert all(t.source == "public" and t.context is None and t.history is None for t in turns)
    assert any("Tom" in t.text for t in turns)


@pytest.mark.unit
def test_exit_code_applies_the_threshold_and_provider_errors() -> None:
    clean = StreamProtocolResult(
        valid=19, invalid_protocol=1, empty_stream=0, errors=0, by_source={}
    )
    errored = StreamProtocolResult(
        valid=19, invalid_protocol=0, empty_stream=0, errors=1, by_source={}
    )

    assert stream_exit_code(clean, max_fallback_rate=None) == 0
    assert stream_exit_code(clean, max_fallback_rate=0.10) == 0
    assert stream_exit_code(clean, max_fallback_rate=0.04) == 1
    assert stream_exit_code(errored, max_fallback_rate=None) == 1


@pytest.mark.unit
def test_the_report_states_the_rate_and_never_prints_model_output() -> None:
    report = render_stream_report(
        StreamProtocolResult(valid=57, invalid_protocol=3, empty_stream=0, errors=0, by_source={}),
        model="qwen2.5:3b",
        runs=5,
    )

    assert "fallback rate" in report.lower()
    assert "5.00 %" in report
    assert "qwen2.5:3b" in report
