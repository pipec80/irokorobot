from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, call

import pytest
from server.schemas import ConversationTurn, MemoryContext

from scripts import eval_chat
from scripts.eval_chat import (
    AssertionResult,
    CaseRunResult,
    EvaluationResult,
    GoldenCase,
    MetricSummary,
    aggregate_results,
    determine_exit_code,
    load_suite,
    normalize_text,
    parse_cli_args,
    percentile,
    render_report,
    run_cli,
    run_evaluation,
    score_response,
    select_cases,
    write_report,
)

VALID_SUITE_YAML = """
version: 1
cases:
  - id: corrected_age
    tags: [correction, active_fact]
    owner_name: Alex
    question: ¿Cuántos años tiene Sam?
    context:
      entities:
        - id: 1
          name: Sam
          type: person
          facts:
            - predicate: edad
              object_value: "11"
              confidence: 1.0
      memories: []
    history:
      - role: user
        content: Antes tenía 10.
    perception:
    expected:
      required_any:
        - ["11", "once"]
      forbidden:
        - "10"
"""


def _write_suite(tmp_path: Path, content: str = VALID_SUITE_YAML) -> Path:
    path = tmp_path / "golden.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def _case(
    *,
    required_any: list[list[str]],
    forbidden: list[str] | None = None,
    case_id: str = "matching_case",
    tags: list[str] | None = None,
) -> GoldenCase:
    return GoldenCase.model_validate(
        {
            "id": case_id,
            "tags": tags or ["present"],
            "owner_name": "Alex",
            "question": "Pregunta",
            "context": {"entities": [], "memories": []},
            "history": [],
            "expected": {
                "required_any": required_any,
                "forbidden": forbidden or [],
            },
        }
    )


def _assertion(
    *,
    passed: bool = True,
    required_satisfied: int = 1,
    required_total: int = 1,
    forbidden_found: list[str] | None = None,
) -> AssertionResult:
    return AssertionResult(
        passed=passed,
        required_groups_satisfied=required_satisfied,
        required_groups_total=required_total,
        missing_required=[] if required_satisfied == required_total else [["dato"]],
        forbidden_found=forbidden_found or [],
    )


def _run_result(
    *,
    case_id: str,
    tags: list[str],
    repetition: int,
    latency_ms: float,
    assertion: AssertionResult | None = None,
    error: str | None = None,
) -> CaseRunResult:
    return CaseRunResult(
        case_id=case_id,
        tags=tags,
        repetition=repetition,
        response="respuesta completa",
        emotion="neutral",
        latency_ms=latency_ms,
        assertion=assertion or _assertion(),
        error=error,
    )


@pytest.mark.unit
def test_normalize_text_folds_case_accents_and_whitespace() -> None:
    assert normalize_text("  ÁRBOL\u00a0   Cálido  ") == "arbol calido"


@pytest.mark.unit
def test_score_response_accepts_one_alternative_from_every_group() -> None:
    case = _case(required_any=[["11", "once"], ["Sam"]])

    result = score_response(case, "Sam tiene ONCE años.")

    assert result.passed
    assert result.missing_required == []
    assert result.forbidden_found == []


@pytest.mark.unit
def test_score_response_fails_when_required_group_is_missing() -> None:
    case = _case(required_any=[["11", "once"], ["Sam"]])

    result = score_response(case, "Tiene once años.")

    assert not result.passed
    assert result.missing_required == [["Sam"]]


@pytest.mark.unit
def test_score_response_fails_when_forbidden_expression_is_present() -> None:
    case = _case(required_any=[["11"]], forbidden=["10"])

    result = score_response(case, "Ahora tiene 11, no 10.")

    assert not result.passed
    assert result.forbidden_found == ["10"]


@pytest.mark.unit
def test_score_response_uses_word_boundaries_for_simple_tokens() -> None:
    case = _case(required_any=[["11"]])

    result = score_response(case, "El código es 111.")

    assert not result.passed
    assert result.missing_required == [["11"]]


@pytest.mark.unit
def test_load_suite_constructs_productive_schema_types(tmp_path: Path) -> None:
    suite = load_suite(_write_suite(tmp_path))

    assert isinstance(suite.cases[0].context, MemoryContext)
    assert isinstance(suite.cases[0].history[0], ConversationTurn)
    assert suite.cases[0].history[0].content == "Antes tenía 10."


@pytest.mark.unit
@pytest.mark.parametrize(
    "content,message",
    [
        (VALID_SUITE_YAML.replace("version: 1", "version: 2"), "version"),
        (
            VALID_SUITE_YAML.replace(
                "cases:",
                """cases:
  - id: corrected_age
    tags: [present]
    owner_name: Alex
    question: Pregunta duplicada
    context: {entities: [], memories: []}
    history: []
    expected:
      required_any: [[dato]]
      forbidden: []""",
            ),
            "unique",
        ),
        (
            VALID_SUITE_YAML.replace("question: ¿Cuántos años tiene Sam?", "question: '   '"),
            "question",
        ),
        (
            VALID_SUITE_YAML.replace(
                'required_any:\n        - ["11", "once"]\n      forbidden:\n        - "10"',
                "required_any: []\n      forbidden: []",
            ),
            "assertion",
        ),
    ],
    ids=["wrong-version", "duplicate-id", "blank-question", "empty-assertions"],
)
def test_load_suite_rejects_invalid_schema(
    tmp_path: Path,
    content: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        load_suite(_write_suite(tmp_path, content))


@pytest.mark.unit
def test_select_cases_rejects_unknown_only_before_execution(tmp_path: Path) -> None:
    suite = load_suite(_write_suite(tmp_path))

    with pytest.raises(ValueError, match="unknown_case"):
        select_cases(suite, "unknown_case")


@pytest.mark.unit
async def test_run_evaluation_forwards_exact_case_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _case(required_any=[["11"]])
    mock_generate = AsyncMock(return_value=("La respuesta es 11.", "joy"))
    monkeypatch.setattr(eval_chat.llm, "generate_response", mock_generate)
    monkeypatch.setattr(eval_chat.settings, "llm_provider", "anthropic")
    monkeypatch.setattr(eval_chat.time, "perf_counter", lambda: 1.0)

    evaluation = await run_evaluation([case], runs=1, provider="ollama")

    mock_generate.assert_awaited_once_with(
        case.question,
        context=case.context,
        history=case.history,
        owner_name=case.owner_name,
        perception=case.perception,
    )
    assert evaluation.provider == "ollama"
    assert evaluation.results[0].response == "La respuesta es 11."
    assert evaluation.results[0].emotion == "joy"
    assert evaluation.results[0].latency_ms == 0.0


@pytest.mark.unit
async def test_run_evaluation_runs_each_repetition_sequentially(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _case(required_any=[["dato"]], case_id="first")
    second = _case(required_any=[["dato"]], case_id="second")
    active_calls = 0
    max_active_calls = 0

    async def generate_sequentially(
        question: str,
        **_kwargs: object,
    ) -> tuple[str, str]:
        nonlocal active_calls, max_active_calls
        active_calls += 1
        max_active_calls = max(max_active_calls, active_calls)
        await eval_chat.asyncio.sleep(0)
        active_calls -= 1
        return f"dato para {question}", "neutral"

    mock_generate = AsyncMock(side_effect=generate_sequentially)
    monkeypatch.setattr(eval_chat.llm, "generate_response", mock_generate)

    evaluation = await run_evaluation([first, second], runs=2, provider="configured")

    assert max_active_calls == 1
    assert [result.case_id for result in evaluation.results] == [
        "first",
        "first",
        "second",
        "second",
    ]
    assert mock_generate.await_args_list == [
        call(
            first.question,
            context=first.context,
            history=first.history,
            owner_name=first.owner_name,
            perception=first.perception,
        ),
        call(
            first.question,
            context=first.context,
            history=first.history,
            owner_name=first.owner_name,
            perception=first.perception,
        ),
        call(
            second.question,
            context=second.context,
            history=second.history,
            owner_name=second.owner_name,
            perception=second.perception,
        ),
        call(
            second.question,
            context=second.context,
            history=second.history,
            owner_name=second.owner_name,
            perception=second.perception,
        ),
    ]


@pytest.mark.unit
async def test_run_evaluation_records_failure_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _case(required_any=[["dato"]])
    mock_generate = AsyncMock(
        side_effect=[
            RuntimeError("secret-token-must-not-leak"),
            ("dato correcto", "neutral"),
        ]
    )
    monkeypatch.setattr(eval_chat.llm, "generate_response", mock_generate)

    evaluation = await run_evaluation([case], runs=2, provider="configured")

    assert len(evaluation.results) == 2
    assert evaluation.results[0].error == "RuntimeError: provider call failed"
    assert "secret-token" not in evaluation.results[0].error
    assert not evaluation.results[0].assertion.passed
    assert evaluation.results[1].assertion.passed


@pytest.mark.unit
async def test_run_evaluation_restores_provider_after_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _case(required_any=[["dato"]])
    monkeypatch.setattr(
        eval_chat.llm,
        "generate_response",
        AsyncMock(side_effect=RuntimeError("offline")),
    )
    monkeypatch.setattr(eval_chat.settings, "llm_provider", "anthropic")

    evaluation = await run_evaluation([case], runs=1, provider="ollama")

    assert evaluation.results[0].error is not None
    assert eval_chat.settings.llm_provider == "anthropic"


@pytest.mark.unit
def test_percentile_is_defined_for_one_sample_and_interpolates() -> None:
    assert percentile([42.0], 50) == 42.0
    assert percentile([10.0, 20.0], 50) == 15.0
    assert percentile([10.0, 20.0], 95) == 19.5


@pytest.mark.unit
def test_aggregate_results_computes_global_and_per_tag_metrics() -> None:
    forbidden_failure = _assertion(passed=False, forbidden_found=["viejo"])
    results = [
        _run_result(case_id="stable", tags=["present"], repetition=1, latency_ms=10),
        _run_result(case_id="stable", tags=["present"], repetition=2, latency_ms=20),
        _run_result(case_id="mixed", tags=["correction"], repetition=1, latency_ms=30),
        _run_result(
            case_id="mixed",
            tags=["correction"],
            repetition=2,
            latency_ms=40,
            assertion=forbidden_failure,
        ),
    ]

    summary, by_tag = aggregate_results(results)

    assert summary.case_pass_rate == 0.75
    assert summary.required_group_recall == 1.0
    assert summary.forbidden_violation_rate == 0.25
    assert summary.stability == 0.5
    assert summary.latency_p50_ms == 25.0
    assert summary.latency_p95_ms == 38.5
    assert by_tag["present"].case_pass_rate == 1.0
    assert by_tag["correction"].case_pass_rate == 0.5


@pytest.mark.unit
def test_determine_exit_code_applies_threshold_and_provider_errors() -> None:
    passing = MetricSummary(
        total_runs=2,
        error_runs=0,
        case_pass_rate=0.5,
        required_group_recall=1.0,
        forbidden_violation_rate=0.0,
        stability=0.5,
        latency_p50_ms=10.0,
        latency_p95_ms=10.0,
    )
    with_error = passing.model_copy(update={"error_runs": 1})

    assert determine_exit_code(passing, min_pass_rate=None) == 0
    assert determine_exit_code(passing, min_pass_rate=0.5) == 0
    assert determine_exit_code(passing, min_pass_rate=0.51) == 1
    assert determine_exit_code(with_error, min_pass_rate=None) == 1


@pytest.mark.unit
def test_render_report_includes_results_metrics_and_tags() -> None:
    summary = MetricSummary(
        total_runs=1,
        error_runs=0,
        case_pass_rate=1.0,
        required_group_recall=1.0,
        forbidden_violation_rate=0.0,
        stability=1.0,
        latency_p50_ms=12.5,
        latency_p95_ms=12.5,
    )
    evaluation = EvaluationResult(
        generated_at=datetime(2026, 7, 29, 12, 0, tzinfo=UTC),
        provider="ollama",
        model="synthetic-model",
        runs=1,
        results=[
            _run_result(
                case_id="report_case",
                tags=["present"],
                repetition=1,
                latency_ms=12.5,
            )
        ],
        summary=summary,
        by_tag={"present": summary},
    )

    report = render_report(evaluation)

    assert "2026-07-29T12:00:00+00:00" in report
    assert "ollama" in report
    assert "synthetic-model" in report
    assert "respuesta completa" in report
    assert "Case pass rate" in report
    assert "present" in report


@pytest.mark.unit
def test_write_report_creates_parent_and_never_overwrites(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "report.md"

    write_report(output, "# report")

    assert output.read_text(encoding="utf-8") == "# report"
    with pytest.raises(FileExistsError):
        write_report(output, "# replacement")


@pytest.mark.unit
def test_parse_cli_args_supports_all_public_options(tmp_path: Path) -> None:
    output = tmp_path / "custom-report.md"

    options = parse_cli_args(
        [
            "--provider",
            "ollama",
            "--runs",
            "2",
            "--only",
            "corrected_age_active_fact",
            "--output",
            str(output),
            "--min-pass-rate",
            "0.8",
        ]
    )

    assert options.provider == "ollama"
    assert options.runs == 2
    assert options.only == "corrected_age_active_fact"
    assert options.output == output.resolve()
    assert options.min_pass_rate == 0.8


@pytest.mark.unit
async def test_run_cli_rejects_unknown_only_before_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suite_path = _write_suite(tmp_path)
    provider_runner = AsyncMock()
    monkeypatch.setattr(eval_chat, "_GOLDEN_PATH", suite_path)
    monkeypatch.setattr(eval_chat, "run_evaluation", provider_runner)

    with pytest.raises(ValueError, match="unknown_case"):
        await run_cli(eval_chat.CliOptions(only="unknown_case"))

    provider_runner.assert_not_awaited()


@pytest.mark.unit
def test_real_golden_suite_has_representative_synthetic_cases() -> None:
    suite = load_suite(Path("tests/evals/golden_chat_faithfulness.yaml"))
    case_ids = {case.id for case in suite.cases}
    tags = {tag for case in suite.cases for tag in case.tags}

    assert len(suite.cases) >= 12
    assert len(case_ids) == len(suite.cases)
    assert {
        "present",
        "absent",
        "correction",
        "distractor",
        "identity",
        "perception",
        "restart",
        "multi_fact",
    } <= tags
    assert {"present", "absent", "correction", "perception", "restart"} <= tags


@pytest.mark.unit
def test_real_golden_suite_contains_no_reserved_names() -> None:
    golden_path = Path("tests/evals/golden_chat_faithfulness.yaml")
    normalized_corpus = normalize_text(golden_path.read_text(encoding="utf-8"))
    reserved_names = {
        "pipec",
        "felipe",
        "maximo",
        "dominga",
        "iroko",
        "omnibot",
    }

    assert not {name for name in reserved_names if name in normalized_corpus}


@pytest.mark.unit
def test_justfile_exposes_eval_chat_and_forwards_arguments() -> None:
    justfile = Path("justfile").read_text(encoding="utf-8")

    assert "eval-chat *ARGS:" in justfile
    assert "python scripts/eval_chat.py {{ARGS}}" in justfile
