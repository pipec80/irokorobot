"""Streaming-protocol measurement for `just eval-chat --mode stream` (Plan 0056).

Runs real turns through the production streaming generator and consumes the deltas the
way `server.streaming._consume_llm_stream` does: incrementally, with the production
helpers, so a reply is judged exactly as it would be live. A test pins the equivalence
against the real consumer for several fragmentations. It measures
how often a reply would drop to the fallback phrase (0049 O-04); it never prints or
stores model output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import enum
import logging
from typing import TYPE_CHECKING

from server.streaming_protocol import StreamProtocolError
from server.streaming_render import (
    StreamFallbackReason,
    StreamState,
    _consume_body,
    _consume_preamble,
    classify_stream_end,
)

from server import llm_streaming

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterable, Sequence

    import httpx
    from server.cognition.identity import ActivePersonContext
    from server.schemas import ConversationTurn, MemoryContext

    type StreamGenerator = Callable[..., AsyncIterator[str]]

logger = logging.getLogger(__name__)

_PERCENT = 100
_SOURCES = ("context", "public")
_PUBLIC_UTTERANCES = (
    "Hola, ¿cómo estás?",
    "Te presento a mi amigo Tom.",
    "¿Qué opinas del clima hoy?",
    "Cuéntame algo interesante.",
    "Estoy un poco cansado hoy.",
    "¿Qué sabes hacer?",
    "Buenas noches, Iroko.",
    "Gracias por la ayuda.",
    "¿Puedes decirme un chiste?",
    "Hoy fue un día largo.",
    "¿Cómo se prepara un té?",
    "Me gusta la música tranquila.",
)


class StreamOutcome(enum.StrEnum):
    """How one streamed reply ends; the fallback reasons mirror production's."""

    VALID = "valid"
    INVALID_PROTOCOL = "invalid_protocol"
    EMPTY_STREAM = "empty_stream"
    ERROR = "error"


def _classify_end_of_stream(buffer: str, state: StreamState) -> StreamOutcome:
    """Map production's end-of-stream judgement (`classify_stream_end`) to an outcome."""
    reason = classify_stream_end(buffer, state)
    if reason is None:
        return StreamOutcome.VALID
    if reason is StreamFallbackReason.EMPTY_STREAM:
        return StreamOutcome.EMPTY_STREAM
    return StreamOutcome.INVALID_PROTOCOL


class _StreamClassifier:
    """Consume deltas one at a time, exactly as `streaming._consume_llm_stream` does."""

    def __init__(self) -> None:
        self._state = StreamState(request_start=0.0)
        self._buffer = ""
        self.sentences_seen = 0

    def feed(self, delta: str) -> StreamOutcome | None:
        """Take one delta; return ``INVALID_PROTOCOL`` once production would stop reading.

        Returns:
            The decided outcome, or ``None`` while production would keep consuming.
        """
        self._buffer += delta
        try:
            if self._state.pending_emotion is None and self._state.emotion is None:
                self._buffer, consumed = _consume_preamble(self._buffer, self._state)
                if not consumed:
                    return None
            self._buffer, sentences = _consume_body(self._buffer, self._state)
        except StreamProtocolError:
            return StreamOutcome.INVALID_PROTOCOL
        self.sentences_seen += len(sentences)
        return None

    def finish(self) -> StreamOutcome:
        """Decide the outcome once the stream has ended without an earlier decision."""
        return _classify_end_of_stream(self._buffer, self._state)


def classify_deltas(deltas: Iterable[str]) -> StreamOutcome:
    """Classify one streamed reply the way production consumes it.

    Args:
        deltas: The text deltas in arrival order (empty deltas never occur live).

    Returns:
        ``VALID``, ``INVALID_PROTOCOL`` or ``EMPTY_STREAM`` (nothing but whitespace).
    """
    classifier = _StreamClassifier()
    for delta in deltas:
        decided = classifier.feed(delta)
        if decided is not None:
            return decided
    return classifier.finish()


@dataclass(frozen=True)
class StreamTurn:
    """One user turn to stream; ``source`` says where it came from."""

    label: str
    source: str
    text: str
    context: MemoryContext | None
    history: list[ConversationTurn] | None
    active_person: ActivePersonContext | None

    def __post_init__(self) -> None:
        """Reject an unknown source so a typo cannot create a silent third bucket."""
        if self.source not in _SOURCES:
            raise ValueError(f"source must be one of {_SOURCES}, got {self.source!r}")


def public_turns() -> list[StreamTurn]:
    """Return the synthetic, context-free chit-chat turns (public-channel shape)."""
    return [
        StreamTurn(f"public_{index}", "public", text, None, None, None)
        for index, text in enumerate(_PUBLIC_UTTERANCES, start=1)
    ]


@dataclass(frozen=True)
class StreamProtocolResult:
    """Outcome counts of one measurement, overall and per turn source."""

    valid: int
    invalid_protocol: int
    empty_stream: int
    errors: int
    by_source: dict[str, StreamProtocolResult] = field(default_factory=dict)

    @classmethod
    def none(cls) -> StreamProtocolResult:
        """Return a result with no observations."""
        return cls(0, 0, 0, 0)

    @property
    def graded(self) -> int:
        """Observations that count toward the rate (provider errors excluded)."""
        return self.valid + self.invalid_protocol + self.empty_stream

    @property
    def fallback_rate(self) -> float | None:
        """Share of graded replies that would drop to the fallback phrase."""
        if not self.graded:
            return None
        return (self.invalid_protocol + self.empty_stream) / self.graded


def _tally(outcomes: Sequence[StreamOutcome]) -> StreamProtocolResult:
    return StreamProtocolResult(
        valid=outcomes.count(StreamOutcome.VALID),
        invalid_protocol=outcomes.count(StreamOutcome.INVALID_PROTOCOL),
        empty_stream=outcomes.count(StreamOutcome.EMPTY_STREAM),
        errors=outcomes.count(StreamOutcome.ERROR),
    )


async def _stream_once(
    turn: StreamTurn, client: httpx.AsyncClient, generate: StreamGenerator
) -> StreamOutcome:
    """Classify one live stream while it arrives and stop when production would stop.

    A provider error that comes after production has already decided (an invalid body
    start) never happens live, so it must not turn that observation into an ``ERROR``.
    """
    classifier = _StreamClassifier()
    stream = generate(
        client,
        turn.text,
        context=turn.context,
        history=turn.history,
        active_person=turn.active_person,
    )
    try:
        async for delta in stream:
            if not delta:
                continue
            decided = classifier.feed(delta)
            if decided is not None:
                return decided
    except Exception as exc:
        logger.warning("Provider call failed for %s (%s)", turn.label, type(exc).__name__)
        return StreamOutcome.ERROR
    finally:
        # Stop the model generating: an abandoned async generator would keep the HTTP
        # stream (and Ollama) running until it is garbage collected.
        aclose = getattr(stream, "aclose", None)
        if aclose is not None:
            await aclose()
    return classifier.finish()


async def measure_stream_protocol(
    turns: Sequence[StreamTurn],
    *,
    client: httpx.AsyncClient,
    runs: int,
    generate: StreamGenerator = llm_streaming.generate_response_stream,
) -> StreamProtocolResult:
    """Stream every turn ``runs`` times sequentially and tally the protocol outcomes.

    Args:
        turns: Synthetic turns, in execution order.
        client: Run-owned HTTP client, passed first to the generator (Plan 0039).
        runs: Repetitions per turn.
        generate: Streaming generator; the production one unless a test injects one.

    Returns:
        Overall and per-source counts. Provider errors are counted separately and
        never as a protocol failure or a pass.
    """
    outcomes: list[StreamOutcome] = []
    by_source: dict[str, list[StreamOutcome]] = {}
    for turn in turns:
        for _ in range(runs):
            outcome = await _stream_once(turn, client, generate)
            outcomes.append(outcome)
            by_source.setdefault(turn.source, []).append(outcome)
    overall = _tally(outcomes)
    return StreamProtocolResult(
        overall.valid,
        overall.invalid_protocol,
        overall.empty_stream,
        overall.errors,
        {source: _tally(items) for source, items in by_source.items()},
    )


def _percent(rate: float | None) -> str:
    return "n/a" if rate is None else f"{rate * _PERCENT:.2f} %"


def render_stream_report(result: StreamProtocolResult, *, model: str, runs: int) -> str:
    """Render the measurement as Markdown: counts and rates only, never model output."""
    rows = [
        "| Set | Valid | Invalid protocol | Empty stream | Provider errors | Fallback rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, part in (("all", result), *sorted(result.by_source.items())):
        rows.append(
            f"| {label} | {part.valid} | {part.invalid_protocol} | {part.empty_stream} | "
            f"{part.errors} | {_percent(part.fallback_rate)} |"
        )
    return (
        "# Streaming protocol measurement\n\n"
        f"- model: {model}\n- runs per turn: {runs}\n"
        f"- graded observations: {result.graded}\n"
        f"- fallback rate (invalid protocol + empty stream, over graded): "
        f"{_percent(result.fallback_rate)}\n\n" + "\n".join(rows) + "\n"
    )


def stream_exit_code(result: StreamProtocolResult, *, max_fallback_rate: float | None) -> int:
    """Return 1 on a provider error or a fallback rate above the optional limit, else 0."""
    if result.errors:
        return 1
    rate = result.fallback_rate
    if max_fallback_rate is not None and rate is not None and rate > max_fallback_rate:
        return 1
    return 0
