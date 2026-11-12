"""No datum the alta loads stays unreachable by voice (Plan 0082 Task 8, ADR 0037 decision 5).

Every field the seed importer can write, and every field of a contact row, has an entry in the
reach map: a voice read, or the reason it is not said aloud. A field added later without an entry
fails here, and every claimed read is checked against the reader that makes it.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest
from server.cognition.recall_cues import RELATION_PREDICATES
from server.cognition.sensitive_questions import TOPIC_PREDICATE
from server.memory import contact_access, seed_plan
from server.memory.alta_reach import ALTA_REACH, CONTACT_FIELD_REACH, Reach, ReachEntry
from server.memory.care_contacts import CareContact
from server.memory.predicate_registry import POOL_PREDICATE_IDS
from server.memory.profile_card import CARD_PREDICATES
from server.memory.seed_file import load_seed_file
from server.memory.seed_plan import ALTA_FIELDS, build_plan

pytestmark = pytest.mark.unit

_EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "examples" / "seed-household.example.toml"
_READS = frozenset({Reach.CARD, Reach.RELATIVES, Reach.SENSITIVE, Reach.CONTACTS})


def _predicates(reach: Reach) -> set[str]:
    return {predicate for (_, predicate), entry in ALTA_REACH.items() if entry.reach is reach}


def test_every_alta_field_has_a_reach() -> None:
    assert set(ALTA_REACH) == set(ALTA_FIELDS)


def test_the_alta_fields_cover_every_write_of_the_example_file() -> None:
    loaded = load_seed_file(_EXAMPLE)
    plan = build_plan(loaded.seed)
    written = {
        (operation.subject.role.value, operation.predicate)
        for operation in plan.operations
        if operation.subject is not None and operation.predicate is not None
    }
    assert written
    assert written <= set(ALTA_FIELDS)


def test_the_pool_is_inside_the_alta() -> None:
    assert {predicate for _, predicate in ALTA_FIELDS} >= POOL_PREDICATE_IDS


def test_every_contact_field_has_a_reach() -> None:
    assert set(CONTACT_FIELD_REACH) == {field.name for field in dataclasses.fields(CareContact)}


def test_each_read_is_real() -> None:
    assert _predicates(Reach.CARD) <= CARD_PREDICATES
    assert _predicates(Reach.SENSITIVE) <= set(TOPIC_PREDICATE.values())
    # «child_of» is the children-list route (CHILDREN_LIST_SENTENCE), the rest ``relation_of``.
    assert _predicates(Reach.RELATIVES) <= RELATION_PREDICATES | {"child_of"}
    assert not _predicates(Reach.CONTACTS)  # contacts are table fields, not predicates


def _fields_contact_access_reads() -> set[str]:
    tree = ast.parse(Path(contact_access.__file__).read_text(encoding="utf-8"))
    return {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "row"
    }


def test_the_contact_fields_said_aloud_are_the_ones_contact_access_reads() -> None:
    said = {name for name, entry in CONTACT_FIELD_REACH.items() if entry.reach is Reach.CONTACTS}
    assert said == _fields_contact_access_reads()


def test_a_reason_goes_with_every_unread_field() -> None:
    for entry in (*ALTA_REACH.values(), *CONTACT_FIELD_REACH.values()):
        if entry.reach in _READS:
            assert entry.reason is None
        else:
            assert entry.reason


def test_a_read_entry_refuses_a_reason_and_an_unread_one_needs_it() -> None:
    with pytest.raises(ValueError, match="no reason"):
        ReachEntry(Reach.CARD, "a reason")
    with pytest.raises(ValueError, match="needs a reason"):
        ReachEntry(Reach.RULE)


def test_the_household_members_own_literals_wait_for_the_family_stage() -> None:
    for field in (("child", "stated_age"), ("child", "likes"), ("pet", "species")):
        assert ALTA_REACH[field].reach is Reach.FAMILY_STAGE


def _relations_written_by_hand() -> set[str]:
    """The predicates ``seed_plan`` passes as a literal to ``_relation`` (its third argument)."""
    tree = ast.parse(Path(seed_plan.__file__).read_text(encoding="utf-8"))
    return {
        node.args[2].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_relation"
        and len(node.args) > 2
        and isinstance(node.args[2], ast.Constant)
        and isinstance(node.args[2].value, str)
    }


def test_a_relation_written_by_hand_is_an_alta_field() -> None:
    """A predicate hard-coded in the builder, not only its key tables, must have a reach."""
    by_hand = _relations_written_by_hand()
    assert by_hand >= {"child_of", "partner_of", "pet_of", "withhold_from"}
    assert by_hand <= {predicate for _, predicate in ALTA_FIELDS}
