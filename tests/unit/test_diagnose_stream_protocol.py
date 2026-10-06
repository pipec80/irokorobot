"""The ``just diagnose-stream`` command (Plan 0057, Task 7)."""

from collections import Counter
from collections.abc import AsyncGenerator, AsyncIterator, Callable
import contextlib
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import NamedTuple
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from scripts import diagnose_stream_protocol as cli
from scripts.diagnose_stream_protocol import CliOptions, parse_cli_args, run_cli
from scripts.eval_chat import golden_stream_turns, load_suite
from scripts.eval_stream_diagnosis import Observation, run_diagnosis
from scripts.eval_stream_protocol import StreamOutcome, public_turns
from scripts.stream_diagnosis_probes import (
    OllamaFacts,
    RunStatus,
    StructuredProbeResult,
    StructuredRun,
    summarize_arrivals,
)
from scripts.stream_diagnosis_report import ReportContext, render_diagnosis_report
from scripts.stream_diagnosis_variants import DiagnosisUnit, StreamVariant, build_units
from scripts.stream_failure_shapes import FailureShape


@contextlib.asynccontextmanager
async def _factory() -> AsyncGenerator[httpx.AsyncClient]:
    yield Mock(spec=httpx.AsyncClient)


def _observation(
    outcome: StreamOutcome, variant: StreamVariant = StreamVariant.FULL
) -> Observation:
    return Observation(
        variant=variant,
        source="public",
        label="public_1",
        run=1,
        position=0,
        outcome=outcome,
        shape=None if outcome is StreamOutcome.ERROR else FailureShape.VALID,
        whole_text_outcome=None if outcome is StreamOutcome.ERROR else StreamOutcome.VALID,
        fragmentation_consistent=None if outcome is StreamOutcome.ERROR else True,
        prompt_chars=10,
        reply_chars=5,
        delta_count=1,
        first_delta_ms=1,
        speech_start_ms=1,
        end_ms=2,
    )


def _probe_result(*extra: RunStatus, constrained: bool = True) -> StructuredProbeResult:
    paced = summarize_arrivals([0, 100, 200, 300, 400], 410)
    runs = [StructuredRun(RunStatus.COMPLETE, paced)] * 3
    extras = (StructuredRun(status, None) for status in extra)
    return StructuredProbeResult((*runs, *extras), constrained)


class _Patched(NamedTuple):
    run: AsyncMock
    probe: AsyncMock | None


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    reachable: bool = True,
    outcome: StreamOutcome = StreamOutcome.VALID,
    probe_extra: tuple[RunStatus, ...] = (),
    control_extra: tuple[RunStatus, ...] = (),
    patch_probe: bool = True,
) -> _Patched:
    facts = OllamaFacts(reachable=reachable, version="0.34.4", model="qwen2.5:3b", digest="abc")
    monkeypatch.setattr(cli, "fetch_ollama_facts", AsyncMock(return_value=facts))
    run = AsyncMock(return_value=[_observation(outcome)])
    monkeypatch.setattr(cli, "run_diagnosis", run)
    if not patch_probe:
        return _Patched(run, None)

    def probe_result(
        _client: object, *, runs: int, constrained: bool = True
    ) -> StructuredProbeResult:
        extra = probe_extra if constrained else control_extra
        return _probe_result(*extra, constrained=constrained)

    probe = AsyncMock(side_effect=probe_result)
    monkeypatch.setattr(cli, "probe_structured_stream", probe)
    return _Patched(run, probe)


@pytest.mark.unit
def test_the_defaults_match_the_plan() -> None:
    options = parse_cli_args([])

    assert (options.runs, options.seed, options.variants, options.structured_runs) == (
        5,
        57,
        None,
        5,
    )


@pytest.mark.unit
def test_variants_are_parsed_as_words_without_quotes() -> None:
    options = parse_cli_args(["--variants", "no_context", "question_only", "--runs", "3"])

    assert options.variants == [StreamVariant.NO_CONTEXT, StreamVariant.QUESTION_ONLY]
    assert options.runs == 3


@pytest.mark.unit
@pytest.mark.parametrize("argv", [["--runs", "0"], ["--runs", "11"], ["--structured-runs", "11"]])
def test_out_of_range_runs_are_rejected(argv: list[str]) -> None:
    with pytest.raises(ValueError, match=r"less than or equal|greater than or equal"):
        parse_cli_args(argv)


@pytest.mark.unit
def test_an_unknown_variant_is_rejected_by_argparse() -> None:
    with pytest.raises(SystemExit):
        parse_cli_args(["--variants", "nope"])


@pytest.mark.unit
async def test_a_complete_run_writes_the_report_and_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _patch(monkeypatch).run
    output = tmp_path / "diagnosis.md"

    code = await run_cli(CliOptions(output=output, runs=2, seed=9), client_factory=_factory)

    assert code == 0
    text = output.read_text(encoding="utf-8")
    assert "# Streaming protocol diagnosis (Plan 0057)" in text
    assert "qwen2.5:3b" in text
    assert "seed: 9" in text
    assert run.await_args is not None
    assert run.await_args.kwargs["runs"] == 2
    assert run.await_args.kwargs["seed"] == 9
    units = run.await_args.args[0]
    assert {u.variant for u in units} == set(StreamVariant)


@pytest.mark.unit
async def test_the_closing_log_line_reports_the_baseline_rate_not_the_experiment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _patch(monkeypatch)
    monkeypatch.setattr(
        cli,
        "run_diagnosis",
        AsyncMock(
            return_value=[
                _observation(StreamOutcome.VALID),
                _observation(StreamOutcome.INVALID_PROTOCOL, variant=StreamVariant.NO_CONTEXT),
            ]
        ),
    )

    with caplog.at_level("INFO", logger=cli.logger.name):
        await run_cli(CliOptions(output=tmp_path / "d.md"), client_factory=_factory)

    assert "baseline_fallback_rate=0.0" in caplog.text


@pytest.mark.unit
async def test_the_variant_filter_reaches_the_units(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _patch(monkeypatch).run
    options = CliOptions(output=tmp_path / "d.md", variants=[StreamVariant.NO_CONTEXT])

    await run_cli(options, client_factory=_factory)

    assert run.await_args is not None
    assert {u.variant for u in run.await_args.args[0]} == {StreamVariant.NO_CONTEXT}


@pytest.mark.unit
async def test_a_provider_error_exits_one_but_still_writes_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, outcome=StreamOutcome.ERROR)
    output = tmp_path / "d.md"

    assert await run_cli(CliOptions(output=output), client_factory=_factory) == 1
    assert output.exists()


@pytest.mark.unit
@pytest.mark.parametrize("status", [RunStatus.PROVIDER_ERROR, RunStatus.INCOMPLETE])
async def test_a_failed_probe_run_also_exits_one(
    status: RunStatus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, probe_extra=(status,))

    assert await run_cli(CliOptions(output=tmp_path / "d.md"), client_factory=_factory) == 1


@pytest.mark.unit
async def test_an_off_schema_probe_run_is_a_finding_not_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, probe_extra=(RunStatus.OFF_SCHEMA,))
    output = tmp_path / "d.md"

    assert await run_cli(CliOptions(output=output), client_factory=_factory) == 0
    assert "off_schema" in output.read_text(encoding="utf-8")


@pytest.mark.unit
async def test_the_plain_text_control_runs_after_the_schema_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = _patch(monkeypatch).probe
    output = tmp_path / "d.md"

    await run_cli(CliOptions(output=output, structured_runs=4), client_factory=_factory)

    assert probe is not None
    assert [call.kwargs for call in probe.await_args_list] == [
        {"runs": 4, "constrained": True},
        {"runs": 4, "constrained": False},
    ]
    assert "### Plain-text control" in output.read_text(encoding="utf-8")


@pytest.mark.unit
async def test_a_failed_control_run_also_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, control_extra=(RunStatus.PROVIDER_ERROR,))

    assert await run_cli(CliOptions(output=tmp_path / "d.md"), client_factory=_factory) == 1


@pytest.mark.unit
@pytest.mark.parametrize("emotion", ["[]", "{}", "null", "7", "true"])
async def test_a_real_off_schema_reply_never_costs_the_report(
    emotion: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The probe runs last: a bad reply must cost one status, not the measured streams."""
    _patch(monkeypatch, patch_probe=False)
    reply = '{"response": "Hola", "emotion": ' + emotion + "}"
    lines = "".join(
        json.dumps({"message": {"content": reply[i : i + 6]}}) + "\n"
        for i in range(0, len(reply), 6)
    )
    lines += json.dumps({"done": True}) + "\n"

    @contextlib.asynccontextmanager
    async def factory() -> AsyncGenerator[httpx.AsyncClient]:
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(200, content=lines.encode())
        )
        async with httpx.AsyncClient(transport=transport) as client:
            yield client

    output = tmp_path / "d.md"

    code = await run_cli(CliOptions(output=output, structured_runs=3), client_factory=factory)

    text = output.read_text(encoding="utf-8")
    assert code == 0
    assert "off_schema" in text
    assert "## 8. Stream arrival probe" in text


@pytest.mark.unit
async def test_skipping_the_probe_runs_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch)
    probe = AsyncMock()
    monkeypatch.setattr(cli, "probe_structured_stream", probe)
    output = tmp_path / "d.md"

    code = await run_cli(CliOptions(output=output, structured_runs=0), client_factory=_factory)

    assert code == 0
    probe.assert_not_awaited()
    assert "Not run." in output.read_text(encoding="utf-8")


@pytest.mark.unit
async def test_an_unreachable_ollama_exits_two_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _patch(monkeypatch, reachable=False).run
    output = tmp_path / "d.md"

    assert await run_cli(CliOptions(output=output), client_factory=_factory) == 2
    assert not output.exists()
    run.assert_not_awaited()


@pytest.mark.unit
def test_the_golden_turns_are_shared_with_the_stream_evaluator() -> None:
    suite = load_suite(Path("tests") / "evals" / "golden_chat_faithfulness.yaml")

    turns = golden_stream_turns(suite.cases)

    assert [t.label for t in turns] == [c.id for c in suite.cases]
    assert {t.source for t in turns} == {"context"}


@pytest.mark.unit
def test_the_script_runs_when_executed_directly(tmp_path: Path) -> None:
    """``python scripts/diagnose_stream_protocol.py`` has ``scripts/`` on sys.path, not the root."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "diagnose_stream_protocol.py"
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}

    completed = subprocess.run(  # noqa: S603 — fixed interpreter and our own script
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--variants" in completed.stdout


@pytest.mark.unit
def test_justfile_exposes_diagnose_stream_and_forwards_arguments() -> None:
    justfile = Path("justfile").read_text(encoding="utf-8")

    assert "diagnose-stream *ARGS:" in justfile
    assert "python scripts/diagnose_stream_protocol.py {{ARGS}}" in justfile


def _real_units() -> list[DiagnosisUnit]:
    suite = load_suite(Path("tests") / "evals" / "golden_chat_faithfulness.yaml")
    return build_units(golden_stream_turns(suite.cases), public_turns())


@pytest.mark.unit
def test_the_real_suite_expands_to_the_units_the_plan_promises() -> None:
    units = _real_units()

    counts = Counter(unit.variant for unit in units)

    assert len(units) == 100  # 500 streams at 5 runs
    assert counts == {
        StreamVariant.FULL: 24,
        StreamVariant.FULL_REPEAT: 24,
        StreamVariant.CONTRACT_FIRST: 24,
        StreamVariant.NO_CONTEXT: 12,
        StreamVariant.QUESTION_ONLY: 2,
        StreamVariant.NO_PERSON: 1,
        StreamVariant.NO_HISTORY: 1,
        StreamVariant.PUBLIC_WITH_CONTEXT: 12,
    }


@pytest.mark.unit
async def test_the_whole_pipeline_runs_on_the_real_suite_with_a_fake_model() -> None:
    replies = itertools.cycle(["EMOTION:joy\nHola. Bien.", "sin etiqueta", "EMOTION:joy\n{x}"])

    def generate_for(_variant: StreamVariant) -> Callable[..., AsyncIterator[str]]:
        async def generate(
            _client: httpx.AsyncClient, _text: str, **_kwargs: object
        ) -> AsyncIterator[str]:
            yield next(replies)

        return generate

    units = _real_units()
    observations = await run_diagnosis(
        units, client=Mock(spec=httpx.AsyncClient), runs=2, seed=1, generate_for=generate_for
    )
    context = ReportContext(model="m", ollama_version="v", model_digest="d", runs=2, seed=1)
    report = render_diagnosis_report(observations, context, _probe_result())

    assert len(observations) == len(units) * 2
    assert sorted(o.position for o in observations) == list(range(len(units) * 2))
    for section in ("## 1.", "## 2.", "## 3.", "## 4.", "## 5.", "## 6.", "## 7.", "## 8."):
        assert section in report
