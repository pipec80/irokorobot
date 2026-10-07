"""Facts about the local Ollama and one arrival-time probe (Plan 0057).

The diagnosis must say which Ollama and which model it measured, and whether Ollama
streams a reply constrained by a JSON schema chunk by chunk or withholds it until the
end. ``llm_streaming`` states the second as a fact; nobody has measured it. Only closed
statuses, counts and milliseconds are kept, never model text.

Over the ~200-line guideline on purpose: the facts, the arrival rule and the probe share
one vocabulary (statuses and patterns) that the report imports as a unit.
"""

from __future__ import annotations

from dataclasses import dataclass
import enum
from itertools import pairwise
import json
import logging
import time
from typing import TYPE_CHECKING

import httpx
from server.llm import _OLLAMA_RESPONSE_SCHEMA, VALID_EMOTIONS
from server.settings import settings

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

logger = logging.getLogger(__name__)

_UNKNOWN = "unknown"
_DIGEST_CHARS = 12
_DEFAULT_TAG = "latest"
_MS_PER_SECOND = 1000
# Rules fixed before measuring (Plan 0057, R-6). Chunks of a burst reach the client
# within a few milliseconds; a model generating on this machine spaces its chunks by
# tens. A burst can be withheld output, fast generation or buffering: it proves nothing.
_PACED_GAP_MS = 20
_MIN_CHUNKS = 5
_INCREMENTAL_MIN_PACED_SHARE = 0.5
_BURST_MAX_PACED_SHARE = 0.25
_MIN_COMPLETE_RUNS = 3
_PROBE_SYSTEM = "Eres un robot doméstico llamado Iroko. Responde siempre en español."
_PROBE_QUESTION = "Cuéntame algo interesante en tres frases."


@dataclass(frozen=True)
class OllamaFacts:
    """What the diagnosis ran against; ``unknown`` when Ollama did not say."""

    reachable: bool
    version: str
    model: str
    digest: str


def parse_version(body: object) -> str:
    """Return ``version`` from an ``/api/version`` body, or ``unknown``."""
    if isinstance(body, dict) and isinstance(body.get("version"), str):
        return body["version"]
    return _UNKNOWN


def _tag_candidates(model: str) -> tuple[str, ...]:
    """Names Ollama may list for ``model``: itself, plus ``:latest`` when no tag is given.

    A name without a tag means ``:latest``, and ``/api/tags`` lists it that way. A colon
    before the last ``/`` is a registry port, not a tag. An explicit tag such as ``:3b``
    is compared exactly.
    """
    if ":" in model.rsplit("/", 1)[-1]:
        return (model,)
    return (model, f"{model}:{_DEFAULT_TAG}")


def parse_digest(body: object, model: str) -> str:
    """Return the first characters of ``model``'s digest from an ``/api/tags`` body.

    An untagged ``model`` (``qwen2.5``) matches its implicit ``:latest`` entry; an
    explicit tag (``qwen2.5:3b``) matches only that exact name.
    """
    candidates = _tag_candidates(model)
    models = body.get("models") if isinstance(body, dict) else None
    for entry in models if isinstance(models, list) else []:
        if not isinstance(entry, dict) or not (
            entry.get("name") in candidates or entry.get("model") in candidates
        ):
            continue
        digest = entry.get("digest")
        if isinstance(digest, str) and digest:
            return digest[:_DIGEST_CHARS]
    return _UNKNOWN


async def _get_json(client: httpx.AsyncClient, path: str) -> object | None:
    """GET one Ollama path as JSON; ``None`` on any transport, status or JSON failure."""
    try:
        response = await client.get(f"{settings.ollama_url.rstrip('/')}{path}")
        response.raise_for_status()
        body: object = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Ollama %s unavailable (%s)", path, type(exc).__name__)
        return None
    return body


async def fetch_ollama_facts(client: httpx.AsyncClient) -> OllamaFacts:
    """Read the Ollama version and the configured model's digest.

    Args:
        client: Run-owned HTTP client.

    Returns:
        The facts; ``reachable`` is False when ``/api/version`` did not answer.
    """
    version_body = await _get_json(client, "/api/version")
    tags_body = await _get_json(client, "/api/tags")
    return OllamaFacts(
        reachable=version_body is not None,
        version=parse_version(version_body),
        model=settings.ollama_model,
        digest=parse_digest(tags_body, settings.ollama_model),
    )


class ArrivalPattern(enum.StrEnum):
    """How the chunks of one reply were spread in time."""

    INCREMENTAL = "incremental"
    BURST = "burst"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class ArrivalSummary:
    """When the content chunks of one streamed reply arrived, as gaps between chunks."""

    chunks: int
    first_chunk_ms: int | None
    last_chunk_ms: int | None
    gaps: int
    paced_gaps: int
    total_ms: int

    @property
    def pattern(self) -> ArrivalPattern:
        """Read the spacing between chunks, never how long the first one took to come.

        Rule fixed before measuring: fewer than five chunks tell nothing; at least half
        of the gaps paced (20 ms or more) is an arrival spread over time, compatible with
        incremental generation; a quarter or fewer is a burst at the client, which a
        withheld reply, fast generation and buffering all produce; anything between is
        inconclusive. Arrivals at the client never show when generation ended.
        """
        if self.chunks < _MIN_CHUNKS or not self.gaps:
            return ArrivalPattern.INCONCLUSIVE
        share = self.paced_gaps / self.gaps
        if share >= _INCREMENTAL_MIN_PACED_SHARE:
            return ArrivalPattern.INCREMENTAL
        if share <= _BURST_MAX_PACED_SHARE:
            return ArrivalPattern.BURST
        return ArrivalPattern.INCONCLUSIVE


def summarize_arrivals(arrivals_ms: Sequence[int], total_ms: int) -> ArrivalSummary:
    """Reduce chunk arrival times (ms since the request) to an ``ArrivalSummary``."""
    gaps = [later - earlier for earlier, later in pairwise(arrivals_ms)]
    return ArrivalSummary(
        chunks=len(arrivals_ms),
        first_chunk_ms=arrivals_ms[0] if arrivals_ms else None,
        last_chunk_ms=arrivals_ms[-1] if arrivals_ms else None,
        gaps=len(gaps),
        paced_gaps=sum(1 for gap in gaps if gap >= _PACED_GAP_MS),
        total_ms=total_ms,
    )


def conforms_to_schema(text: str) -> bool:
    """Whether the assembled reply satisfies the classic response schema.

    The text is judged in memory and dropped; only the boolean leaves this function.
    """
    try:
        data = json.loads(text)
    except ValueError:
        return False
    if not isinstance(data, dict):
        return False
    response = data.get("response")
    emotion = data.get("emotion")
    return (
        isinstance(response, str)
        and bool(response.strip())
        and isinstance(emotion, str)  # a list or a dict is unhashable: look it up only as text
        and emotion in VALID_EMOTIONS
    )


class RunStatus(enum.StrEnum):
    """How one schema-constrained stream ended. Only ``COMPLETE`` runs reach the verdict."""

    COMPLETE = "complete"
    PROVIDER_ERROR = "provider_error"
    INCOMPLETE = "incomplete"
    OFF_SCHEMA = "off_schema"


@dataclass(frozen=True)
class StructuredRun:
    """One run: a closed status and, when the stream finished, its arrival summary."""

    status: RunStatus
    arrivals: ArrivalSummary | None

    @property
    def pattern(self) -> ArrivalPattern | None:
        """The arrival pattern of a ``COMPLETE`` run; ``None`` for any other status."""
        if self.status is RunStatus.COMPLETE and self.arrivals is not None:
            return self.arrivals.pattern
        return None


@dataclass(frozen=True)
class StructuredProbeResult:
    """The runs of one probe: schema-constrained, or the plain-text control."""

    runs: tuple[StructuredRun, ...]
    constrained: bool = True

    def count(self, status: RunStatus) -> int:
        """How many runs ended with ``status``."""
        return sum(1 for run in self.runs if run.status is status)

    @property
    def errors(self) -> int:
        """Provider errors plus incomplete streams: runs that say nothing about Ollama."""
        return self.count(RunStatus.PROVIDER_ERROR) + self.count(RunStatus.INCOMPLETE)

    @property
    def verdict(self) -> ArrivalPattern:
        """The reading of R-6: needs three complete runs and a majority.

        Errors, incomplete streams and off-schema replies never vote; an unclear mix is
        ``INCONCLUSIVE``. ``BURST`` is a burst *at the client*: it cannot tell a withheld
        reply from fast generation or from buffering, so it never proves the header.
        """
        patterns = [run.pattern for run in self.runs if run.status is RunStatus.COMPLETE]
        if len(patterns) < _MIN_COMPLETE_RUNS:
            return ArrivalPattern.INCONCLUSIVE
        for candidate in (ArrivalPattern.INCREMENTAL, ArrivalPattern.BURST):
            if patterns.count(candidate) * 2 > len(patterns):
                return candidate
        return ArrivalPattern.INCONCLUSIVE


def _content(event: dict[str, object]) -> str:
    """Return the text of one stream event, or ``""`` when it carries none."""
    message = event.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]
    return ""


async def _stream_once(
    client: httpx.AsyncClient, clock: Callable[[], float], *, constrained: bool
) -> StructuredRun:
    """Stream one reply, constrained by the schema or as plain text, and classify its end."""
    payload: dict[str, object] = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": _PROBE_SYSTEM},
            {"role": "user", "content": _PROBE_QUESTION},
        ],
        "stream": True,
    }
    if constrained:
        payload["format"] = _OLLAMA_RESPONSE_SCHEMA
    url = f"{settings.ollama_url.rstrip('/')}/api/chat"
    started = clock()
    arrivals: list[int] = []
    pieces: list[str] = []
    saw_done = False
    received = False
    try:
        async with client.stream(
            "POST", url, json=payload, timeout=settings.ollama_timeout_s
        ) as response:
            response.raise_for_status()
            received = True
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError("stream line is not an object")
                if "error" in event:
                    return StructuredRun(RunStatus.PROVIDER_ERROR, None)
                if piece := _content(event):
                    arrivals.append(round((clock() - started) * _MS_PER_SECOND))
                    pieces.append(piece)
                saw_done = saw_done or event.get("done") is True
    except httpx.HTTPError as exc:
        # Before the headers it is the provider; after them the stream was cut.
        logger.warning("Stream probe failed (%s)", type(exc).__name__)
        failed = RunStatus.INCOMPLETE if received else RunStatus.PROVIDER_ERROR
        return StructuredRun(failed, None)
    except ValueError as exc:
        logger.warning("Stream probe failed (%s)", type(exc).__name__)
        return StructuredRun(RunStatus.INCOMPLETE, None)
    if not saw_done:
        return StructuredRun(RunStatus.INCOMPLETE, None)
    total_ms = round((clock() - started) * _MS_PER_SECOND)
    summary = summarize_arrivals(arrivals, total_ms)
    text = "".join(pieces)
    if constrained:
        return StructuredRun(
            RunStatus.COMPLETE if conforms_to_schema(text) else RunStatus.OFF_SCHEMA, summary
        )
    return StructuredRun(RunStatus.COMPLETE if text.strip() else RunStatus.INCOMPLETE, summary)


async def _structured_run(
    client: httpx.AsyncClient, clock: Callable[[], float], *, constrained: bool
) -> StructuredRun:
    """Run one probe stream; an unexpected failure is an incomplete run, never a crash.

    The probe runs after the diagnosis has measured hundreds of streams: a bug here must
    cost one run, not the report of everything measured before it. It is logged by type
    and counted as an error, so it is never silent.
    """
    try:
        return await _stream_once(client, clock, constrained=constrained)
    except Exception as exc:
        logger.warning("Stream probe crashed (%s)", type(exc).__name__)
        return StructuredRun(RunStatus.INCOMPLETE, None)


async def probe_structured_stream(
    client: httpx.AsyncClient,
    *,
    runs: int,
    clock: Callable[[], float] = time.perf_counter,
    constrained: bool = True,
) -> StructuredProbeResult:
    """Measure how the chunks of a streamed reply arrive at this client.

    Args:
        client: Run-owned HTTP client.
        runs: How many times to stream the same synthetic question.
        clock: Monotonic clock in seconds; injectable for tests.
        constrained: Ask for the response schema (``format``) when True; stream plain
            text when False, the control that makes a burst readable.

    Returns:
        One closed ``StructuredRun`` per run; see ``RunStatus`` for how a run can end.
    """
    return StructuredProbeResult(
        tuple([await _structured_run(client, clock, constrained=constrained) for _ in range(runs)]),
        constrained,
    )
