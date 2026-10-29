"""Every reachable system prompt stays byte-identical across the legacy retirement (Plan 0076).

The fixture holds one SHA-256 per prompt, computed on ``main`` before the legacy memory path was
removed. Today every voice and chat turn builds its prompt with no memory context and no
onboarding, so those are the only values pinned; a change to any other block fails here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import itertools
import json
from pathlib import Path
from uuid import uuid4

import pytest
from server.characters import build_system_prompt, get_character
from server.cognition.identity import (
    ActivePersonContext,
    HouseholdRole,
    IdentityEvidence,
    IdentityEvidenceSource,
    PersonRecord,
    resolve_active_person,
)
from server.cognition.models import Confidence, ConfidenceBasis
from server.settings import ProfileCardPosition, settings

from server import characters, llm, llm_streaming

pytestmark = pytest.mark.unit

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "prompt_golden.json"
_NOW = datetime(2026, 10, 29, 10, 0, tzinfo=UTC)
_DATE = "jueves 29 de octubre de 2026"
_CHARACTERS = ("iroko", "nova", "ejemplo_vendedor")
_CARD = '--- Lo que sabes de la persona con quien hablas ---\n- Le gusta: "el mate".'
_POSITIONS: tuple[ProfileCardPosition, ...] = ("with_memory", "before_language")


def _face_actor() -> ActivePersonContext:
    person = PersonRecord(person_id=7, display_name="Canary", entity_type="person")
    evidence = IdentityEvidence(
        evidence_id=uuid4(),
        source=IdentityEvidenceSource.FACE,
        candidate_person_id=7,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
        observed_at=_NOW - timedelta(seconds=1),
        reference="canary",
    )
    return resolve_active_person(
        evidence=(evidence,),
        lookup_person=lambda pid: person if pid == 7 else None,
        lookup_role=lambda _pid: HouseholdRole.OWNER,
        clock=lambda: _NOW,
    )


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def golden_prompts(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Build every prompt of the matrix and return its digest by case key."""
    monkeypatch.setattr(characters, "current_date_es", lambda _today=None: _DATE)
    actors: dict[str, ActivePersonContext | None] = {"none": None, "face": _face_actor()}
    digests: dict[str, str] = {}
    for name, card, position, emotion, perception, actor_key in itertools.product(
        _CHARACTERS, (None, _CARD), _POSITIONS, (None, "sadness"), (None, "una taza"), actors
    ):
        key = f"{name}|{card is not None}|{position}|{emotion}|{perception}|{actor_key}"
        actor = actors[actor_key]
        monkeypatch.setattr(settings, "robot_character", name)
        monkeypatch.setattr(settings, "profile_card_position", position)
        digests[f"system|{key}"] = _digest(
            build_system_prompt(
                get_character(name),
                user_emotion=emotion,
                active_person=actor,
                perception=perception,
                profile_card=card,
                profile_card_position=position,
            )
        )
        digests[f"classic|{key}"] = _digest(
            llm._classic_system_prompt(
                llm._build_classic_base_prompt(
                    user_emotion=emotion,
                    active_person=actor,
                    perception=perception,
                    profile_card=card,
                )
            )
        )
        digests[f"stream|{key}"] = _digest(
            llm_streaming._streaming_system_prompt(
                llm_streaming._build_streaming_base_prompt(
                    user_emotion=emotion,
                    active_person=actor,
                    profile_card=card,
                )
            )
        )
    return digests


def test_every_reachable_prompt_matches_the_golden_digests(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = json.loads(_FIXTURE.read_text(encoding="utf-8"))

    actual = golden_prompts(monkeypatch)

    changed = sorted(key for key in expected if actual.get(key) != expected[key])
    assert set(actual) == set(expected)
    assert changed == []
