"""Unit tests for the profile card's access: policy, audit before the read, never a raise (Plan 0074)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import aiosqlite
import pytest
from server.cognition.authorization import AuthorizationRequest, evaluate_authorization
from server.cognition.identity import (
    ActivePersonContext,
    HouseholdRole,
    IdentityAssurance,
    IdentityEvidence,
    IdentityEvidenceSource,
    PersonRecord,
    resolve_active_person,
)
from server.cognition.models import (
    AuthorizationAction,
    AuthorizationDecision,
    Confidence,
    ConfidenceBasis,
)
from server.cognition.response_plan import ProfileSummaryReply
from server.exceptions import BrainMemoryError
from server.memory.profile_card import CARD_PREDICATES, CardTaste, ProfileCard
from server.memory.profile_card_access import (
    CardOutcome,
    CardRead,
    profile_summary_text,
    prompt_card_text,
    read_card,
)
from server.memory.relational_v4 import AssertionLifecycle, LiteralFactV4

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 10, 28, 10, 0, tzinfo=UTC)
_OWNER = 7
_CORRELATION = UUID(int=74)
_CANARY_CARD = ProfileCard(None, None, (CardTaste("likes", "el mate"),))


def _evidence(source: IdentityEvidenceSource, person_id: int = _OWNER) -> IdentityEvidence:
    token = source is IdentityEvidenceSource.LOCAL_UNLOCK
    return IdentityEvidence(
        evidence_id=uuid4(),
        source=source,
        candidate_person_id=person_id,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
        observed_at=_NOW - timedelta(seconds=1),
        reference="canary",
        expires_at=_NOW + timedelta(minutes=5) if token else None,
        grant_scope="personal_protected_read" if token else None,
        grant_spent=token,
    )


def _actor(
    *sources: IdentityEvidenceSource, role: HouseholdRole = HouseholdRole.OWNER
) -> ActivePersonContext:
    person = PersonRecord(person_id=_OWNER, display_name="Canary", entity_type="person")
    return resolve_active_person(
        evidence=tuple(_evidence(source) for source in sources),
        lookup_person=lambda pid: person if pid == _OWNER else None,
        lookup_role=lambda _pid: role,
        clock=lambda: _NOW,
    )


def _face(role: HouseholdRole = HouseholdRole.OWNER) -> ActivePersonContext:
    return _actor(IdentityEvidenceSource.FACE, role=role)


def _row(value: str = "el mate") -> LiteralFactV4:
    return LiteralFactV4(
        id=1,
        subject_entity_id=_OWNER,
        predicate="likes",
        value_text=value,
        confidence=1.0,
        source_memory_id=None,
        asserted_at="2026-10-28T10:00:00.000000+00:00",
        valid_from=None,
        valid_to=None,
        lifecycle=AssertionLifecycle.ACTIVE,
        visibility="personal",
        sensitivity="normal",
        superseded_at=None,
        superseded_by=None,
    )


async def _read(
    actor: ActivePersonContext,
    *,
    audit: AsyncMock | None = None,
    reader: AsyncMock | None = None,
    policy: Mock | None = None,
) -> CardRead:
    return await read_card(
        actor,
        correlation_id=_CORRELATION,
        now=_NOW,
        audit=audit or AsyncMock(),
        reader=reader or AsyncMock(return_value=[_row()]),
        policy=policy or evaluate_authorization,
    )


async def test_a_face_owner_at_basic_gets_the_card_and_one_audit_row_before_the_read() -> None:
    order: list[str] = []

    def policy(request: AuthorizationRequest) -> AuthorizationDecision:
        order.append("policy")
        return evaluate_authorization(request)

    audit = AsyncMock(side_effect=lambda *_: order.append("audit"))
    reader = AsyncMock(side_effect=lambda **_: order.append("reader") or [_row()])

    result = await _read(_face(), audit=audit, reader=reader, policy=Mock(side_effect=policy))

    assert result.outcome is CardOutcome.ALLOWED
    assert result.card == ProfileCard(None, None, (CardTaste("likes", "el mate"),))
    assert order == ["policy", "audit", "reader"]
    audit.assert_awaited_once()
    request, decision = audit.call_args.args
    assert request.action is AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY
    assert request.target_person_id == _OWNER
    assert request.correlation_id == _CORRELATION
    assert decision.decision.value == "allowed"
    reader.assert_awaited_once_with(subject_entity_id=_OWNER, predicates=CARD_PREDICATES)


@pytest.mark.parametrize("role", [HouseholdRole.ADULT, HouseholdRole.CHILD, HouseholdRole.GUEST])
async def test_a_non_owner_is_denied_and_audited_and_never_read(role: HouseholdRole) -> None:
    audit = AsyncMock()
    reader = AsyncMock()

    result = await _read(_face(role), audit=audit, reader=reader)

    assert result == CardRead(CardOutcome.DENIED, None)
    audit.assert_awaited_once()
    assert audit.call_args.args[1].decision.value == "denied"
    reader.assert_not_awaited()


async def test_an_audit_failure_is_unavailable_and_never_reads(
    caplog: pytest.LogCaptureFixture,
) -> None:
    audit = AsyncMock(side_effect=RuntimeError("disk full: zumo de pomelo"))
    reader = AsyncMock()

    with caplog.at_level("DEBUG"):
        result = await _read(_face(), audit=audit, reader=reader)

    assert result == CardRead(CardOutcome.UNAVAILABLE, None)
    reader.assert_not_awaited()
    assert "pomelo" not in caplog.text


@pytest.mark.parametrize(
    "failure",
    [
        BrainMemoryError("db down: zumo de pomelo"),
        aiosqlite.Error("locked: zumo de pomelo"),
        ValueError("corrupt row: zumo de pomelo"),
    ],
    ids=["brain-memory", "aiosqlite", "corrupt-row"],
)
async def test_any_read_failure_is_unavailable(
    failure: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    audit = AsyncMock()

    with caplog.at_level("DEBUG"):
        result = await _read(_face(), audit=audit, reader=AsyncMock(side_effect=failure))

    assert result == CardRead(CardOutcome.UNAVAILABLE, None)
    audit.assert_awaited_once()  # the row precedes the read, whatever the read does
    assert "pomelo" not in caplog.text


def _below_basic() -> ActivePersonContext:
    return _face().model_copy(update={"assurance": IdentityAssurance.NONE})


@pytest.mark.parametrize(
    "actor",
    [
        _actor(),
        _actor(IdentityEvidenceSource.VOICE),
        _below_basic(),
        resolve_active_person(
            evidence=(
                _evidence(IdentityEvidenceSource.FACE, _OWNER),
                _evidence(IdentityEvidenceSource.FACE, _OWNER + 1),
            ),
            lookup_person=lambda pid: PersonRecord(
                person_id=pid, display_name="Canary", entity_type="person"
            ),
            lookup_role=lambda _pid: HouseholdRole.OWNER,
            clock=lambda: _NOW,
        ),
    ],
    ids=["unknown", "voice-only", "assurance-none", "ambiguous"],
)
async def test_an_unidentified_ambiguous_or_none_assurance_actor_is_not_asked(
    actor: ActivePersonContext,
) -> None:
    audit = AsyncMock()
    reader = AsyncMock()
    policy = Mock(side_effect=evaluate_authorization)

    result = await _read(actor, audit=audit, reader=reader, policy=policy)

    assert result == CardRead(CardOutcome.DENIED, None)
    policy.assert_not_called()
    audit.assert_not_awaited()
    reader.assert_not_awaited()


async def test_a_token_speaker_is_not_asked_and_writes_no_row() -> None:
    audit = AsyncMock()
    reader = AsyncMock()
    token_actor = _actor(IdentityEvidenceSource.LOCAL_UNLOCK)

    result = await _read(token_actor, audit=audit, reader=reader)

    assert result == CardRead(CardOutcome.DENIED, None)
    audit.assert_not_awaited()
    reader.assert_not_awaited()


async def test_prompt_card_text_renders_only_when_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    allowed = AsyncMock(return_value=CardRead(CardOutcome.ALLOWED, _CANARY_CARD))
    monkeypatch.setattr("server.memory.profile_card_access.read_card", allowed)

    text = await prompt_card_text(_face(), correlation_id=_CORRELATION, now=_NOW)

    assert text is not None
    assert '- Le gusta: "el mate".' in text

    for outcome in (CardOutcome.DENIED, CardOutcome.UNAVAILABLE):
        refused = AsyncMock(return_value=CardRead(outcome, None))
        monkeypatch.setattr("server.memory.profile_card_access.read_card", refused)
        assert await prompt_card_text(_face(), correlation_id=_CORRELATION, now=_NOW) is None


async def test_prompt_card_text_is_none_for_an_empty_card(monkeypatch: pytest.MonkeyPatch) -> None:
    empty = AsyncMock(return_value=CardRead(CardOutcome.ALLOWED, ProfileCard(None, None, ())))
    monkeypatch.setattr("server.memory.profile_card_access.read_card", empty)

    assert await prompt_card_text(_face(), correlation_id=_CORRELATION, now=_NOW) is None


async def test_profile_summary_text_maps_the_three_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = {
        CardRead(CardOutcome.ALLOWED, _CANARY_CARD): ProfileSummaryReply(
            text="Esto es lo que sé de ti. Me has dicho que te gusta: el mate."
        ),
        CardRead(CardOutcome.ALLOWED, ProfileCard(None, None, ())): ProfileSummaryReply(
            text="Todavía no me has contado cosas que pueda recordar."
        ),
        CardRead(CardOutcome.DENIED, None): ProfileSummaryReply(text=None, denied=True),
        CardRead(CardOutcome.UNAVAILABLE, None): ProfileSummaryReply(text=None),
    }
    for read, expected in cases.items():
        monkeypatch.setattr(
            "server.memory.profile_card_access.read_card", AsyncMock(return_value=read)
        )

        reply = await profile_summary_text(_face(), correlation_id=_CORRELATION, now=_NOW)

        assert reply == expected
