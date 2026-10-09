"""Invariants of identity fusion that the personal-memory policy leans on (ADR 0019 §3).

The policy compares assurance by rank and trusts `strong` to mean "face and voice agreeing,
or an owner unlock". These tests sweep every combination of evidence sources for one person
through the real `resolve_active_person` and check that no combination breaks that meaning.
"""

from datetime import UTC, datetime
from itertools import combinations
from uuid import UUID

import pytest
from server.cognition.identity import (
    ActivePersonStatus,
    HouseholdRole,
    IdentityAssurance,
    IdentityEvidence,
    IdentityEvidenceSource,
    PersonRecord,
    resolve_active_person,
)
from server.cognition.models import Confidence, ConfidenceBasis

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 10, 8, 12, tzinfo=UTC)
_PERSON = PersonRecord(person_id=42, display_name="Ada", entity_type="person")
_SOURCES = (
    IdentityEvidenceSource.SESSION,
    IdentityEvidenceSource.MANUAL,
    IdentityEvidenceSource.FACE,
    IdentityEvidenceSource.VOICE,
    IdentityEvidenceSource.CONTEXT,
    IdentityEvidenceSource.LOCAL_UNLOCK,
)
_BASIC_SOURCES = frozenset(
    {
        IdentityEvidenceSource.MANUAL,
        IdentityEvidenceSource.LOCAL_UNLOCK,
        IdentityEvidenceSource.FACE,
    }
)
_FACE_AND_VOICE = frozenset({IdentityEvidenceSource.FACE, IdentityEvidenceSource.VOICE})


def _subsets() -> tuple[frozenset[IdentityEvidenceSource], ...]:
    """Every non-empty subset of the six evidence sources (63)."""
    return tuple(
        frozenset(subset)
        for size in range(1, len(_SOURCES) + 1)
        for subset in combinations(_SOURCES, size)
    )


def _evidence(source: IdentityEvidenceSource) -> IdentityEvidence:
    return IdentityEvidence(
        evidence_id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        source=source,
        candidate_person_id=_PERSON.person_id,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.ASSERTED, calibrated=True),
        observed_at=_NOW,
        reference="canary",
    )


def _resolve(
    sources: frozenset[IdentityEvidenceSource],
) -> tuple[ActivePersonStatus, IdentityAssurance]:
    context = resolve_active_person(
        evidence=tuple(_evidence(source) for source in _SOURCES if source in sources),
        lookup_person=lambda person_id: _PERSON if person_id == _PERSON.person_id else None,
        lookup_role=lambda _person_id: HouseholdRole.OWNER,
        clock=lambda: _NOW,
    )
    return context.status, context.assurance


def _violations(
    sources: frozenset[IdentityEvidenceSource],
    status: ActivePersonStatus,
    assurance: IdentityAssurance,
) -> list[str]:
    """Name every invariant that (sources, status, assurance) breaks."""
    broken = []
    if assurance is IdentityAssurance.STRONG and not (
        IdentityEvidenceSource.LOCAL_UNLOCK in sources or sources >= _FACE_AND_VOICE
    ):
        broken.append("strong without an unlock or face and voice")
    if (
        status is ActivePersonStatus.IDENTIFIED
        and assurance is IdentityAssurance.BASIC
        and not sources & _BASIC_SOURCES
    ):
        broken.append("basic without a manual, unlock or face source")
    if status is not ActivePersonStatus.IDENTIFIED and assurance is not IdentityAssurance.NONE:
        broken.append("assurance on a result that did not identify")
    if status is ActivePersonStatus.IDENTIFIED and assurance is IdentityAssurance.NONE:
        broken.append("identified without any assurance")
    return broken


def test_no_combination_of_sources_breaks_the_assurance_invariants() -> None:
    """63 source sets for one person: strong, basic and none each mean what the ADR says."""
    subsets = _subsets()
    assert len(subsets) == 63

    broken = {
        tuple(sorted(source.value for source in sources)): problems
        for sources in subsets
        if (problems := _violations(sources, *_resolve(sources)))
    }

    assert broken == {}


def test_a_voice_never_identifies_and_never_lifts_a_session_selection() -> None:
    assert _resolve(frozenset({IdentityEvidenceSource.VOICE})) == (
        ActivePersonStatus.PROBABLE,
        IdentityAssurance.NONE,
    )
    assert _resolve(frozenset({IdentityEvidenceSource.SESSION, IdentityEvidenceSource.VOICE})) == (
        ActivePersonStatus.PROBABLE,
        IdentityAssurance.NONE,
    )
    assert _resolve(frozenset({IdentityEvidenceSource.CONTEXT})) == (
        ActivePersonStatus.UNKNOWN,
        IdentityAssurance.NONE,
    )


def test_the_invariant_check_detects_a_violation() -> None:
    """A green sweep means something: synthetic bad results are flagged, good ones are not."""
    identified = ActivePersonStatus.IDENTIFIED
    strong, basic, none = (
        IdentityAssurance.STRONG,
        IdentityAssurance.BASIC,
        IdentityAssurance.NONE,
    )

    assert _violations(frozenset({IdentityEvidenceSource.FACE}), identified, strong)
    assert _violations(frozenset({IdentityEvidenceSource.VOICE}), identified, basic)
    assert _violations(
        frozenset({IdentityEvidenceSource.SESSION}), ActivePersonStatus.PROBABLE, basic
    )
    assert _violations(frozenset({IdentityEvidenceSource.FACE}), identified, none)
    assert not _violations(frozenset({IdentityEvidenceSource.LOCAL_UNLOCK}), identified, strong)
    assert not _violations(_FACE_AND_VOICE, identified, strong)
    assert not _violations(frozenset({IdentityEvidenceSource.FACE}), identified, basic)
    assert not _violations(
        frozenset({IdentityEvidenceSource.SESSION}), ActivePersonStatus.PROBABLE, none
    )
