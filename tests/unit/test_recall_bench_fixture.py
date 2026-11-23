"""The invented retrieval bench of recall (Plan 0088 Task A1, D-4): structure and loader.

No Ollama, no database: the tracked fixture is read and checked, and the loader refuses a broken
bench before a run can measure it.
"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import httpx
import pytest
from server.cognition.recall_cues import CueStrength, classify_recall_cue
from server.memory import recall_search
from server.memory.recall_sensitivity import classify_turn_text
from server.memory.retrieval import GateSignals
from server.settings import settings

from scripts import check_reserved_terms, recall_bench, recall_bench_gates
from server import db

pytestmark = pytest.mark.unit

_FIXTURE = Path(__file__).resolve().parents[1] / "evals" / "recall_bench_v1.yaml"
_HEADER = 'version: 1\ntoday: "2026-11-20"\nowner: Canario Prueba\n'
_UNIT = '  - {id: u1, kind: turn, day: "2026-11-01", body: "Fuimos al cerro."}\n'


def _question(qid: str, klass: str, half: str, expected: str = "[u1]") -> str:
    return (
        f"  - {{id: {qid}, class: {klass}, half: {half}, strength: strong, "
        f'raw: "¿Qué te conté del cerro?", expected: {expected}}}\n'
    )


def _complete_questions() -> list[str]:
    """Every class at its minimum, both halves present, all expecting the one unit."""
    lines: list[str] = []
    for klass, minimum in recall_bench.CLASS_MINIMUMS.items():
        for index in range(minimum):
            half = "tune" if index % 2 == 0 else "check"
            lines.append(_question(f"{klass}_{index}", klass, half))
    return lines


def _write(tmp_path: Path, questions: list[str]) -> Path:
    path = tmp_path / "bench.yaml"
    path.write_text(_HEADER + "units:\n" + _UNIT + "questions:\n" + "".join(questions), "utf-8")
    return path


def _with_capitalized_nouns(questions: list[str]) -> list[str]:
    """Mark the meaning questions the loader needs to see as capitalized common nouns."""
    marked = 0
    result: list[str] = []
    for line in questions:
        if "class: direct_meaning" in line and marked < recall_bench.MIN_CAPITALIZED_COMMON_NOUNS:
            result.append(line.replace("strong", "strong, capitalized_common_noun: true"))
            marked += 1
        else:
            result.append(line)
    return result


def test_the_bench_loads_and_every_expected_unit_exists() -> None:
    bench = recall_bench.load_bench(_FIXTURE)

    unit_ids = {unit.id for unit in bench.units}
    assert bench.questions
    assert all(question.expected <= unit_ids for question in bench.questions)


def test_each_class_has_its_minimum_in_both_halves() -> None:
    bench = recall_bench.load_bench(_FIXTURE)

    for klass, minimum in recall_bench.CLASS_MINIMUMS.items():
        of_class = [question for question in bench.questions if question.klass == klass]
        assert len(of_class) >= minimum, klass
        assert {question.half for question in of_class} == {"tune", "check"}, klass
    meaning = [question for question in bench.questions if question.klass == "direct_meaning"]
    capitalized = sum(question.capitalized_common_noun for question in meaning)
    assert capitalized >= recall_bench.MIN_CAPITALIZED_COMMON_NOUNS


def test_a_question_naming_an_absent_unit_is_refused(tmp_path: Path) -> None:
    questions = _with_capitalized_nouns(_complete_questions())
    questions.append(_question("ghost", "window", "tune", expected="[absent]"))

    with pytest.raises(recall_bench.BenchError, match="absent"):
        recall_bench.load_bench(_write(tmp_path, questions))


def test_a_complete_small_bench_loads(tmp_path: Path) -> None:
    bench = recall_bench.load_bench(
        _write(tmp_path, _with_capitalized_nouns(_complete_questions()))
    )

    assert bench.today == date(2026, 11, 20)
    assert [unit.id for unit in bench.units] == ["u1"]


def test_a_class_below_its_minimum_is_refused(tmp_path: Path) -> None:
    questions = [
        line
        for line in _with_capitalized_nouns(_complete_questions())
        if "id: window_0," not in line
    ]

    with pytest.raises(recall_bench.BenchError, match="window"):
        recall_bench.load_bench(_write(tmp_path, questions))


def test_a_class_missing_a_half_is_refused(tmp_path: Path) -> None:
    questions = [
        line.replace("half: check", "half: tune") if "class: window" in line else line
        for line in _with_capitalized_nouns(_complete_questions())
    ]

    with pytest.raises(recall_bench.BenchError, match="window"):
        recall_bench.load_bench(_write(tmp_path, questions))


def test_a_duplicated_id_is_refused(tmp_path: Path) -> None:
    questions = _with_capitalized_nouns(_complete_questions())
    questions.append(_question("window_0", "window", "tune"))

    with pytest.raises(recall_bench.BenchError, match="window_0"):
        recall_bench.load_bench(_write(tmp_path, questions))


def test_every_question_is_a_recall_cue_of_its_strength() -> None:
    bench = recall_bench.load_bench(_FIXTURE)

    for question in bench.questions:
        cue = classify_recall_cue(question.raw, today=bench.today)
        assert cue is not None, question.id
        assert cue.strength is question.strength, question.id


def test_every_turn_unit_is_readable_as_normal() -> None:
    """A unit the store would class above ``normal`` is never read: the bench would lie."""
    bench = recall_bench.load_bench(_FIXTURE)

    for unit in bench.units:
        assert classify_turn_text(unit.body) == "normal", unit.id


def test_the_bench_holds_no_reserved_term() -> None:
    matcher = check_reserved_terms.build_matcher(check_reserved_terms.load_reserved_terms())
    if matcher is not None:
        text = _FIXTURE.read_text(encoding="utf-8")
        assert check_reserved_terms.offending_lines(text, matcher) == []


# The candidate rules of D-2 (Plan 0088 Task A3 Step 1), on hand-made signals.


def _s(
    distance: float | None,
    *,
    words: bool = False,
    has: bool = False,
    covers: bool = False,
) -> GateSignals:
    return GateSignals(distance=distance, by_words=words, covers_specific=covers, has_specific=has)


def test_g1_lets_a_word_hit_through_only_under_the_second_gate() -> None:
    gate = recall_bench_gates.build("G1", vector=0.43, words=0.55)

    assert gate(_s(0.40))
    assert gate(_s(0.50, words=True))
    assert not gate(_s(0.50))
    assert not gate(_s(0.60, words=True))


def test_g1_without_a_distance_needs_covered_specific_words() -> None:
    gate = recall_bench_gates.build("G1", vector=0.43, words=0.55)

    assert gate(_s(None, words=True, has=True, covers=True))
    assert not gate(_s(None, words=True, has=True, covers=False))
    assert not gate(_s(None, words=True))
    assert not gate(_s(None))


def test_g2_refuses_a_unit_that_does_not_hold_the_named_words() -> None:
    gate = recall_bench_gates.build("G2", vector=0.43)

    assert not gate(_s(0.10, words=True, has=True, covers=False))
    assert gate(_s(0.90, words=True, has=True, covers=True))
    assert gate(_s(0.90, words=True))
    assert gate(_s(0.40))


def test_g3_is_g1_and_g2_together() -> None:
    gate = recall_bench_gates.build("G3", vector=0.43, words=0.55)

    assert not gate(_s(0.10, has=True, covers=False))
    assert gate(_s(0.10, has=True, covers=True))
    assert not gate(_s(0.60, words=True, has=True, covers=True))
    assert gate(_s(None, words=True, has=True, covers=True))
    assert not gate(_s(None, words=True))


def test_g0_is_the_rule_adr_0040_replaced() -> None:
    gate = recall_bench_gates.build("G0", vector=0.43)

    assert gate(_s(0.90, words=True))
    assert gate(_s(0.42))
    assert not gate(_s(0.43))


def test_a_rule_with_a_second_gate_needs_its_threshold() -> None:
    with pytest.raises(ValueError, match="G1"):
        recall_bench_gates.build("G1", vector=0.43)
    with pytest.raises(ValueError, match="G9"):
        recall_bench_gates.build("G9", vector=0.43)


# The metrics and the selection rule of D-3, fixed before the bench runs.


def _q(klass: str, expected: frozenset[str], half: str = "tune") -> recall_bench.BenchQuestion:
    return recall_bench.BenchQuestion(
        id=f"{klass}-{sorted(expected)}",
        klass=klass,
        half="tune" if half == "tune" else "check",
        raw="¿Qué te conté?",
        strength=CueStrength.STRONG,
        expected=expected,
    )


def test_the_metrics_of_one_question() -> None:
    found = recall_bench.score(_q("direct_words", frozenset({"a"})), ("b", "a"))

    assert found.recall == 1.0
    assert found.precision == 0.5
    assert found.reciprocal_rank == 0.5
    assert found.correct_zero is None
    none = recall_bench.score(_q("named_never_told", frozenset()), ())
    assert (none.recall, none.precision, none.correct_zero) == (None, None, True)
    wrong = recall_bench.score(_q("named_never_told", frozenset()), ("a",))
    assert (wrong.precision, wrong.correct_zero) == (0.0, False)


def test_the_midpoints_lie_between_consecutive_distances_in_the_range() -> None:
    points = recall_bench.midpoints([0.40, 0.45, 0.45, 0.55, 0.80], low=0.43, high=0.70)

    # The range's ends count as observed points: below the first distance and above the last.
    assert [(point.value, point.margin) for point in points] == [
        (pytest.approx(0.44), pytest.approx(0.02)),
        (pytest.approx(0.50), pytest.approx(0.10)),
        (pytest.approx(0.625), pytest.approx(0.15)),
    ]


def test_direct_by_meaning_is_measured_not_required() -> None:
    """Pipec, 2026-11-23 (D-3 amended): the meaning threshold is a problem apart from the gate."""
    assert recall_bench.HARD_CLASSES == ("direct_words", "lexical_only", "window")
    meaning = _q("direct_meaning", frozenset({"a"}))
    words = _q("direct_words", frozenset({"a"}))
    lexical = _q("lexical_only", frozenset({"a"}))
    window = _q("window", frozenset({"a"}))
    scores = {
        meaning: recall_bench.score(meaning, ()),
        words: recall_bench.score(words, ("a",)),
        lexical: recall_bench.score(lexical, ("a",)),
        window: recall_bench.score(window, ("a",)),
    }

    assert recall_bench.summarize(scores, "tune").hard_recall_min == 1.0


def _summary(*, hard: float, zero: float, common: float) -> recall_bench.HalfSummary:
    return recall_bench.HalfSummary(hard_recall_min=hard, correct_zero=zero, common_no_name=common)


def test_the_selection_keeps_the_hard_constraints_on_both_halves() -> None:
    g0 = recall_bench.Candidate(
        "G0",
        None,
        None,
        _summary(hard=1, zero=0.2, common=0.0),
        _summary(hard=1, zero=0.2, common=0.0),
    )
    g2 = recall_bench.Candidate(
        "G2",
        None,
        None,
        _summary(hard=1, zero=0.9, common=0.0),
        _summary(hard=0.9, zero=0.9, common=0.0),
    )
    g1 = recall_bench.Candidate(
        "G1",
        0.5,
        0.1,
        _summary(hard=1, zero=0.6, common=0.5),
        _summary(hard=1, zero=0.6, common=0.5),
    )

    assert recall_bench.choose([g0, g2, g1]) is g1


def test_the_winner_must_improve_on_g0_with_one_common_word() -> None:
    g0 = recall_bench.Candidate(
        "G0",
        None,
        None,
        _summary(hard=1, zero=0.2, common=0.0),
        _summary(hard=1, zero=0.2, common=0.0),
    )
    g2 = recall_bench.Candidate(
        "G2",
        None,
        None,
        _summary(hard=1, zero=0.7, common=0.0),
        _summary(hard=1, zero=0.7, common=0.0),
    )

    assert recall_bench.choose([g0, g2]) is None


def test_ties_go_to_fewer_parameters_then_the_wider_margin() -> None:
    same = _summary(hard=1, zero=0.6, common=0.5)
    g0 = recall_bench.Candidate(
        "G0",
        None,
        None,
        _summary(hard=1, zero=0.2, common=0.0),
        _summary(hard=1, zero=0.2, common=0.0),
    )
    g1_narrow = recall_bench.Candidate("G1", 0.5, 0.01, same, same)
    g1_wide = recall_bench.Candidate("G1", 0.6, 0.20, same, same)
    g3 = recall_bench.Candidate("G3", 0.6, 0.10, same, same)

    assert recall_bench.choose([g0, g3, g1_narrow, g1_wide]) is g1_wide
    g2 = recall_bench.Candidate("G2", None, None, same, same)
    assert recall_bench.choose([g0, g1_wide, g2]) is g2


def test_no_candidate_meeting_the_hard_constraints_adopts_nothing() -> None:
    weak = _summary(hard=0.5, zero=1, common=1)
    assert recall_bench.choose([recall_bench.Candidate("G0", None, None, weak, weak)]) is None


@pytest.mark.integration
def test_the_runner_measures_every_rule_through_the_production_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end on a temporary database with a fake embedder: no Ollama, no real data."""

    async def fake_embed(*_args: object, **_kwargs: object) -> list[float]:
        return [1.0] + [0.0] * 767

    monkeypatch.setattr(recall_bench, "ollama_embed", fake_embed)
    monkeypatch.setattr(recall_search, "ollama_embed", fake_embed)
    monkeypatch.setattr(settings, "brain_db_path", settings.brain_db_path)
    monkeypatch.setattr(settings, "occurred_time_enabled", settings.occurred_time_enabled)
    monkeypatch.setattr(db, "_conn", None)
    fixture = _write(tmp_path, _with_capitalized_nouns(_complete_questions()))
    out = tmp_path / "record.json"

    assert (
        recall_bench.main(
            ["--gates", "G0,G1,G2,G3,production", "--fixture", str(fixture), "--out", str(out)]
        )
        == 0
    )

    record = json.loads(out.read_text(encoding="utf-8"))
    assert set(record["rules"]) == {"G0", "G1", "G2", "G3", "production"}
    assert record["rules"]["G0"]["classes"]["window"]["tune"]["recall_at_3"] == 1.0
    # The production gate is G3 (ADR 0040): the same rule, the same numbers.
    assert record["rules"]["production"]["classes"] == record["rules"]["G3"]["classes"]


@pytest.mark.integration
def test_a_search_degraded_mid_run_stops_the_bench(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Final review: a question meant to use the vector side must not be scored by words alone."""

    async def loads(*_args: object, **_kwargs: object) -> list[float]:
        return [1.0] + [0.0] * 767

    async def fails(*_args: object, **_kwargs: object) -> list[float]:
        raise httpx.ConnectError("down mid-run")

    monkeypatch.setattr(recall_bench, "ollama_embed", loads)
    monkeypatch.setattr(recall_search, "ollama_embed", fails)
    monkeypatch.setattr(settings, "brain_db_path", settings.brain_db_path)
    monkeypatch.setattr(settings, "occurred_time_enabled", settings.occurred_time_enabled)
    monkeypatch.setattr(db, "_conn", None)
    fixture = _write(tmp_path, _with_capitalized_nouns(_complete_questions()))

    with pytest.raises(recall_bench.BenchError, match="vector side"):
        recall_bench.main(
            ["--gates", "G0", "--fixture", str(fixture), "--out", str(tmp_path / "r")]
        )


def test_the_selection_refuses_without_the_baseline() -> None:
    """D-3 asks the winner to improve on G0: without G0 there is nothing to improve on."""
    same = _summary(hard=1, zero=0.6, common=0.5)

    with pytest.raises(ValueError, match="G0"):
        recall_bench.choose([recall_bench.Candidate("G1", 0.5, 0.1, same, same)])


def test_a_malformed_entry_is_refused(tmp_path: Path) -> None:
    questions = [*_with_capitalized_nouns(_complete_questions()), "  - not a mapping\n"]

    with pytest.raises(recall_bench.BenchError, match="mapping"):
        recall_bench.load_bench(_write(tmp_path, questions))


def test_a_flag_must_be_a_boolean(tmp_path: Path) -> None:
    questions = _with_capitalized_nouns(_complete_questions())
    questions[0] = questions[0].replace("strength: strong", 'strength: strong, vector_off: "false"')

    with pytest.raises(recall_bench.BenchError, match="vector_off"):
        recall_bench.load_bench(_write(tmp_path, questions))
