"""Which own contact a question names (Plan 0082 Task 2, D-5 to D-7).

The tails are folded words, as ``classify_sensitive_question`` hands them over; canaries only.
"""

from __future__ import annotations

from pathlib import Path
from typing import NotRequired, TypedDict

import pytest
from server.cognition.contact_questions import (
    ContactSelector,
    contact_selector,
    match_score,
    selects,
)
import yaml

pytestmark = pytest.mark.unit

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "contact_selectors.yaml"


class _Case(TypedDict):
    tail: str
    own: bool
    order: int | None
    roles: list[str]
    words: list[str]
    everyone: NotRequired[bool]


def _cases() -> list[_Case]:
    with _FIXTURE.open(encoding="utf-8") as handle:
        loaded: list[_Case] = yaml.safe_load(handle)
    return loaded


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["tail"])
def test_each_tail_gives_its_selector(case: _Case) -> None:
    selector = contact_selector(tuple(case["tail"].split()))
    assert selector == ContactSelector(
        own=case["own"],
        order=case["order"],
        roles=frozenset(case["roles"]),
        words=frozenset(case["words"]),
        everyone=case.get("everyone", False),
    )


def test_an_empty_selector_is_empty() -> None:
    assert contact_selector(("mis", "contactos")).is_empty
    assert not contact_selector(("mi", "hija")).is_empty
    assert not contact_selector(("mi", "contacto", "1")).is_empty


def test_selects_by_order_role_word_and_plural() -> None:
    by_order = contact_selector(("mi", "contacto", "1"))
    assert selects(by_order, call_order=1, role="other", relationship=None, name=None)
    assert not selects(by_order, call_order=2, role="other", relationship=None, name=None)
    by_role = contact_selector(("mi", "doctor"))
    assert selects(by_role, call_order=None, role="doctor", relationship=None, name=None)
    by_label = contact_selector(("mis", "hijas"))
    assert selects(
        by_label, call_order=None, role="caregiver", relationship="Hija mayor", name=None
    )
    by_name = contact_selector(("mi", "doctora", "canary"))
    assert selects(
        by_name, call_order=None, role="trusted", relationship=None, name="Canary Doctor"
    )
    other = contact_selector(("mi", "hija"))
    assert not selects(other, call_order=3, role="neighbor", relationship="vecina", name="Zeta")


def test_a_relationship_word_is_matched_folded() -> None:
    selector = contact_selector(("mi", "tia"))
    assert selects(selector, call_order=None, role="other", relationship="Tía", name=None)


def test_the_repr_holds_no_word() -> None:
    assert "canary" not in repr(contact_selector(("mi", "doctora", "canary")))


def test_the_best_match_wins_when_people_share_a_surname() -> None:
    selector = contact_selector(("mi", "amiga", "canary"))
    friend = match_score(
        selector, call_order=None, role="trusted", relationship="amiga", name="Canary Friend"
    )
    daughter = match_score(
        selector, call_order=1, role="caregiver", relationship="hija", name="Canary Daughter"
    )
    assert friend > daughter > 0


def test_an_empty_selector_scores_every_contact_alike() -> None:
    selector = contact_selector(("mis", "contactos"))
    assert match_score(selector, call_order=None, role="other", relationship=None, name=None) == 1


# --- Final review fixes (Plan 0082) ---


def test_mi_counts_only_at_the_head_of_the_tail() -> None:
    assert not contact_selector(("la", "tienda", "de", "mi", "barrio")).own
    assert contact_selector(("mi", "hija")).own
    assert contact_selector(("contacto", "1")).own


def test_my_contacts_means_everyone_whatever_else_is_said() -> None:
    selector = contact_selector(("mis", "contactos", "por", "si", "pasa", "algo"))
    assert selector.everyone
    assert match_score(selector, call_order=None, role="other", relationship="hija", name=None) == 1


def test_a_bare_mi_selects_nobody() -> None:
    selector = contact_selector(("mi",))
    assert selector.is_empty
    assert not selector.everyone
    assert (
        match_score(selector, call_order=1, role="caregiver", relationship="hija", name=None) == 0
    )


def test_my_emergency_contacts_still_filter_by_role() -> None:
    selector = contact_selector(("mis", "contactos", "de", "emergencia"))
    assert (
        match_score(selector, call_order=None, role="emergency", relationship=None, name=None) > 0
    )
    assert match_score(selector, call_order=None, role="doctor", relationship=None, name=None) == 0
