"""Streaming-protocol diagnosis: one observation per streamed reply (Plan 0057).

Runs the production streaming generator over the units built by
``stream_diagnosis_variants`` and consumes each reply the way ``server.streaming`` does.
Every reply is classified in memory (failure shape, whole-text verdict, fragmentation
consistency) and dropped: an ``Observation`` carries closed enums, flags, counts and
milliseconds, never a character of model output.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import TYPE_CHECKING

from scripts.eval_stream_protocol import StreamOutcome, _StreamClassifier, classify_deltas
from scripts.stream_diagnosis_variants import (
    DiagnosisUnit,
    StreamVariant,
    generator_for,
    plan_runs,
    prompt_chars,
)
from scripts.stream_failure_shapes import FailureShape, classify_failure_shape
from scripts.stream_fragmentation import is_fragmentation_consistent

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Sequence

    import httpx

    type StreamGenerator = Callable[..., AsyncIterator[str]]
    type Clock = Callable[[], float]

logger = logging.getLogger(__name__)

_MS_PER_SECOND = 1000
_PROGRESS_EVERY = 25


@dataclass(frozen=True)
class Observation:
    """One streamed reply, reduced to closed values. Never holds model text."""

    variant: StreamVariant
    source: str
    label: str
    run: int
    position: int
    outcome: StreamOutcome
    shape: FailureShape | None
    whole_text_outcome: StreamOutcome | None
    fragmentation_consistent: bool | None
    prompt_chars: int
    reply_chars: int
    delta_count: int
    first_delta_ms: int | None
    speech_start_ms: int
    end_ms: int

    @property
    def fell_back(self) -> bool:
        """Whether production would have spoken the fallback phrase."""
        return self.outcome in (StreamOutcome.INVALID_PROTOCOL, StreamOutcome.EMPTY_STREAM)

    @property
    def tolerated(self) -> bool:
        """Production spoke a reply whose shape the strict 0057 grammar named a failure."""
        return (
            self.outcome is StreamOutcome.VALID
            and self.shape is not None
            and self.shape is not FailureShape.VALID
        )

    @property
    def undue_accept(self) -> bool:
        """Production spoke a reply that the whole text would have rejected."""
        return (
            self.outcome is StreamOutcome.VALID
            and self.whole_text_outcome is not None
            and self.whole_text_outcome is not StreamOutcome.VALID
        )


def _ms(seconds: float) -> int:
    return round(seconds * _MS_PER_SECOND)


def _speech_start_ms(
    outcome: StreamOutcome, first_sentence_ms: int | None, decided_ms: int | None, end_ms: int
) -> int:
    """When production would hand its first sentence, or the fallback, to TTS.

    A valid reply starts at its first closed sentence (or the end of the stream when it
    never closes one); a rejected reply starts the fallback the moment production
    decides, which for a reply without the tag is only the end of the stream.
    """
    if outcome is StreamOutcome.VALID:
        return end_ms if first_sentence_ms is None else first_sentence_ms
    return end_ms if decided_ms is None else decided_ms


async def _close_stream(stream: object, label: str) -> None:
    """Stop the model generating: an abandoned async generator keeps Ollama running.

    A failing close is logged by type and ignored: it must not cost the hundreds of
    observations measured around it.
    """
    aclose = getattr(stream, "aclose", None)
    if aclose is None:
        return
    try:
        await aclose()
    except Exception as exc:
        logger.warning("Closing the stream failed for %s (%s)", label, type(exc).__name__)


async def observe_once(
    unit: DiagnosisUnit,
    *,
    run: int,
    position: int,
    client: httpx.AsyncClient,
    generate: StreamGenerator,
    clock: Clock = time.perf_counter,
) -> Observation:
    """Stream one reply the way production consumes it and reduce it to closed values.

    Production stops reading at an invalid body start, so this does too (and closes the
    stream); every other reply is read to its end. The reply text lives only inside this
    call.
    """
    turn = unit.turn
    started = clock()
    classifier = _StreamClassifier()
    pieces: list[str] = []
    first_delta_ms: int | None = None
    first_sentence_ms: int | None = None
    decided_ms: int | None = None
    decided: StreamOutcome | None = None
    stream = generate(
        client,
        turn.text,
        context=turn.context,
        history=turn.history,
        active_person=turn.active_person,
    )
    failed = False
    try:
        async for delta in stream:
            if not delta:
                continue
            now_ms = _ms(clock() - started)
            if first_delta_ms is None:
                first_delta_ms = now_ms
            pieces.append(delta)
            decided = classifier.feed(delta)
            if first_sentence_ms is None and classifier.sentences_seen:
                first_sentence_ms = now_ms
            if decided is not None:
                decided_ms = now_ms
                break
    except Exception as exc:
        # Any provider or stream failure is one ERROR observation, logged by type only
        # (never the message, which could carry model text); it must not end the run.
        logger.warning("Provider call failed for %s (%s)", turn.label, type(exc).__name__)
        failed = True
    finally:
        await _close_stream(stream, turn.label)
    end_ms = _ms(clock() - started)
    text = "".join(pieces)
    outcome = StreamOutcome.ERROR
    shape: FailureShape | None = None
    whole: StreamOutcome | None = None
    consistent: bool | None = None
    speech_start_ms = end_ms
    if not failed:
        outcome = decided if decided is not None else classifier.finish()
        shape = classify_failure_shape(text)
        whole = classify_deltas([text] if text else [])
        consistent = is_fragmentation_consistent(text)
        speech_start_ms = _speech_start_ms(outcome, first_sentence_ms, decided_ms, end_ms)
    return Observation(
        variant=unit.variant,
        source=turn.source,
        label=turn.label,
        run=run,
        position=position,
        outcome=outcome,
        shape=shape,
        whole_text_outcome=whole,
        fragmentation_consistent=consistent,
        prompt_chars=prompt_chars(unit),
        reply_chars=len(text),
        delta_count=len(pieces),
        first_delta_ms=first_delta_ms,
        speech_start_ms=speech_start_ms,
        end_ms=end_ms,
    )


async def run_diagnosis(
    units: Sequence[DiagnosisUnit],
    *,
    client: httpx.AsyncClient,
    runs: int,
    seed: int,
    generate_for: Callable[[StreamVariant], StreamGenerator] = generator_for,
) -> list[Observation]:
    """Stream every unit ``runs`` times, sequentially, in the seeded shuffled order.

    Args:
        units: The units to measure (see ``build_units``).
        client: Run-owned HTTP client, passed first to the generator (Plan 0039).
        runs: Repetitions per unit.
        seed: Seed of the shuffle, recorded in the report.
        generate_for: Maps a variant to its generator; production's unless a test
            injects one.

    Returns:
        One observation per ``(unit, run)``, in execution order. A provider error is an
        ``ERROR`` observation, never a protocol failure or a pass.
    """
    plan = plan_runs(units, runs, seed)
    observations: list[Observation] = []
    for position, (unit, run) in enumerate(plan):
        observations.append(
            await observe_once(
                unit,
                run=run,
                position=position,
                client=client,
                generate=generate_for(unit.variant),
            )
        )
        if (position + 1) % _PROGRESS_EVERY == 0:
            logger.info("Diagnosis progress: %d/%d", position + 1, len(plan))
    return observations
