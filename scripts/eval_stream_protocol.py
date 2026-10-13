"""Streaming-protocol measurement for `just eval-chat --mode stream` (Plan 0056).

Runs real turns through the production streaming generator and consumes the deltas the
way `server.streaming._consume_llm_stream` does: incrementally, with the production
helpers, so a reply is judged exactly as it would be live. A test pins the equivalence
against the real consumer for several fragmentations. It measures the generator only (the
turn's emotion is decided apart from the reply, so it is preset to the neutral fallback
here) and how often a reply would drop to the fallback phrase (0049 O-04); it never
prints or stores model output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import enum
import logging
from typing import TYPE_CHECKING

from server.llm import FALLBACK_EMOTION
from server.schemas import ConversationTurn
from server.streaming_protocol import StreamProtocolError
from server.streaming_render import (
    StreamFallbackReason,
    StreamState,
    _consume_body,
    classify_stream_end,
)

from scripts.reply_language import judge_language
from server import llm_streaming

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterable, Sequence

    import httpx
    from server.cognition.identity import ActivePersonContext
    from server.schemas import MemoryContext

    type StreamGenerator = Callable[..., AsyncIterator[str]]

logger = logging.getLogger(__name__)

_PERCENT = 100
_SOURCES = ("context", "public", "history")
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


# Invented one-line facts followed by a question that only the history answers (ADR 0020
# §7). Each entry is (labelled exchanges, question): no household data of any kind.
_HISTORY_DIALOGUES: tuple[tuple[tuple[tuple[str, str], ...], str], ...] = (
    (
        (("Mi número favorito es el 42.", "Anotado: tu número favorito es el 42."),),
        "¿Cuál es mi número favorito?",
    ),
    (
        (
            (
                "Esta noche voy a cocinar lentejas.",
                "¡Qué buena idea! Las lentejas son muy reconfortantes.",
            ),
        ),
        "¿Qué te dije que iba a cocinar?",
    ),
    (
        (
            (
                "Tengo una reunión mañana a las nueve.",
                "Entendido, mañana a las nueve tienes una reunión.",
            ),
        ),
        "¿A qué hora es mi reunión?",
    ),
    (
        (
            (
                "Estoy aprendiendo a tocar la guitarra.",
                "¡Qué genial! La guitarra es un instrumento hermoso.",
            ),
        ),
        "¿Qué instrumento estoy aprendiendo?",
    ),
    (
        (
            (
                "Compré una planta nueva para la sala.",
                "Qué lindo, una planta alegra cualquier sala.",
            ),
        ),
        "¿Dónde puse la planta?",
    ),
    (
        (("Mañana voy a viajar a la playa.", "¡Qué bien! Disfruta mucho de la playa."),),
        "¿A dónde voy a viajar mañana?",
    ),
    (
        (
            (
                "El código de mi bicicleta es Zorro.",
                "Entendido, el código de tu bicicleta es Zorro.",
            ),
        ),
        "¿Cuál era el código de mi bicicleta?",
    ),
    (
        (
            (
                "Hoy me levanté muy temprano.",
                "Madrugar a veces cuesta, pero rinde mucho.",
            ),
        ),
        "¿Qué te conté sobre mi mañana?",
    ),
    (
        (
            ("Quiero aprender ajedrez.", "Es un juego excelente para entrenar la mente."),
            ("Empezaré con las aperturas.", "Buena idea, las aperturas son la base."),
        ),
        "¿Qué quiero aprender y por dónde voy a empezar?",
    ),
    (
        (("Mi tortuga se llama Cobalto.", "Qué nombre tan original para una tortuga."),),
        "¿Cómo se llama mi tortuga?",
    ),
    (
        (("Prefiero el té sin azúcar.", "Anotado, té sin azúcar."),),
        "¿Cómo prefiero el té?",
    ),
    (
        (("Mañana es mi día libre.", "¡Qué bien, aprovéchalo!"),),
        "¿Qué te dije sobre mañana?",
    ),
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
        self._state = StreamState(request_start=0.0, pending_emotion=FALLBACK_EMOTION)
        self._buffer = ""
        self._spoken: list[str] = []
        self.sentences_seen = 0

    def feed(self, delta: str) -> StreamOutcome | None:
        """Take one delta; return ``INVALID_PROTOCOL`` once production would stop reading.

        Returns:
            The decided outcome, or ``None`` while production would keep consuming.
        """
        self._buffer += delta
        try:
            self._buffer, sentences = _consume_body(self._buffer, self._state)
        except StreamProtocolError:
            return StreamOutcome.INVALID_PROTOCOL
        self._spoken.extend(sentences)
        self.sentences_seen += len(sentences)
        return None

    def finish(self) -> StreamOutcome:
        """Decide the outcome once the stream has ended without an earlier decision."""
        return _classify_end_of_stream(self._buffer, self._state)

    def reply_text(self) -> str:
        """Return what production would have spoken, to be judged and then dropped."""
        return " ".join([*self._spoken, self._buffer]).strip()


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


def history_turns() -> list[StreamTurn]:
    """Return synthetic dialogues whose question depends on the history (ADR 0020 §7)."""
    return [
        StreamTurn(
            f"history_{index}",
            "history",
            question,
            None,
            [
                ConversationTurn(role=role, content=content)
                for user, assistant in exchanges
                for role, content in (("user", user), ("assistant", assistant))
            ],
            None,
        )
        for index, (exchanges, question) in enumerate(_HISTORY_DIALOGUES, start=1)
    ]


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
    not_spanish: int = 0
    language_judged: int = 0

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


def _tally(
    observations: Sequence[tuple[StreamOutcome, bool | None]],
) -> StreamProtocolResult:
    outcomes = [outcome for outcome, _ in observations]
    languages = [spanish for _, spanish in observations if spanish is not None]
    return StreamProtocolResult(
        valid=outcomes.count(StreamOutcome.VALID),
        invalid_protocol=outcomes.count(StreamOutcome.INVALID_PROTOCOL),
        empty_stream=outcomes.count(StreamOutcome.EMPTY_STREAM),
        errors=outcomes.count(StreamOutcome.ERROR),
        not_spanish=languages.count(False),
        language_judged=len(languages),
    )


async def _stream_once(
    turn: StreamTurn, client: httpx.AsyncClient, generate: StreamGenerator
) -> tuple[StreamOutcome, bool | None]:
    """Classify one live stream while it arrives and stop when production would stop.

    A provider error that comes after production has already decided (an invalid body
    start) never happens live, so it must not turn that observation into an ``ERROR``.
    The second item is the language verdict of a reply that would be spoken
    (``None`` for anything else, or when the reply is too short to judge).
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
                return decided, None
    except Exception as exc:
        logger.warning("Provider call failed for %s (%s)", turn.label, type(exc).__name__)
        return StreamOutcome.ERROR, None
    finally:
        # Stop the model generating: an abandoned async generator would keep the HTTP
        # stream (and Ollama) running until it is garbage collected.
        aclose = getattr(stream, "aclose", None)
        if aclose is not None:
            await aclose()
    outcome = classifier.finish()
    if outcome is not StreamOutcome.VALID:
        return outcome, None
    return outcome, judge_language(classifier.reply_text())


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
    observations: list[tuple[StreamOutcome, bool | None]] = []
    by_source: dict[str, list[tuple[StreamOutcome, bool | None]]] = {}
    for turn in turns:
        for _ in range(runs):
            observation = await _stream_once(turn, client, generate)
            observations.append(observation)
            by_source.setdefault(turn.source, []).append(observation)
    overall = _tally(observations)
    return StreamProtocolResult(
        overall.valid,
        overall.invalid_protocol,
        overall.empty_stream,
        overall.errors,
        {source: _tally(items) for source, items in by_source.items()},
        overall.not_spanish,
        overall.language_judged,
    )


def _percent(rate: float | None) -> str:
    return "n/a" if rate is None else f"{rate * _PERCENT:.2f} %"


def render_stream_report(result: StreamProtocolResult, *, model: str, runs: int) -> str:
    """Render the measurement as Markdown: counts and rates only, never model output."""
    rows = [
        "| Set | Valid | Invalid protocol | Empty stream | Provider errors | Fallback rate "
        "| Not in Spanish |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label, part in (("all", result), *sorted(result.by_source.items())):
        rows.append(
            f"| {label} | {part.valid} | {part.invalid_protocol} | {part.empty_stream} | "
            f"{part.errors} | {_percent(part.fallback_rate)} | "
            f"{part.not_spanish} of {part.language_judged} |"
        )
    return (
        "# Streaming protocol measurement\n\n"
        f"- model: {model}\n- runs per turn: {runs}\n"
        f"- graded observations: {result.graded}\n"
        f"- fallback rate (invalid protocol + empty stream, over graded): "
        f"{_percent(result.fallback_rate)}\n"
        f"- replies not in Spanish (word-list heuristic, replies it could judge): "
        f"{result.not_spanish} of {result.language_judged}\n\n" + "\n".join(rows) + "\n"
    )


def stream_exit_code(result: StreamProtocolResult, *, max_fallback_rate: float | None) -> int:
    """Return 1 on a provider error or a fallback rate above the optional limit, else 0."""
    if result.errors:
        return 1
    rate = result.fallback_rate
    if max_fallback_rate is not None and rate is not None and rate > max_fallback_rate:
        return 1
    return 0
