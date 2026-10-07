"""Streaming-protocol diagnosis: one observation per reply (Plan 0057, Task 4)."""

from collections.abc import AsyncIterator, Callable
import dataclasses
import itertools
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock

import httpx
import pytest
from server.exceptions import LLMError
from server.schemas import ConversationTurn, MemoryContext

from scripts.eval_stream_diagnosis import Observation, observe_once, run_diagnosis
from scripts.eval_stream_protocol import StreamOutcome, StreamTurn
from scripts.stream_diagnosis_variants import DiagnosisUnit, StreamVariant
from scripts.stream_failure_shapes import FailureShape

if TYPE_CHECKING:
    from server.cognition.identity import ActivePersonContext

_CANARY = "CANARIO-INVENTADO-731"

type StreamGenerator = Callable[..., AsyncIterator[str]]


def _client() -> httpx.AsyncClient:
    return cast("httpx.AsyncClient", Mock(spec=httpx.AsyncClient))


def _turn(
    label: str = "t", *, source: str = "context", person: bool = False, history: bool = False
) -> StreamTurn:
    return StreamTurn(
        label=label,
        source=source,
        text="hola",
        context=MemoryContext() if source == "context" else None,
        history=[ConversationTurn(role="user", content="antes")] if history else None,
        active_person=cast("ActivePersonContext", Mock()) if person else None,
    )


def _unit(variant: StreamVariant = StreamVariant.FULL) -> DiagnosisUnit:
    return DiagnosisUnit(variant, _turn())


class _FakeStream:
    """A generator stand-in that records whether it was closed and whether it resumed."""

    def __init__(self, *fragments: str, fail: bool = False) -> None:
        self._fragments = fragments
        self._fail = fail
        self.closed = False
        self.resumed = False

    async def __call__(
        self, _client: httpx.AsyncClient, _text: str, **_kwargs: object
    ) -> AsyncIterator[str]:
        try:
            for index, fragment in enumerate(self._fragments):
                if index and self.closed:
                    self.resumed = True
                yield fragment
            if self._fail:
                raise LLMError("provider failed")
        finally:
            self.closed = True


async def _observe(generate: _FakeStream, unit: DiagnosisUnit | None = None) -> Observation:
    ticks = itertools.count(0.0, 0.01)
    return await observe_once(
        unit or _unit(),
        run=1,
        position=0,
        client=_client(),
        generate=generate,
        clock=lambda: next(ticks),
    )


@pytest.mark.unit
async def test_a_valid_reply_starts_speaking_at_its_first_closed_sentence() -> None:
    obs = await _observe(_FakeStream("EMOTION:joy\nHola. ", "¿Cómo estás?"))

    assert obs.outcome is StreamOutcome.VALID
    assert obs.shape is FailureShape.VALID
    assert obs.whole_text_outcome is StreamOutcome.VALID
    assert obs.fragmentation_consistent is True
    assert obs.first_delta_ms == 10
    assert obs.speech_start_ms == 10  # the first delta already closes "Hola."
    assert obs.end_ms == 30
    assert obs.delta_count == 2
    assert obs.reply_chars == len("EMOTION:joy\nHola. ¿Cómo estás?")
    assert not obs.fell_back
    assert not obs.undue_accept


@pytest.mark.unit
async def test_a_prefix_split_across_deltas_is_no_longer_an_undue_accept() -> None:
    """The 0057 fragmentation defect, repaired: production waits for the rest of "EMO"."""
    obs = await _observe(_FakeStream("EMOTION:joy\nEMO", "TION:anger\nhola"))

    assert obs.outcome is StreamOutcome.INVALID_PROTOCOL
    assert obs.whole_text_outcome is StreamOutcome.INVALID_PROTOCOL
    assert obs.fragmentation_consistent is True
    assert not obs.undue_accept


@pytest.mark.unit
async def test_an_invalid_body_start_decides_at_once_and_closes_the_stream() -> None:
    generate = _FakeStream("EMOTION:joy\n{", "never consumed")

    obs = await _observe(generate)

    assert obs.outcome is StreamOutcome.INVALID_PROTOCOL
    assert obs.shape is FailureShape.BODY_JSON
    assert obs.fell_back
    assert obs.speech_start_ms == obs.first_delta_ms == 10
    assert obs.delta_count == 1
    assert (generate.closed, generate.resumed) == (True, False)


@pytest.mark.unit
async def test_a_reply_without_the_tag_waits_for_the_end_of_the_stream() -> None:
    obs = await _observe(_FakeStream("Hola ", "sin etiqueta."))

    assert obs.outcome is StreamOutcome.INVALID_PROTOCOL
    assert obs.shape is FailureShape.NO_TAG
    assert obs.speech_start_ms == obs.end_ms == 30
    assert obs.first_delta_ms == 10


@pytest.mark.unit
async def test_an_empty_stream_is_an_empty_observation() -> None:
    obs = await _observe(_FakeStream())

    assert obs.outcome is StreamOutcome.EMPTY_STREAM
    assert obs.shape is FailureShape.EMPTY
    assert obs.first_delta_ms is None
    assert obs.fell_back


@pytest.mark.unit
async def test_a_provider_error_is_an_error_not_a_protocol_verdict() -> None:
    obs = await _observe(_FakeStream("EMOTION:joy\nHola", fail=True))

    assert obs.outcome is StreamOutcome.ERROR
    assert obs.shape is None
    assert obs.whole_text_outcome is None
    assert obs.fragmentation_consistent is None
    assert not obs.fell_back
    assert not obs.undue_accept


@pytest.mark.unit
async def test_an_observation_never_holds_the_reply_text() -> None:
    obs = await _observe(_FakeStream(f"EMOTION:joy\n{_CANARY}. ", f"{_CANARY}."))

    assert _CANARY not in repr(obs)
    text_fields = [
        field.name
        for field in dataclasses.fields(Observation)
        if field.type in ("str", str) and field.name not in {"source", "label"}
    ]
    assert text_fields == []


@pytest.mark.unit
async def test_the_diagnosis_runs_every_unit_and_keeps_provider_errors_apart() -> None:
    replies: list[str | Exception] = ["EMOTION:joy\nHola.", LLMError("boom"), "sin etiqueta"]
    queue = iter(replies)

    def generate_for(_variant: StreamVariant) -> StreamGenerator:
        async def generate(
            _client: httpx.AsyncClient, _text: str, **_kwargs: object
        ) -> AsyncIterator[str]:
            reply = next(queue)
            if isinstance(reply, Exception):
                raise reply
            yield reply

        return generate

    units = [_unit(), _unit(StreamVariant.NO_CONTEXT), _unit(StreamVariant.QUESTION_ONLY)]
    observations = await run_diagnosis(
        units, client=_client(), runs=1, seed=1, generate_for=generate_for
    )

    assert sorted(o.position for o in observations) == [0, 1, 2]
    assert {o.outcome for o in observations} == {
        StreamOutcome.VALID,
        StreamOutcome.ERROR,
        StreamOutcome.INVALID_PROTOCOL,
    }


class _BrokenClose:
    """A stream whose ``aclose`` fails after it has already delivered its reply."""

    def __call__(self, _client: httpx.AsyncClient, _text: str, **_kwargs: object) -> "_BrokenClose":
        return self

    def __aiter__(self) -> AsyncIterator[str]:
        return self._deltas()

    @staticmethod
    async def _deltas() -> AsyncIterator[str]:
        yield "EMOTION:joy\nHola. Bien."

    async def aclose(self) -> None:
        raise RuntimeError("close failed")


@pytest.mark.unit
async def test_a_stream_that_fails_to_close_does_not_cost_the_observation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One bad close must not lose the hundreds of observations measured around it."""
    with caplog.at_level("WARNING"):
        obs = await observe_once(
            _unit(),
            run=1,
            position=0,
            client=_client(),
            generate=cast("StreamGenerator", _BrokenClose()),
            clock=itertools.count(0.0, 0.01).__next__,
        )

    assert obs.outcome is StreamOutcome.VALID
    assert "RuntimeError" in caplog.text
    assert "close failed" not in caplog.text
