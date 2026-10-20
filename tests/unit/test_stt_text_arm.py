"""The text arm: did the speech-to-text mishear, or did the rest misread? (Plan 0069 Task 8)"""

from dataclasses import replace
from pathlib import Path

import pytest

from scripts import stt_bench, stt_text_arm
from scripts.stt_corpus_models import load_script
from tests.unit.stt_bench_fixtures import FREE_SENTINEL, FakeTranscriber, build_corpus

_ITEMS = {item.id: item for item in load_script()}


@pytest.mark.unit
def test_a_misheard_answer_is_the_stt() -> None:
    assert stt_text_arm.attribute(_ITEMS["B05"], "Sí, autorizo.", "sí autoriso") == "stt"


@pytest.mark.unit
def test_a_taste_written_as_a_question_is_the_stt_under_todays_gate() -> None:
    item = _ITEMS["A03"]

    outcome = stt_text_arm.attribute(
        item, item.text, "¿Me gustan las películas de ciencia ficción?"
    )

    assert outcome == "stt"


@pytest.mark.unit
def test_a_reference_that_already_fails_is_the_rest() -> None:
    item = replace(_ITEMS["A02"], expect={"taste": "yes"})

    assert stt_text_arm.attribute(item, item.text, item.text) == "rest"
    assert stt_text_arm.attribute(item, item.text, "me gusta el lado de chocolate") == "both"


@pytest.mark.unit
def test_a_correct_hypothesis_is_ok() -> None:
    assert stt_text_arm.attribute(_ITEMS["B05"], "Sí, autorizo.", "Sí, autorizo.") == "ok"


@pytest.mark.unit
def test_the_count_table_has_layers_and_outcomes_and_no_free_text(tmp_path: Path) -> None:
    root = tmp_path / "stt"
    heard = build_corpus(root)
    run = stt_bench.run_bench(
        ["P0"],
        root=root,
        half="all",
        repeat=1,
        segmentation=None,
        conditions=[],
        load_model=lambda _config: object(),
        transcribe=FakeTranscriber(heard),
        run_id="arm",
    )[0].stem

    table = stt_text_arm.render(root, run)

    assert "| B | 1 | 0 | 0 | 0 |" in table  # «Sí, autorizo.» heard exactly
    assert "| D |" in table
    assert FREE_SENTINEL not in table
