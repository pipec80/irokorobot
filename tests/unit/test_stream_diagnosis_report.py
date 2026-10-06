"""Aggregation and report of the streaming diagnosis (Plan 0057, Task 6)."""

import pytest

from scripts.eval_stream_diagnosis import Observation
from scripts.eval_stream_protocol import StreamOutcome
from scripts.stream_diagnosis_probes import (
    ArrivalPattern,
    RunStatus,
    StructuredProbeResult,
    StructuredRun,
    summarize_arrivals,
)
from scripts.stream_diagnosis_report import (
    ReportContext,
    probe_reading,
    render_diagnosis_report,
)
from scripts.stream_diagnosis_stats import (
    baseline_observations,
    compare_to_full,
    comparisons,
    dominant_shape,
    drift_flagged,
    drift_rates,
    per_case_counts,
    percentiles,
    shape_counts,
    summarize,
)
from scripts.stream_diagnosis_variants import StreamVariant
from scripts.stream_failure_shapes import FailureShape

_RUNS = 5


def _obs(
    *,
    variant: StreamVariant = StreamVariant.FULL,
    label: str = "case_a",
    source: str = "context",
    outcome: StreamOutcome = StreamOutcome.VALID,
    shape: FailureShape | None = FailureShape.VALID,
    whole: StreamOutcome | None = StreamOutcome.VALID,
    consistent: bool | None = True,
    position: int = 0,
) -> Observation:
    return Observation(
        variant=variant,
        source=source,
        label=label,
        run=1,
        position=position,
        outcome=outcome,
        shape=shape,
        whole_text_outcome=whole,
        fragmentation_consistent=consistent,
        prompt_chars=500,
        reply_chars=40,
        delta_count=8,
        first_delta_ms=50,
        speech_start_ms=100,
        end_ms=200,
    )


def _ok(
    label: str = "case_a", variant: StreamVariant = StreamVariant.FULL, position: int = 0
) -> Observation:
    return _obs(label=label, variant=variant, position=position)


def _bad(
    label: str = "case_a",
    variant: StreamVariant = StreamVariant.FULL,
    shape: FailureShape = FailureShape.NO_TAG,
    position: int = 0,
    source: str = "context",
) -> Observation:
    return _obs(
        label=label,
        variant=variant,
        source=source,
        outcome=StreamOutcome.INVALID_PROTOCOL,
        shape=shape,
        whole=StreamOutcome.INVALID_PROTOCOL,
        position=position,
    )


def _err(label: str = "case_a", variant: StreamVariant = StreamVariant.FULL) -> Observation:
    return _obs(
        label=label,
        variant=variant,
        outcome=StreamOutcome.ERROR,
        shape=None,
        whole=None,
        consistent=None,
    )


def _case(
    variant: StreamVariant, label: str, fallbacks: int, runs: int = _RUNS
) -> list[Observation]:
    """``runs`` complete observations of one turn, ``fallbacks`` of them fallbacks."""
    return [_bad(label, variant) for _ in range(fallbacks)] + [
        _ok(label, variant) for _ in range(runs - fallbacks)
    ]


@pytest.mark.unit
def test_summarize_counts_each_outcome_and_keeps_errors_out_of_the_rate() -> None:
    summary = summarize(
        [
            _ok(),
            _bad(),
            _obs(outcome=StreamOutcome.EMPTY_STREAM, shape=FailureShape.EMPTY),
            _err(),
            _obs(whole=StreamOutcome.INVALID_PROTOCOL, consistent=False),
        ]
    )

    assert (summary.valid, summary.invalid_protocol, summary.empty_stream, summary.errors) == (
        2,
        1,
        1,
        1,
    )
    assert summary.undue_accept == 1
    assert summary.inconsistent == 1
    assert summary.graded == 4
    assert summary.fallback_rate == pytest.approx(2 / 4)


@pytest.mark.unit
def test_the_rate_is_none_when_nothing_was_graded() -> None:
    assert summarize([]).fallback_rate is None


@pytest.mark.unit
def test_the_baseline_is_only_the_full_variant() -> None:
    observations = [
        _ok(),
        _ok(variant=StreamVariant.FULL_REPEAT),
        _bad(variant=StreamVariant.NO_CONTEXT),
    ]

    assert [o.variant for o in baseline_observations(observations)] == [StreamVariant.FULL]


@pytest.mark.unit
def test_shapes_count_only_fallbacks_and_name_the_dominant_one() -> None:
    observations = [
        _bad(shape=FailureShape.TAG_WRAPPED),
        _bad(shape=FailureShape.TAG_WRAPPED),
        _bad(shape=FailureShape.NO_TAG),
        _ok(),
    ]

    counts = shape_counts(observations)

    assert counts == {"tag_wrapped": 2, "no_tag": 1}
    assert dominant_shape(counts) == "tag_wrapped"
    assert dominant_shape({"a": 1, "b": 1, "c": 1}) is None
    assert dominant_shape({}) is None


@pytest.mark.unit
def test_per_case_counts_distinguish_errors_from_missing_and_from_fallbacks() -> None:
    observations = [
        *_case(StreamVariant.FULL, "all_bad", _RUNS),
        _bad("one_bad_four_errors"),
        *[_err("one_bad_four_errors")] * 4,
        *_case(StreamVariant.FULL, "partial", 2, runs=3),
        _bad("other_variant", StreamVariant.NO_CONTEXT),
    ]

    cases = per_case_counts(observations, StreamVariant.FULL, _RUNS)

    assert list(cases) == ["all_bad", "one_bad_four_errors", "partial"]
    assert cases["all_bad"].fell_every_run
    assert cases["all_bad"].complete
    assert cases["one_bad_four_errors"].fallbacks == 1
    assert cases["one_bad_four_errors"].errors == 4
    assert not cases["one_bad_four_errors"].fell_every_run
    assert not cases["partial"].complete
    assert not cases["partial"].fell_every_run


@pytest.mark.unit
def test_removing_a_factor_that_fixes_a_turn_is_an_exploratory_signal_with_its_denominators() -> (
    None
):
    observations = [
        *_case(StreamVariant.FULL, "a", 4),
        *_case(StreamVariant.FULL_REPEAT, "a", 4),
        *_case(StreamVariant.FULL, "b", 0),
        *_case(StreamVariant.NO_CONTEXT, "a", 0),
    ]

    result = compare_to_full(observations, StreamVariant.NO_CONTEXT, _RUNS)

    assert result.paired_cases == 1  # only turn "a" was run under the variant
    assert (result.baseline_fallbacks, result.baseline_graded) == (4, 5)
    assert (result.variant_fallbacks, result.variant_graded) == (0, 5)
    assert result.change_pp == pytest.approx(80.0)
    assert result.noise_pp == pytest.approx(0.0)
    assert result.reading == "exploratory signal"


@pytest.mark.unit
def test_a_difference_inside_the_noise_of_its_own_turns_is_no_signal() -> None:
    observations = [
        *_case(StreamVariant.FULL, "a", 2),
        *_case(StreamVariant.FULL_REPEAT, "a", 4),  # repeating `full` alone moved it 40 points
        *_case(StreamVariant.NO_CONTEXT, "a", 0),
    ]

    result = compare_to_full(observations, StreamVariant.NO_CONTEXT, _RUNS)

    assert result.change_pp == pytest.approx(40.0)
    assert result.noise_pp == pytest.approx(40.0)
    assert result.reading == "no signal"  # not above what repeating `full` alone moved


@pytest.mark.unit
def test_noise_is_measured_on_each_comparisons_own_turns_and_does_not_cancel() -> None:
    """Opposite swings on two turns must not average into a quiet control."""
    observations = [
        *_case(StreamVariant.FULL, "a", 5),
        *_case(StreamVariant.FULL_REPEAT, "a", 0),
        *_case(StreamVariant.FULL, "b", 0),
        *_case(StreamVariant.FULL_REPEAT, "b", 5),
        *_case(StreamVariant.NO_CONTEXT, "a", 0),
        *_case(StreamVariant.CONTRACT_FIRST, "a", 0),
        *_case(StreamVariant.CONTRACT_FIRST, "b", 0),
    ]

    only_a = compare_to_full(observations, StreamVariant.NO_CONTEXT, _RUNS)
    both = compare_to_full(observations, StreamVariant.CONTRACT_FIRST, _RUNS)

    assert only_a.noise_pp == pytest.approx(100.0)  # turn "a" alone swung 100 points
    assert only_a.change_pp == pytest.approx(100.0)
    assert only_a.reading == "no signal"
    assert both.noise_pp == pytest.approx(100.0)  # 100 on each turn, never averaged to 0
    assert both.change_pp == pytest.approx(50.0)
    assert both.reading == "no signal"


@pytest.mark.unit
def test_a_change_below_the_threshold_is_no_signal() -> None:
    one_in_ten = [*[_bad("a")] * 1, *[_ok("a")] * 9]
    observations = [
        *one_in_ten,
        *[_bad("a", StreamVariant.FULL_REPEAT)] * 1,
        *[_ok("a", StreamVariant.FULL_REPEAT)] * 9,
        *[_ok("a", StreamVariant.NO_CONTEXT)] * 10,
    ]

    result = compare_to_full(observations, StreamVariant.NO_CONTEXT, 10)

    assert result.change_pp == pytest.approx(10.0)
    assert result.reading == "no signal"


@pytest.mark.unit
def test_a_case_with_a_missing_or_failed_observation_is_excluded_not_compared() -> None:
    observations = [
        *_case(StreamVariant.FULL, "complete", 5),
        *_case(StreamVariant.FULL_REPEAT, "complete", 5),
        *_case(StreamVariant.NO_CONTEXT, "complete", 0),
        *_case(StreamVariant.FULL, "with_error", 5),
        *_case(StreamVariant.FULL_REPEAT, "with_error", 5),
        *_case(StreamVariant.NO_CONTEXT, "with_error", 0, runs=4),
        _err("with_error", StreamVariant.NO_CONTEXT),
        *_case(StreamVariant.FULL, "never_ran_full", 0, runs=3),
        *_case(StreamVariant.FULL_REPEAT, "never_ran_full", 0),
        *_case(StreamVariant.NO_CONTEXT, "never_ran_full", 0),
    ]

    result = compare_to_full(observations, StreamVariant.NO_CONTEXT, _RUNS)

    assert result.paired_cases == 1
    assert result.excluded_cases == 2
    assert (result.baseline_fallbacks, result.baseline_graded) == (5, 5)
    assert (result.variant_fallbacks, result.variant_graded) == (0, 5)


@pytest.mark.unit
def test_a_turn_without_a_complete_control_is_excluded_and_without_any_it_is_incomplete() -> None:
    observations = [
        *_case(StreamVariant.FULL, "controlled", 3),
        *_case(StreamVariant.FULL_REPEAT, "controlled", 3),
        *_case(StreamVariant.NO_CONTEXT, "controlled", 0),
        *_case(StreamVariant.FULL, "uncontrolled", 3),
        *_case(StreamVariant.NO_CONTEXT, "uncontrolled", 0),
    ]

    partial = compare_to_full(observations, StreamVariant.NO_CONTEXT, _RUNS)
    nothing = compare_to_full(
        [o for o in observations if o.variant is not StreamVariant.FULL_REPEAT],
        StreamVariant.NO_CONTEXT,
        _RUNS,
    )

    assert (partial.paired_cases, partial.excluded_cases) == (1, 1)
    assert nothing.paired_cases == 0
    assert nothing.reading == "incomplete"  # no control: never a signal
    assert nothing.change_pp is None
    assert nothing.noise_pp is None


@pytest.mark.unit
def test_no_complete_pair_is_incomplete_and_never_a_signal() -> None:
    observations = [
        *_case(StreamVariant.FULL, "a", 5),
        *_case(StreamVariant.FULL_REPEAT, "a", 5),
        _err("a", StreamVariant.NO_CONTEXT),
    ]

    result = compare_to_full(observations, StreamVariant.NO_CONTEXT, _RUNS)

    assert result.paired_cases == 0
    assert result.reading == "incomplete"
    assert result.change_pp is None


@pytest.mark.unit
def test_adding_a_context_to_a_public_question_is_read_in_the_other_direction() -> None:
    observations = [
        *_case(StreamVariant.FULL, "p1", 0),
        *_case(StreamVariant.FULL_REPEAT, "p1", 0),
        *_case(StreamVariant.PUBLIC_WITH_CONTEXT, "p1", 5),
    ]

    result = compare_to_full(observations, StreamVariant.PUBLIC_WITH_CONTEXT, _RUNS)

    assert result.change_pp == pytest.approx(100.0)
    assert result.reading == "exploratory signal"


@pytest.mark.unit
def test_comparisons_cover_every_intervention_that_ran_and_not_the_baseline() -> None:
    observations = [
        *_case(StreamVariant.FULL, "a", 3),
        *_case(StreamVariant.FULL_REPEAT, "a", 3),
        *_case(StreamVariant.NO_CONTEXT, "a", 0),
        *_case(StreamVariant.CONTRACT_FIRST, "a", 3),
    ]

    result = comparisons(observations, _RUNS)

    assert [c.variant for c in result] == [
        StreamVariant.FULL_REPEAT,
        StreamVariant.NO_CONTEXT,
        StreamVariant.CONTRACT_FIRST,
    ]
    assert result[0].reading == "control"  # the control never counts as a factor
    assert result[0].noise_pp is None
    assert result[1].reading == "exploratory signal"
    assert result[1].noise_pp == pytest.approx(0.0)
    assert result[2].reading == "no signal"


@pytest.mark.unit
def test_drift_splits_the_execution_order_into_quarters() -> None:
    observations = [_ok(position=i) if i < 6 else _bad(position=i) for i in range(8)]

    rates = drift_rates(observations)

    assert rates == [0.0, 0.0, 0.0, 1.0]
    assert drift_flagged(rates)
    assert not drift_flagged([0.1, 0.1, 0.2, 0.1])
    assert not drift_flagged([None, None])
    assert drift_rates([]) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "values, expected",
    [
        ([], None),
        ([10], (10, 10)),
        (list(range(1, 11)), (5, 10)),  # p50: 5th of 10; p95: ceil(9.5) = 10th
        (list(range(1, 12)), (6, 11)),  # p95: ceil(10.45) = 11th; rounding gave the 10th
        (list(range(1, 21)), (10, 19)),
        (list(range(1, 101)), (50, 95)),
        ([30, 10, 20], (20, 30)),
    ],
)
def test_percentiles_use_the_nearest_rank_for_both_p50_and_p95(
    values: list[int], expected: tuple[int, int] | None
) -> None:
    assert percentiles(values) == expected


def _context() -> ReportContext:
    return ReportContext(
        model="qwen2.5:3b",
        ollama_version="0.34.4",
        model_digest="abcdef012345",
        runs=_RUNS,
        seed=57,
    )


def _probe(
    pattern: ArrivalPattern = ArrivalPattern.INCREMENTAL,
    *,
    constrained: bool = True,
    complete: int = 3,
) -> StructuredProbeResult:
    arrivals = {
        ArrivalPattern.INCREMENTAL: summarize_arrivals([0, 100, 200, 300, 400], 410),
        ArrivalPattern.BURST: summarize_arrivals([0, 1, 1, 2, 2], 12),
        ArrivalPattern.INCONCLUSIVE: summarize_arrivals([0, 100], 110),
    }[pattern]
    runs = [StructuredRun(RunStatus.COMPLETE, arrivals)] * complete
    runs.append(StructuredRun(RunStatus.PROVIDER_ERROR, None))
    return StructuredProbeResult(tuple(runs), constrained)


@pytest.mark.unit
def test_the_report_states_facts_rules_and_every_section() -> None:
    observations = [
        *_case(StreamVariant.FULL, "a", 2),
        *_case(StreamVariant.FULL_REPEAT, "a", 2),
        *_case(StreamVariant.NO_CONTEXT, "a", 0),
        _bad("a", shape=FailureShape.TAG_WRAPPED, position=1),
    ]

    report = render_diagnosis_report(observations, _context(), _probe(), _probe(constrained=False))

    for expected in (
        "qwen2.5:3b",
        "abcdef012345",
        "0.34.4",
        "server defaults",
        "seed: 57",
        "the noise of repeating one condition",
        "## 1. Fallback by variant and source",
        "## 2. Interventions against `full`",
        "exploratory",
        "confirm with another seed",
        "Noise (pp)",
        "mean absolute difference",
        "## 3. Failure shapes",
        "## 4. Turns under `full`",
        "## 5. Timing (ms)",
        "## 6. Execution order",
        "## 7. Prompt size",
        "## 8. Stream arrival probe",
        "### Schema-constrained",
        "### Plain-text control",
        "Verdict: incremental",
        "provider_error",
        "compatible with incremental generation",
    ):
        assert expected in report


@pytest.mark.unit
def test_the_headline_rate_is_the_baseline_not_the_whole_experiment() -> None:
    observations = [
        *_case(StreamVariant.FULL, "a", 0),
        *_case(StreamVariant.PUBLIC_WITH_CONTEXT, "p", 5),
    ]

    report = render_diagnosis_report(observations, _context(), None)

    assert "baseline (`full`) fallback rate: context 0.00 %" in report
    assert "fallback rate over graded" not in report


@pytest.mark.unit
def test_a_shape_that_only_an_intervention_causes_is_not_the_dominant_shape() -> None:
    observations = [
        *_case(StreamVariant.FULL, "a", 1),
        *[_bad("p", StreamVariant.PUBLIC_WITH_CONTEXT, FailureShape.TAG_WRAPPED)] * 5,
    ]

    report = render_diagnosis_report(observations, _context(), None)
    full_section = report.split("## 3. Failure shapes")[1].split("## 4.")[0]

    assert "Dominant shape in `full` (context): `no_tag`" in full_section
    assert full_section.count("tag_wrapped") == 1  # only in the apart table of its variant


@pytest.mark.unit
def test_the_case_summary_never_claims_every_run_when_some_were_errors() -> None:
    observations = [_bad("a"), *[_err("a")] * 4]

    report = render_diagnosis_report(observations, _context(), None)

    assert "in every expected run: 0" in report
    assert "incomplete turns: 1" in report


@pytest.mark.unit
def test_the_report_without_a_probe_or_observations_still_renders() -> None:
    report = render_diagnosis_report([], _context(), None)

    assert "Not run." in report
    assert "n/a" in report


@pytest.mark.unit
def test_a_report_without_the_control_probe_says_so() -> None:
    report = render_diagnosis_report([], _context(), _probe(), None)

    assert "Plain-text control: not run." in report


@pytest.mark.unit
@pytest.mark.parametrize(
    "constrained, plain, fragment",
    [
        (ArrivalPattern.INCREMENTAL, None, "compatible with incremental generation"),
        (
            ArrivalPattern.INCREMENTAL,
            ArrivalPattern.BURST,
            "compatible with incremental generation",
        ),
        (ArrivalPattern.BURST, ArrivalPattern.INCREMENTAL, "differs from the plain-text control"),
        (ArrivalPattern.BURST, ArrivalPattern.BURST, "cannot tell generation from buffering"),
        (ArrivalPattern.BURST, ArrivalPattern.INCONCLUSIVE, "stays unproven"),
        (ArrivalPattern.BURST, None, "stays unproven"),
        (ArrivalPattern.INCONCLUSIVE, ArrivalPattern.INCREMENTAL, "No conclusion"),
        (ArrivalPattern.INCONCLUSIVE, None, "No conclusion"),
    ],
)
def test_a_burst_is_never_read_as_proof_that_ollama_withholds_the_reply(
    constrained: ArrivalPattern, plain: ArrivalPattern | None, fragment: str
) -> None:
    control = None if plain is None else _probe(plain, constrained=False)

    reading = probe_reading(_probe(constrained), control)

    assert fragment in reading
    assert "header holds" not in reading
    if constrained is ArrivalPattern.INCONCLUSIVE:
        assert "not evidence that the" in reading


@pytest.mark.unit
def test_the_report_states_what_a_client_side_probe_can_and_cannot_see() -> None:
    report = render_diagnosis_report([], _context(), _probe(ArrivalPattern.BURST), None)

    assert "as this client received them" in report
    assert "a burst never proves" in report
    assert "stays unproven" in report
    assert "header holds" not in report


@pytest.mark.unit
def test_a_spread_out_arrival_is_compatible_with_incremental_generation_not_proof_of_it() -> None:
    """The client sees arrivals, not when Ollama finished generating."""
    reading = probe_reading(_probe(ArrivalPattern.INCREMENTAL), None)

    assert "cannot see when generation ended" in reading
    assert "evidence against" in reading
    assert "is wrong" not in reading
    assert "did not withhold" not in reading
