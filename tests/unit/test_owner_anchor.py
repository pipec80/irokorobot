"""Unit tests for deterministic owner anchoring (F4-D2).

Regression source: live session 2026-07-13 — the owner talked about his
children before introducing himself and the old heuristic ("first person
learned IS the owner") anchored a child ('Máximo') as the owner, then
misattributed the owner's hobbies to the child.
"""

import pytest
from server.memory.consolidation import _self_intro_name
from server.schemas import ExtractedEntity, TurnExtraction


def _extraction(*names: str) -> TurnExtraction:
    return TurnExtraction(
        entities=[ExtractedEntity(name=n, type="person") for n in names],
        facts=[],
        episodic_summary=None,
        importance=0.5,
    )


@pytest.mark.unit
def test_children_mentioned_first_do_not_anchor() -> None:
    """THE 2026-07-13 regression: no self-intro → no owner, period."""
    text = "sí, tengo dos hijos. Máximo tiene diez años y mi hija Dominga tiene ocho"

    assert _self_intro_name(text, _extraction("Máximo", "Dominga")) is None


@pytest.mark.unit
def test_me_llamo_with_full_name_entity_anchors_full_name() -> None:
    text = "ay, te quería contar de mí, me llamo Felipe Castro, tengo 40"

    assert _self_intro_name(text, _extraction("Felipe Castro")) == "Felipe Castro"


@pytest.mark.unit
def test_me_llamo_without_entities_falls_back_to_first_word() -> None:
    """Extractor failed the turn — the regex capture alone still anchors,
    but only ONE word (the greedy two-word capture may grab a verb)."""
    text = "me llamo felipe tengo cuarenta años"

    assert _self_intro_name(text, _extraction()) == "Felipe"


@pytest.mark.unit
def test_soy_de_place_does_not_anchor() -> None:
    """'soy de Santiago' is not an introduction."""
    assert _self_intro_name("soy de santiago de chile", _extraction()) is None


@pytest.mark.unit
def test_mi_nombre_es_anchors() -> None:
    assert _self_intro_name("mi nombre es dominga", _extraction()) == "Dominga"


@pytest.mark.unit
def test_ungrounded_entity_does_not_refine_the_capture() -> None:
    """A person entity NOT present in the user's words (hallucinated or from
    context) must not replace the literal captured name."""
    text = "me llamo felipe"

    assert _self_intro_name(text, _extraction("Felipe Dominguez")) == "Felipe"
