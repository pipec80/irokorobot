"""The example seed file is also the questionnaire (Plan 0071 Task 6b).

It parses, plans and passes a dry run; every key carries its question as a Spanish comment in
neutral tuteo (no voseo); it holds only invented names and phones; and its name marks it as a
template the command refuses to apply.
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest
from server.memory.commissioning import Section, SectionStatus
from server.memory.seed_file import load_seed_file
from server.memory.seed_import import resolve_ready_owner
from server.memory.seed_plan import build_plan
from server.memory.seed_run import run_seed

from tests.integration.seed_household import NOW, owner, seed_db

__all__ = ["owner", "seed_db"]

pytestmark = pytest.mark.integration

_EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "examples" / "seed-household.example.toml"
_KEY_LINE = re.compile(r"^\s*([a-z_]+)\s*=")
_VOSEO = re.compile(
    r"\b(tenés|querés|podés|sabés|sos|vivís|decís|escribís|tomás|usás|llamás|preferís|ponés|"
    r"poné|decime|contame|fijate|acordate|mirá|guardás|desplazás|escuchás|entrás)\b",
    re.IGNORECASE,
)
_NAME = re.compile(r'^\s*name\s*=\s*"([^"]*)"')
_PHONE = re.compile(r'^\s*phone(?:_alt)?\s*=\s*"([^"]*)"', re.MULTILINE)


def _lines() -> list[str]:
    return _EXAMPLE.read_text(encoding="utf-8").splitlines()


def test_the_example_is_a_template_by_its_name() -> None:
    assert _EXAMPLE.name.endswith(".example.toml")


def test_every_key_carries_its_question_as_a_comment() -> None:
    lines = _lines()
    missing = []
    for index, line in enumerate(lines):
        if _KEY_LINE.match(line) is None:
            continue
        previous = lines[index - 1].strip() if index else ""
        if "#" not in line and not previous.startswith("#"):
            missing.append(line.strip())

    assert missing == []


def test_the_comments_are_spanish_tuteo_without_voseo() -> None:
    comments = " ".join(line.split("#", 1)[1] for line in _lines() if "#" in line)

    assert _VOSEO.findall(comments) == []
    assert "Nunca escribas el código, solo quién lo sabe" in comments


def test_the_address_says_the_numbers_go_there() -> None:
    (address,) = [line for line in _lines() if line.startswith("address ")]

    assert "Aquí sí van los números" in address


def test_only_invented_names_and_phones() -> None:
    text = _EXAMPLE.read_text(encoding="utf-8")
    names = [m.group(1) for line in _lines() if (m := _NAME.match(line))]

    assert names
    assert all(name.startswith("Canary") for name in names)
    phones = _PHONE.findall(text)
    assert phones
    assert all(phone.startswith(("+569000000", "+562000000")) for phone in phones)


def test_the_example_covers_every_section_and_a_caregiver_child() -> None:
    seed = load_seed_file(_EXAMPLE).seed
    statuses = build_plan(seed).section_statuses

    assert set(statuses) == set(Section)
    assert SectionStatus.NOT_ASKED not in statuses.values()
    assert statuses[Section.DEVICES] is SectionStatus.NONE
    children = {child.name for child in seed.children}
    assert any(contact.name in children for contact in seed.contacts)


async def test_the_example_passes_a_dry_run(owner: int) -> None:
    loaded = load_seed_file(_EXAMPLE)
    assert await resolve_ready_owner(loaded.seed.owner.name) == owner

    report = await run_seed(
        loaded,
        build_plan(loaded.seed),
        owner_entity_id=owner,
        commit=False,
        approved=False,
        commissioning=None,
        replace=False,
        now=NOW,
    )

    assert report.problems == ()
    assert report.applied is False
