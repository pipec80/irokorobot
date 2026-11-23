"""The invented retrieval bench of recall (Plan 0088 Task A1, D-4): structure and loader.

No Ollama, no database: the tracked fixture is read and checked, and the loader refuses a broken
bench before a run can measure it.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from server.cognition.recall_cues import classify_recall_cue
from server.memory.recall_sensitivity import classify_turn_text

from scripts import check_reserved_terms, recall_bench

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
