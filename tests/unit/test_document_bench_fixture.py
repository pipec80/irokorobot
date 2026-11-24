"""The document bench's fixture is a valid bench (Plan 0088 Task B7, D-13). No model, no database."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import document_bench

pytestmark = pytest.mark.unit

_FIXTURE = Path(__file__).parents[2] / "tests" / "evals" / "document_bench_v1.yaml"


def test_the_bench_loads_with_every_class_at_its_minimum_in_both_halves() -> None:
    documents, questions = document_bench.load(_FIXTURE)

    assert {d["level"] for d in documents} == {"normal", "sensitive"}
    assert {q.klass for q in questions} == set(document_bench.MINIMUMS)


def test_injected_instructions_reach_the_sensitive_document_twice_or_more() -> None:
    documents, questions = document_bench.load(_FIXTURE)
    sensitive = {d["id"] for d in documents if d["level"] == "sensitive"}

    injected = [q for q in questions if q.klass == "injected_instruction"]
    assert sum(any(e.doc in sensitive for e in q.expect) for q in injected) >= 2


def test_a_question_that_is_no_document_cue_is_refused(tmp_path: Path) -> None:
    text = _FIXTURE.read_text(encoding="utf-8").replace(
        "¿Qué dice la receta del pan sobre la levadura?", "¿Qué te conté de la levadura?"
    )
    path = tmp_path / "bench.yaml"
    path.write_bytes(text.encode("utf-8"))

    with pytest.raises(document_bench.BenchError):
        document_bench.load(path)
