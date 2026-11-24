"""Who may read a document, audited before any search (Plan 0088 Task B5, D-15).

Mirrors ``test_recall_access``: the face-identified owner at ``basic``, the policy and the audit row
**before** the search; a visitor, an unknown face or no face hears the generic denial; with a second
face in view the ``sensitive`` level is left out of the request and of the search. Canaries only.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from server.cognition.authorization import DataSensitivity, evaluate_authorization
from server.cognition.document_cues import DocumentCue
from server.cognition.identity import ActivePersonContext, HouseholdRole, IdentityEvidenceSource
from server.cognition.identity_fusion import FusionReason
from server.cognition.models import AuthorizationAction
from server.cognition.recall_cues import CueStrength
from server.memory.document_access import NOT_IN_DOCUMENTS, document_reply
from server.memory.document_store import DocumentHit, DocumentSearch, DocumentSection

from tests.unit.test_recall_access import _actor

if TYPE_CHECKING:
    from server.cognition.response_plan import DocumentReply

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 11, 4, 15, tzinfo=UTC)
_CUE = DocumentCue(strength=CueStrength.WEAK, named=("manual", "lavadora"), query="el filtro")
_CANARY = "zzcanaryzz gire el filtro"


def _found(*, scope: bool = True, hit: bool = True) -> AsyncMock:
    section = DocumentSection(
        id=1, source_id=1, position=0, title="Manual", heading="", body=_CANARY
    )
    hits = (DocumentHit(section=section, distance=0.2),) if hit else ()
    return AsyncMock(return_value=DocumentSearch(scope_found=scope, hits=hits, rejected=0))


async def _reply(
    actor: ActivePersonContext | None = None,
    *,
    faces: FusionReason | None = FusionReason.FACE_ONLY,
    search: AsyncMock | None = None,
    answer: AsyncMock | None = None,
    policy: Mock | None = None,
    audit: AsyncMock | None = None,
) -> DocumentReply:
    async with httpx.AsyncClient() as client:
        return await document_reply(
            actor or _actor(),
            _CUE,
            question="¿Qué dice el manual de la lavadora sobre el filtro?",
            faces=faces,
            correlation_id=uuid4(),
            now=_NOW,
            client=client,
            search=search or _found(),
            answer=answer or AsyncMock(return_value="Según Manual: gírelo."),
            policy=policy or Mock(side_effect=evaluate_authorization),
            audit=audit or AsyncMock(),
        )


async def test_the_owner_s_face_reads_after_the_policy_and_the_audit() -> None:
    calls: list[str] = []
    audit = AsyncMock(side_effect=lambda *_: calls.append("audit"))
    original = _found().return_value

    async def searching(*_args: object, **_kwargs: object) -> DocumentSearch:
        calls.append("search")
        return original

    reply = await _reply(audit=audit, search=AsyncMock(side_effect=searching))

    assert calls == ["audit", "search"]
    assert reply.found
    assert reply.text == "Según Manual: gírelo."


async def test_the_action_is_the_document_read_at_basic_with_normal_and_private() -> None:
    policy = Mock(side_effect=evaluate_authorization)
    search = _found()

    await _reply(policy=policy, search=search)

    request = policy.call_args.args[0]
    assert request.action is AuthorizationAction.READ_PERSONAL_DOCUMENT
    assert request.sensitivity == frozenset({DataSensitivity.NORMAL, DataSensitivity.PRIVATE})
    assert search.call_args.kwargs["levels"] == frozenset({"normal", "sensitive"})
    assert evaluate_authorization(request).decision.value == "allowed"


async def test_a_second_face_leaves_the_sensitive_level_out() -> None:
    policy = Mock(side_effect=evaluate_authorization)
    search = _found()

    await _reply(faces=FusionReason.VETO_MULTIPLE_FACES, policy=policy, search=search)

    assert policy.call_args.args[0].sensitivity == frozenset({DataSensitivity.NORMAL})
    assert search.call_args.kwargs["levels"] == frozenset({"normal"})


@pytest.mark.parametrize("role", [HouseholdRole.ADULT, HouseholdRole.CHILD, HouseholdRole.GUEST])
async def test_another_member_hears_the_denial_and_nothing_is_searched(role: HouseholdRole) -> None:
    search = _found()

    reply = await _reply(_actor(role=role), search=search)

    assert reply.denied
    assert reply.text is None
    search.assert_not_awaited()


async def test_a_pin_grant_alone_is_not_the_face() -> None:
    search = _found()

    reply = await _reply(_actor(source=IdentityEvidenceSource.LOCAL_UNLOCK), search=search)

    assert reply.denied
    search.assert_not_awaited()


async def test_a_failing_audit_means_no_search_and_the_fixed_phrase() -> None:
    search = _found()

    reply = await _reply(audit=AsyncMock(side_effect=RuntimeError("down")), search=search)

    assert reply.text == NOT_IN_DOCUMENTS
    search.assert_not_awaited()


async def test_a_failing_search_never_raises() -> None:
    reply = await _reply(search=AsyncMock(side_effect=RuntimeError("db")))

    assert reply.text == NOT_IN_DOCUMENTS


async def test_no_document_named_is_no_scope_and_nothing_found_is_no_text() -> None:
    no_scope = await _reply(search=_found(scope=False, hit=False))
    nothing = await _reply(search=_found(hit=False))

    assert (no_scope.scope_found, no_scope.text) == (False, None)
    assert (nothing.scope_found, nothing.text, nothing.found) == (True, None, False)


async def test_the_log_holds_counts_and_never_a_text(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        await _reply()

    records = [r for r in caplog.records if getattr(r, "event", None) == "document.read"]
    assert len(records) == 1
    assert records[0].__dict__["outcome"] == "found"
    assert _CANARY not in caplog.text
