"""The memory-discipline block of the system prompt (Plan 0061, ADR 0020 §7).

The block keeps small models from inventing facts. With short-term continuity it must also
let them rely on what the person said earlier in the same conversation, and it must not carry
the speaker's identity.
"""

from datetime import UTC, datetime

import pytest
from server.characters import _MEMORY_DISCIPLINE, build_system_prompt, get_character
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityAssurance,
)
from server.cognition.models import Confidence, ConfidenceBasis

pytestmark = pytest.mark.unit

_SPEAKER_NAME = "Canary"


def _identified(person_id: int = 7) -> ActivePersonContext:
    return ActivePersonContext(
        person_id=person_id,
        display_name=_SPEAKER_NAME,
        status=ActivePersonStatus.IDENTIFIED,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=True),
        role=HouseholdRole.OWNER,
        evidence=(),
        resolved_at=datetime(2026, 10, 13, tzinfo=UTC),
        assurance=IdentityAssurance.BASIC,
    )


def test_the_conversation_counts_as_a_source_of_truth() -> None:
    assert "earlier in this same conversation" in _MEMORY_DISCIPLINE
    assert "ONLY sources" in _MEMORY_DISCIPLINE


def test_the_admission_rule_names_both_sources_and_still_forbids_inventing() -> None:
    assert "NOT present in those sources" in _MEMORY_DISCIPLINE
    assert "NEVER invent or guess" in _MEMORY_DISCIPLINE


def test_the_model_is_told_it_stores_nothing_itself() -> None:
    """Plan 0064, D-2: support for the claim guard, which is the actual guarantee."""
    prompt = build_system_prompt(get_character("iroko"), None)

    assert "You do NOT store anything yourself" in prompt
    assert "never say you saved, registered or noted" in prompt


def test_the_block_is_always_in_the_system_prompt() -> None:
    prompt = build_system_prompt(get_character("iroko"), None)

    assert _MEMORY_DISCIPLINE in prompt


def test_the_speakers_identity_never_enters_the_system_prompt() -> None:
    profile = get_character("iroko")

    identified = build_system_prompt(profile, None, active_person=_identified())

    assert _SPEAKER_NAME not in identified
    assert identified == build_system_prompt(profile, None)
