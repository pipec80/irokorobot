"""Ollama facts and the structured-stream probe (Plan 0057, Task 5)."""

from collections.abc import Callable
import itertools
import json

import httpx
import pytest
from server.settings import settings

from scripts import stream_diagnosis_probes as probes
from scripts.stream_diagnosis_probes import (
    ArrivalPattern,
    ArrivalSummary,
    RunStatus,
    StructuredProbeResult,
    StructuredRun,
    conforms_to_schema,
    fetch_ollama_facts,
    parse_digest,
    parse_version,
    probe_structured_stream,
    summarize_arrivals,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "body, expected",
    [
        ({"version": "0.34.4"}, "0.34.4"),
        ({}, "unknown"),
        ([], "unknown"),
        ({"version": 3}, "unknown"),
    ],
)
def test_parse_version_is_tolerant(body: object, expected: str) -> None:
    assert parse_version(body) == expected


@pytest.mark.unit
def test_parse_digest_finds_the_model_by_name_or_model_and_truncates() -> None:
    body = {
        "models": [
            {"name": "other:1b", "digest": "ffff" * 16},
            {"name": "qwen2.5:3b", "model": "qwen2.5:3b", "digest": "abcdef012345" + "0" * 52},
        ]
    }

    assert parse_digest(body, "qwen2.5:3b") == "abcdef012345"
    assert parse_digest({"models": [{"model": "m", "digest": "1234567890123456"}]}, "m") == (
        "123456789012"
    )


@pytest.mark.unit
def test_parse_digest_resolves_the_implicit_latest_tag() -> None:
    """A configured ``qwen2.5`` is what Ollama lists as ``qwen2.5:latest``."""
    body = {
        "models": [
            {"name": "qwen2.5:3b", "model": "qwen2.5:3b", "digest": "3b" * 32},
            {
                "name": "qwen2.5:latest",
                "model": "qwen2.5:latest",
                "digest": "abcdef012345" + "0" * 52,
            },
        ]
    }

    assert parse_digest(body, "qwen2.5") == "abcdef012345"
    assert parse_digest(body, "qwen2.5:latest") == "abcdef012345"


@pytest.mark.unit
def test_parse_digest_keeps_the_exact_comparison_for_an_explicit_tag() -> None:
    only_latest = {"models": [{"name": "qwen2.5:latest", "digest": "a" * 64}]}
    only_3b = {"models": [{"name": "qwen2.5:3b", "digest": "b" * 64}]}

    assert parse_digest(only_latest, "qwen2.5:3b") == "unknown"
    assert parse_digest(only_3b, "qwen2.5") == "unknown"
    assert parse_digest(only_3b, "qwen2.5:3b") == "b" * 12


@pytest.mark.unit
def test_parse_digest_does_not_mistake_a_registry_port_for_a_tag() -> None:
    body = {"models": [{"name": "localhost:5000/team/model:latest", "digest": "c" * 64}]}

    assert parse_digest(body, "localhost:5000/team/model") == "c" * 12


@pytest.mark.unit
@pytest.mark.parametrize(
    "body", [None, {}, {"models": []}, {"models": ["x"]}, {"models": [{"name": "m"}]}]
)
def test_parse_digest_is_unknown_when_ollama_does_not_say(body: object) -> None:
    assert parse_digest(body, "m") == "unknown"


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.unit
async def test_facts_report_version_and_digest() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.34.4"})
        return httpx.Response(
            200, json={"models": [{"name": settings.ollama_model, "digest": "a" * 64}]}
        )

    async with _client(handler) as client:
        facts = await fetch_ollama_facts(client)

    assert (facts.reachable, facts.version, facts.model, facts.digest) == (
        True,
        "0.34.4",
        settings.ollama_model,
        "a" * 12,
    )


@pytest.mark.unit
async def test_facts_say_unreachable_when_ollama_is_down() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    async with _client(handler) as client:
        facts = await fetch_ollama_facts(client)

    assert (facts.reachable, facts.version, facts.digest) == (False, "unknown", "unknown")


@pytest.mark.unit
@pytest.mark.parametrize(
    "arrivals, expected",
    [
        ([5000, 5100, 5200, 5300, 5400], ArrivalPattern.INCREMENTAL),  # a long first wait
        ([100, 200, 300, 400, 1000], ArrivalPattern.INCREMENTAL),
        ([0, 30, 60, 61, 62], ArrivalPattern.INCREMENTAL),  # half of the gaps are paced
        ([1, 1, 1, 1, 2], ArrivalPattern.BURST),  # a burst at the client
        ([900, 900, 901, 901, 902], ArrivalPattern.BURST),
        ([0, 0, 0, 0, 0], ArrivalPattern.BURST),
        ([0, 25, 25, 25, 25], ArrivalPattern.BURST),  # one paced gap in four: a burst after a wait
        ([0, 10, 20, 30, 40], ArrivalPattern.BURST),  # fast generation looks like this too
        ([0, 30, 31, 61, 62], ArrivalPattern.INCREMENTAL),
        ([0, 30, 31, 32, 33, 34, 70], ArrivalPattern.INCONCLUSIVE),  # 2 paced gaps in 6
        ([100, 200, 300, 400], ArrivalPattern.INCONCLUSIVE),  # too few chunks to tell
        ([], ArrivalPattern.INCONCLUSIVE),
    ],
)
def test_the_pattern_reads_the_spacing_between_chunks_not_when_the_first_arrived(
    arrivals: list[int], expected: ArrivalPattern
) -> None:
    summary = summarize_arrivals(arrivals, arrivals[-1] + 10 if arrivals else 10)

    assert summary.pattern is expected
    assert summary.chunks == len(arrivals)


@pytest.mark.unit
def test_an_empty_arrival_list_has_no_first_or_last_chunk_and_no_gaps() -> None:
    assert summarize_arrivals([], 7) == ArrivalSummary(0, None, None, 0, 0, 7)


@pytest.mark.unit
def test_gaps_are_counted_between_consecutive_chunks() -> None:
    summary = summarize_arrivals([0, 10, 40, 100], 120)

    assert (summary.gaps, summary.paced_gaps) == (3, 2)


@pytest.mark.unit
@pytest.mark.parametrize(
    "text, expected",
    [
        ('{"response": "Hola", "emotion": "joy"}', True),
        ('{"response": "Hola", "emotion": "neutral", "extra": 1}', True),
        ('{"response": "Hola"}', False),
        ('{"response": "", "emotion": "joy"}', False),
        ('{"response": "  ", "emotion": "joy"}', False),
        ('{"response": 3, "emotion": "joy"}', False),
        ('{"response": "Hola", "emotion": "furious"}', False),
        ('{"response": "Hola", "emotion": 4}', False),
        ('{"response": "Hola", "emotion": []}', False),
        ('{"response": "Hola", "emotion": {}}', False),
        ('{"response": "Hola", "emotion": null}', False),
        ('{"response": "Hola", "emotion": true}', False),
        ("[1, 2]", False),
        ("not json", False),
        ("", False),
    ],
)
def test_the_assembled_reply_must_satisfy_the_schema(text: str, expected: bool) -> None:
    assert conforms_to_schema(text) is expected


_VALID = '{"response": "Hola, como estas", "emotion": "joy"}'


def _stream(*events: object, status: int = 200) -> Callable[[httpx.Request], httpx.Response]:
    body = "".join(json.dumps(event) + "\n" for event in events)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body.encode(), request=request)

    return handler


def _pieces(text: str, size: int = 8) -> list[dict[str, object]]:
    return [{"message": {"content": text[i : i + size]}} for i in range(0, len(text), size)]


def _ticker(step: float) -> Callable[[], float]:
    ticks = itertools.count(0.0, step)
    return lambda: next(ticks)


async def _probe(
    handler: Callable[[httpx.Request], httpx.Response], *, runs: int = 1, step: float = 0.05
) -> StructuredProbeResult:
    async with _client(handler) as client:
        return await probe_structured_stream(client, runs=runs, clock=_ticker(step))


@pytest.mark.unit
async def test_a_complete_schema_conforming_stream_is_complete_and_paced() -> None:
    result = await _probe(_stream(*_pieces(_VALID), {"done": True}))

    [run] = result.runs
    assert run.status is RunStatus.COMPLETE
    assert run.arrivals is not None
    assert run.arrivals.chunks == len(_pieces(_VALID))
    assert run.pattern is ArrivalPattern.INCREMENTAL
    assert result.errors == 0


@pytest.mark.unit
async def test_chunks_that_arrive_together_are_a_burst() -> None:
    result = await _probe(_stream(*_pieces(_VALID), {"done": True}), step=0.0001)

    assert result.runs[0].status is RunStatus.COMPLETE
    assert result.runs[0].pattern is ArrivalPattern.BURST


@pytest.mark.unit
async def test_the_probe_asks_for_a_schema_and_a_stream() -> None:
    seen: list[dict[str, object]] = []
    lines = _stream(*_pieces(_VALID), {"done": True})

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return lines(request)

    await _probe(handler)

    assert seen[0]["stream"] is True
    assert isinstance(seen[0]["format"], dict)
    assert seen[0]["model"] == settings.ollama_model


@pytest.mark.unit
async def test_an_error_event_after_a_200_is_a_provider_error_not_a_quiet_run() -> None:
    result = await _probe(_stream({"error": "model runner crashed"}))

    assert [r.status for r in result.runs] == [RunStatus.PROVIDER_ERROR]
    assert result.runs[0].arrivals is None
    assert result.errors == 1


@pytest.mark.unit
async def test_an_error_event_in_the_middle_of_the_reply_is_a_provider_error() -> None:
    result = await _probe(_stream(*_pieces(_VALID)[:2], {"error": "boom"}))

    assert [r.status for r in result.runs] == [RunStatus.PROVIDER_ERROR]


@pytest.mark.unit
async def test_a_stream_that_ends_without_done_is_incomplete() -> None:
    result = await _probe(_stream(*_pieces(_VALID)))

    assert [r.status for r in result.runs] == [RunStatus.INCOMPLETE]
    assert result.runs[0].arrivals is None
    assert result.errors == 1


@pytest.mark.unit
async def test_a_malformed_line_makes_the_run_incomplete() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b'{"message": {"content": "{"}}\nnot json\n')

    result = await _probe(handler)

    assert [r.status for r in result.runs] == [RunStatus.INCOMPLETE]


@pytest.mark.unit
async def test_a_non_text_content_is_not_a_chunk() -> None:
    events = [{"message": {"content": 5}}, {"message": {"content": None}}, {"done": True}]

    result = await _probe(_stream(*events))

    [run] = result.runs
    assert run.status is RunStatus.OFF_SCHEMA
    assert run.arrivals is not None
    assert run.arrivals.chunks == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    "reply",
    [
        '{"foo": 1}',
        '{"response": "Hola", "emotion": "furious"}',
        '{"response": "Hola", "emotion": []}',
        '{"response": "Hola", "emotion": {}}',
        '{"response": "',
        "plain text",
    ],
)
async def test_a_reply_outside_the_schema_is_off_schema_and_not_an_error(reply: str) -> None:
    result = await _probe(_stream(*_pieces(reply), {"done": True}))

    assert [r.status for r in result.runs] == [RunStatus.OFF_SCHEMA]
    assert result.errors == 0
    assert result.runs[0].pattern is None


@pytest.mark.unit
async def test_an_http_error_status_is_a_provider_error() -> None:
    result = await _probe(_stream(status=500))

    assert [r.status for r in result.runs] == [RunStatus.PROVIDER_ERROR]


@pytest.mark.unit
async def test_a_refused_connection_is_a_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    result = await _probe(handler, runs=2)

    assert [r.status for r in result.runs] == [RunStatus.PROVIDER_ERROR] * 2
    assert result.errors == 2


def _run(status: RunStatus, pattern: ArrivalPattern | None = None) -> StructuredRun:
    arrivals = None
    if pattern is ArrivalPattern.INCREMENTAL:
        arrivals = summarize_arrivals([0, 100, 200, 300, 400], 410)
    if pattern is ArrivalPattern.BURST:
        arrivals = summarize_arrivals([0, 1, 1, 2, 2], 12)
    return StructuredRun(status, arrivals)


@pytest.mark.unit
@pytest.mark.parametrize(
    "runs, expected",
    [
        ([_run(RunStatus.COMPLETE, ArrivalPattern.INCREMENTAL)] * 3, ArrivalPattern.INCREMENTAL),
        ([_run(RunStatus.COMPLETE, ArrivalPattern.BURST)] * 3, ArrivalPattern.BURST),
        ([_run(RunStatus.COMPLETE, ArrivalPattern.BURST)] * 2, ArrivalPattern.INCONCLUSIVE),
        (
            [
                _run(RunStatus.COMPLETE, ArrivalPattern.BURST),
                _run(RunStatus.COMPLETE, ArrivalPattern.BURST),
                _run(RunStatus.PROVIDER_ERROR),
                _run(RunStatus.INCOMPLETE),
                _run(RunStatus.OFF_SCHEMA),
            ],
            ArrivalPattern.INCONCLUSIVE,
        ),
        (
            [
                _run(RunStatus.COMPLETE, ArrivalPattern.INCREMENTAL),
                _run(RunStatus.COMPLETE, ArrivalPattern.BURST),
                _run(RunStatus.COMPLETE, ArrivalPattern.INCREMENTAL),
                _run(RunStatus.COMPLETE, ArrivalPattern.BURST),
            ],
            ArrivalPattern.INCONCLUSIVE,
        ),
        ([], ArrivalPattern.INCONCLUSIVE),
    ],
)
def test_the_verdict_needs_three_complete_runs_and_a_majority(
    runs: list[StructuredRun], expected: ArrivalPattern
) -> None:
    assert StructuredProbeResult(tuple(runs)).verdict is expected


@pytest.mark.unit
def test_the_probe_result_counts_each_status() -> None:
    result = StructuredProbeResult(
        (
            _run(RunStatus.COMPLETE, ArrivalPattern.BURST),
            _run(RunStatus.PROVIDER_ERROR),
            _run(RunStatus.INCOMPLETE),
            _run(RunStatus.OFF_SCHEMA),
        )
    )

    assert result.count(RunStatus.COMPLETE) == 1
    assert result.count(RunStatus.OFF_SCHEMA) == 1
    assert result.errors == 2


@pytest.mark.unit
async def test_an_unexpected_failure_inside_a_run_is_an_incomplete_run_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A probe bug must not lose the observations measured before it."""

    def explode(_text: str) -> bool:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(probes, "conforms_to_schema", explode)

    result = await _probe(_stream(*_pieces(_VALID), {"done": True}), runs=2)

    assert [r.status for r in result.runs] == [RunStatus.INCOMPLETE] * 2
    assert result.errors == 2


@pytest.mark.unit
async def test_the_plain_text_control_asks_for_no_schema_and_needs_no_json() -> None:
    seen: list[dict[str, object]] = []
    lines = _stream(*_pieces("Una frase. Otra frase. Y otra.", 4), {"done": True})

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return lines(request)

    async with _client(handler) as client:
        result = await probe_structured_stream(
            client, runs=1, clock=_ticker(0.05), constrained=False
        )

    assert "format" not in seen[0]
    assert seen[0]["stream"] is True
    assert result.constrained is False
    assert [r.status for r in result.runs] == [RunStatus.COMPLETE]
    assert result.runs[0].pattern is ArrivalPattern.INCREMENTAL


@pytest.mark.unit
async def test_a_plain_text_control_that_says_nothing_is_incomplete() -> None:
    async with _client(_stream({"done": True})) as client:
        result = await probe_structured_stream(
            client, runs=1, clock=_ticker(0.05), constrained=False
        )

    assert [r.status for r in result.runs] == [RunStatus.INCOMPLETE]


@pytest.mark.unit
async def test_the_constrained_probe_is_the_default() -> None:
    result = await _probe(_stream(*_pieces(_VALID), {"done": True}))

    assert result.constrained is True
