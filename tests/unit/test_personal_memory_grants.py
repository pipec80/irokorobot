"""A PIN grant authorizes only the operation it was issued for (ADR 0019 §4).

These tests run the real `OwnerRequestResolver`, `FusedIdentityResolver`, registry and
policy together; only the person and role stores, the face resolver and the speaker are
doubles. The policy sees the grant through the actor's evidence: its scope and whether this
request spent it.
"""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from uuid import UUID

import pytest
from server.cognition.authorization import (
    AuthorizationRequest,
    ConsentStatus,
    DataSensitivity,
    DataVisibility,
    evaluate_authorization,
)
from server.cognition.face_authentication import FaceAuthenticationVerdict
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityAssurance,
    IdentityEvidence,
    IdentityEvidenceSource,
    PersonRecord,
    resolve_active_person,
)
from server.cognition.identity_fusion import FusedIdentityResolver
from server.cognition.identity_sessions import IdentitySessionRegistry
from server.cognition.models import (
    AuthorizationAction,
    AuthorizationDecision,
    AuthorizationStatus,
    CognitiveEvent,
    Confidence,
    ConfidenceBasis,
)
from server.cognition.owner_authentication import OwnerRequestResolver, OwnerUnlockScope
from server.cognition.response_plan import TextTurnPayload
from server.cognition.speaker_authentication import SpeakerVerdict

if TYPE_CHECKING:
    from collections.abc import Callable

    from server.cognition.face_authentication import FaceRequestResolver
    from server.cognition.speaker_authentication import SpeakerRequestResolver

pytestmark = pytest.mark.unit

_T0 = datetime(2026, 10, 8, 12, tzinfo=UTC)
_OWNER_ID = 7
_OWNER = PersonRecord(person_id=_OWNER_ID, display_name="Ada", entity_type="person")
_READ = AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY
_PROPOSE = AuthorizationAction.PROPOSE_PERSONAL_MEMORY
_CONFIRM = AuthorizationAction.CONFIRM_PERSONAL_MEMORY
_CORRECT = AuthorizationAction.CORRECT_PERSONAL_MEMORY
_FORGET = AuthorizationAction.FORGET_PERSONAL_MEMORY
_ALL_ACTIONS = (_READ, _PROPOSE, _CONFIRM, _CORRECT, _FORGET)
_OWN_ACTION = {
    OwnerUnlockScope.PERSONAL_MEMORY_READ: _READ,
    OwnerUnlockScope.PERSONAL_MEMORY_FORGET: _FORGET,
}
_ALL_SCOPES = tuple(OwnerUnlockScope)
_GRANT_SCOPE_ID = "cm1.personal-memory.grant-scope"
_ALLOWED_ID = "cm1.personal-memory.allowed"
_MEDICAL = frozenset({DataSensitivity.MEDICAL})


def _event() -> CognitiveEvent[TextTurnPayload]:
    return CognitiveEvent(
        event_id=UUID("99999999-9999-9999-9999-999999999999"),
        schema_version=1,
        event_type="text.turn",
        occurred_at=_T0,
        recorded_at=_T0,
        source="web.chat",
        correlation_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message="canary", conversation_id="canary-scope"),
    )


class _Rig:
    """One registry on a movable clock, one issued token, and resolvers built for it."""

    def __init__(self, issued: OwnerUnlockScope) -> None:
        self.now = _T0
        self.registry = IdentitySessionRegistry(
            lookup_person=lambda _pid: None, clock=lambda: self.now, ttl=timedelta(seconds=60)
        )
        self.issued = issued
        self.token = self.registry.issue_for_person(
            _OWNER, source=IdentityEvidenceSource.LOCAL_UNLOCK, scope=issued.value
        )

    def resolver(self, asked: OwnerUnlockScope) -> OwnerRequestResolver:
        """Build the resolver a branch for the `asked` operation would use."""

        async def read_role(_person_id: int) -> HouseholdRole:
            return HouseholdRole.OWNER

        async def read_person(_person_id: int) -> PersonRecord | None:
            return _OWNER

        return OwnerRequestResolver(
            token=self.token,
            registry=self.registry,
            read_role=read_role,
            read_person=read_person,
            clock=lambda: self.now,
            scope=asked,
        )

    def fused(
        self,
        asked: OwnerUnlockScope,
        *,
        face: "_FakeFace | None" = None,
        speaker_factory: "_SpeakerFactory | None" = None,
    ) -> FusedIdentityResolver:
        """The production composition; with no face and no voice the PIN is the only path."""
        return FusedIdentityResolver(
            pin=self.resolver(asked),
            # The fakes stand in for resolvers that need a database and models; the fusion
            # only uses `resolve_actor`, `last_verdict` and `resolve_consent`.
            face=cast("FaceRequestResolver | None", face),
            speaker_factory=cast("Callable[[int], SpeakerRequestResolver] | None", speaker_factory),
            clock=lambda: self.now,
        )

    def is_spendable(self) -> bool:
        """Whether the token is still in the registry, unspent."""
        return self.registry.evidence_for(self.token) is not None


def _lookup(person_id: int) -> PersonRecord | None:
    return _OWNER if person_id == _OWNER_ID else None


def _evidence(source: IdentityEvidenceSource) -> IdentityEvidence:
    return IdentityEvidence(
        evidence_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        source=source,
        candidate_person_id=_OWNER_ID,
        confidence=Confidence(score=0.95, basis=ConfidenceBasis.MEASURED, calibrated=True),
        observed_at=_T0,
        reference="turn",
    )


def _owner_from(*sources: IdentityEvidenceSource) -> ActivePersonContext:
    """Resolve a real actor from the given evidence sources for the owner."""
    return resolve_active_person(
        evidence=tuple(_evidence(source) for source in sources),
        lookup_person=_lookup,
        lookup_role=lambda _person_id: HouseholdRole.OWNER,
        clock=lambda: _T0,
    )


class _FakeFace:
    """Stands in for the face resolver: it always identifies the owner."""

    last_verdict = FaceAuthenticationVerdict.IDENTIFIED

    async def resolve_actor(self, _event: object) -> ActivePersonContext:
        return _owner_from(IdentityEvidenceSource.FACE)

    async def resolve_consent(self, _event: object, _actor: object) -> ConsentStatus:
        return ConsentStatus.GRANTED


class _FakeSpeaker:
    """Stands in for the speaker resolver: it verifies the owner's voice."""

    last_verdict = SpeakerVerdict.VERIFIED

    async def resolve_actor(self, _event: object) -> ActivePersonContext:
        return _owner_from(IdentityEvidenceSource.VOICE)


class _SpeakerFactory:
    def __call__(self, _owner_person_id: int) -> _FakeSpeaker:
        return _FakeSpeaker()


def _decide(
    actor: ActivePersonContext,
    action: AuthorizationAction,
    *,
    sensitivity: frozenset[DataSensitivity] = frozenset({DataSensitivity.NORMAL}),
    consent: ConsentStatus = ConsentStatus.NOT_REQUIRED,
) -> AuthorizationDecision:
    return evaluate_authorization(
        AuthorizationRequest(
            actor=actor,
            action=action,
            target_person_id=_OWNER_ID,
            visibility=frozenset({DataVisibility.PERSONAL}),
            sensitivity=sensitivity,
            consent=consent,
            correlation_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            requested_at=_T0,
        )
    )


def _outcome(decision: AuthorizationDecision) -> tuple[AuthorizationStatus, str]:
    return decision.decision, decision.policy_id


async def test_a_forget_grant_forgets_only_after_this_request_spent_it() -> None:
    rig = _Rig(OwnerUnlockScope.PERSONAL_MEMORY_FORGET)
    fused = rig.fused(OwnerUnlockScope.PERSONAL_MEMORY_FORGET)
    event = _event()

    peeked = await fused.peek_actor(event)
    assert [item.grant_spent for item in peeked.evidence] == [False]
    assert _outcome(_decide(peeked, _FORGET)) == (AuthorizationStatus.DENIED, _GRANT_SCOPE_ID)
    assert rig.is_spendable()

    actor = await fused.resolve_actor(event)
    consent = await fused.resolve_consent(event, actor)
    assert [item.grant_spent for item in actor.evidence] == [True]
    after = _decide(actor, _FORGET, sensitivity=_MEDICAL, consent=consent)
    assert _outcome(after) == (AuthorizationStatus.ALLOWED, _ALLOWED_ID)
    assert not rig.is_spendable()


@pytest.mark.parametrize("issued", _ALL_SCOPES)
async def test_a_spent_grant_authorizes_only_the_operation_it_was_issued_for(
    issued: OwnerUnlockScope,
) -> None:
    """After the right resolver spends it, exactly (read, read scope) and (forget, forget scope)."""
    rig = _Rig(issued)
    fused = rig.fused(issued)
    event = _event()
    actor = await fused.resolve_actor(event)
    consent = await fused.resolve_consent(event, actor)

    for action in _ALL_ACTIONS:
        decision = _decide(actor, action, sensitivity=_MEDICAL, consent=consent)
        if _OWN_ACTION.get(issued) is action:
            assert _outcome(decision) == (AuthorizationStatus.ALLOWED, _ALLOWED_ID)
        else:
            assert _outcome(decision) == (AuthorizationStatus.DENIED, _GRANT_SCOPE_ID)


@pytest.mark.parametrize(
    "issued, asked",
    [(i, a) for i in _ALL_SCOPES for a in _ALL_SCOPES if i is not a],
    ids=lambda scope: scope.value,
)
async def test_a_grant_is_refused_by_every_other_scope_and_not_spent(
    issued: OwnerUnlockScope, asked: OwnerUnlockScope
) -> None:
    rig = _Rig(issued)

    attempt_resolver = rig.resolver(asked)
    attempt = await attempt_resolver.resolve_actor(_event())

    assert attempt.status is ActivePersonStatus.UNKNOWN
    assert attempt_resolver.consumed is False
    assert rig.is_spendable()
    assert _decide(attempt, _READ).policy_id == "p0.5.identity-unresolved"
    own = await rig.resolver(issued).resolve_actor(_event())
    again = await rig.resolver(issued).resolve_actor(_event())
    assert own.status is ActivePersonStatus.IDENTIFIED  # still spendable ...
    assert again.status is ActivePersonStatus.UNKNOWN  # ... exactly once


@pytest.mark.parametrize("scope", _ALL_SCOPES)
async def test_the_actor_evidence_and_the_granted_scope_name_the_grant(
    scope: OwnerUnlockScope,
) -> None:
    rig = _Rig(scope)
    resolver = rig.resolver(scope)
    event = _event()

    peeked = await resolver.peek_actor(event)
    assert resolver.scope == frozenset()
    spent = await resolver.resolve_actor(event)

    assert [(e.grant_scope, e.grant_spent) for e in peeked.evidence] == [(scope.value, False)]
    assert [(e.grant_scope, e.grant_spent) for e in spent.evidence] == [(scope.value, True)]
    expected = {scope.value}
    if scope is OwnerUnlockScope.PERSONAL_PROTECTED_READ:
        expected.add("child_data")  # only the child-data read names the data it unlocks
    assert resolver.scope == frozenset(expected)


async def test_a_face_identified_owner_does_not_consult_a_present_forget_token() -> None:
    """ADR 0016 §5: the face resolved first, so the PIN is not used and nothing is forgotten."""
    rig = _Rig(OwnerUnlockScope.PERSONAL_MEMORY_FORGET)
    fused = rig.fused(OwnerUnlockScope.PERSONAL_MEMORY_FORGET, face=_FakeFace())

    actor = await fused.resolve_actor(_event())

    assert actor.assurance is IdentityAssurance.BASIC
    assert fused.consumed is False
    assert rig.is_spendable()
    # At `basic` the assurance rule answers first; the grant is never even reached.
    assert _decide(actor, _FORGET).policy_id == "cm1.personal-memory.assurance-required"
    later = await rig.fused(OwnerUnlockScope.PERSONAL_MEMORY_FORGET).resolve_actor(_event())
    assert _decide(later, _FORGET).decision is AuthorizationStatus.ALLOWED


async def test_a_face_and_voice_owner_with_a_present_forget_token_still_cannot_forget() -> None:
    rig = _Rig(OwnerUnlockScope.PERSONAL_MEMORY_FORGET)
    fused = rig.fused(
        OwnerUnlockScope.PERSONAL_MEMORY_FORGET,
        face=_FakeFace(),
        speaker_factory=_SpeakerFactory(),
    )

    actor = await fused.resolve_actor(_event())

    assert actor.assurance is IdentityAssurance.STRONG
    assert fused.consumed is False
    assert rig.is_spendable()
    assert _outcome(_decide(actor, _FORGET)) == (AuthorizationStatus.DENIED, _GRANT_SCOPE_ID)
    assert _decide(actor, _READ).decision is AuthorizationStatus.ALLOWED
    assert _decide(actor, _CONFIRM).decision is AuthorizationStatus.ALLOWED
    later = await rig.fused(OwnerUnlockScope.PERSONAL_MEMORY_FORGET).resolve_actor(_event())
    assert _decide(later, _FORGET).decision is AuthorizationStatus.ALLOWED


async def test_a_grant_that_expires_between_issue_and_use_authorizes_nothing() -> None:
    rig = _Rig(OwnerUnlockScope.PERSONAL_MEMORY_FORGET)
    resolver = rig.resolver(OwnerUnlockScope.PERSONAL_MEMORY_FORGET)

    rig.now = _T0 + timedelta(seconds=61)
    actor = await resolver.resolve_actor(_event())

    assert actor.status is ActivePersonStatus.UNKNOWN
    assert resolver.consumed is False
    assert not rig.is_spendable()
    assert _decide(actor, _FORGET).policy_id == "p0.5.identity-unresolved"


def test_two_attempts_to_spend_one_grant_yield_the_evidence_exactly_once() -> None:
    rig = _Rig(OwnerUnlockScope.PERSONAL_MEMORY_FORGET)
    scope = OwnerUnlockScope.PERSONAL_MEMORY_FORGET.value

    first = rig.registry.consume_evidence(rig.token, scope=scope)
    second = rig.registry.consume_evidence(rig.token, scope=scope)

    assert first is not None
    assert first.grant_spent is True
    assert second is None
