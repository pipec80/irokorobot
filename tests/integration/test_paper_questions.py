"""Questions about the paper just read, through the real voice routes (Plan 0090 Tasks 5 and 6).

Face detection, speech and the reader are doubles; the identity store, the policy, the slot and
the conversation record are real. Every paper is an invented canary.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from server.cognition.response_plan import (
    COULD_NOT_READ,
    NOT_IN_PAPER,
    PAPER_NEEDS_IDENTITY,
    PAPER_NOT_INTERPRETED,
    PAPER_RECORDED_TEXT,
    READING_KEPT,
)
from server.exceptions import VisionError
from server.memory.conversation_consent import grant_conversation_consent
from server.memory.reading_offer import READING_SLOT
from server.routers import transcribe as transcribe_module
from server.settings import settings

from server import db
from tests.integration.test_document_routes import _models, household
from tests.integration.test_recall_routes import _client, _files, _hear, _see_the_owner, _spoken

if TYPE_CHECKING:
    from server.personal_setup import PersonalSetupResult

pytestmark = pytest.mark.integration

_BILL = "Boleta qqluzqq\nConsumo del período\nTotal a pagar: $12.345\nVence: 15-12-2026"
_ROUTES = ["/transcribe", "/transcribe/stream"]
__all__ = ["household"]  # the fixture, imported so this module can use it


@pytest.fixture
async def paper(
    household: tuple[PersonalSetupResult, int], monkeypatch: pytest.MonkeyPatch
) -> PersonalSetupResult:
    monkeypatch.setattr(settings, "vision_enabled", True)
    monkeypatch.setattr(transcribe_module, "read_text", AsyncMock(return_value=_BILL))
    READING_SLOT.clear()
    return household[0]


async def _turns(route: str, *frames: bool) -> list[str]:
    async with _client() as client:
        return [
            _spoken(await client.post(route, files=_files(with_frame=frame)), route)
            for frame in frames
        ]


@pytest.mark.parametrize("route", _ROUTES)
async def test_the_paper_answers_its_amount_and_its_due_date_by_quotation(
    paper: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "lee esto", "¿Cuánto tengo que pagar?", "¿Para cuándo es?")
    prompts = _models(monkeypatch)

    spoken = await _turns(route, True, True, True)

    assert spoken[1] == "Según el papel: Total a pagar: $12.345"
    assert spoken[2] == "Según el papel: Vence: 15-12-2026"
    assert prompts == []  # no model words a paper's answer


async def test_a_question_the_paper_cannot_answer_says_so(
    paper: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        transcribe_module, "read_text", AsyncMock(return_value="Querida qqtiaqq: te saludo.")
    )
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "lee esto", "¿Cuánto tengo que pagar?")
    _models(monkeypatch)

    spoken = await _turns("/transcribe", True, True)

    assert spoken[1] == NOT_IN_PAPER


async def test_with_no_paper_the_question_is_today_s_turn(
    paper: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "¿Cuánto tengo que pagar?", "¿Es grave?")
    prompts = _models(monkeypatch)

    spoken = await _turns("/transcribe", True, True)

    assert not spoken[0].startswith("Según el papel")
    assert spoken[1] != PAPER_NOT_INTERPRETED
    assert len(prompts) == 2  # both reached the generic model, as before this plan


async def test_with_a_paper_open_another_question_keeps_its_branch(
    paper: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "lee esto", "¿Qué día es hoy?", "¿Cuánto tengo que pagar?")
    _models(monkeypatch)

    spoken = await _turns("/transcribe", True, True, True)

    assert not spoken[1].startswith("Según el papel")
    assert spoken[2] == "Según el papel: Total a pagar: $12.345"  # the paper is still there


async def test_the_answer_is_recorded_as_a_marker_never_the_paper(
    paper: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "conversation_record_enabled", True)
    await grant_conversation_consent(
        paper.owner_entity_id, notice_version="v1", now=datetime.now(UTC)
    )
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "lee esto", "¿Cuánto tengo que pagar?")
    _models(monkeypatch)

    await _turns("/transcribe", True, True)

    cursor = await db.get_conn().execute("SELECT said FROM conversation_turns ORDER BY id")
    said = [str(row[0]) for row in await cursor.fetchall()]
    await cursor.close()
    assert said[-1] == PAPER_RECORDED_TEXT
    assert not any("12.345" in text for text in said)


async def test_a_keep_right_after_an_interpreting_question_keeps_the_paper(
    paper: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """«¿Es grave?» is a turn about the paper, so «sí, guárdalo» right after still keeps it."""
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "lee esto", "¿Es grave?", "Sí, guárdalo")
    _models(monkeypatch)

    spoken = await _turns("/transcribe", True, True, True)

    assert spoken[1] == PAPER_NOT_INTERPRETED
    assert spoken[2] == READING_KEPT


async def test_a_failed_new_reading_leaves_no_old_paper_answering(
    paper: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review finding 2: bill A read, bill B fails; «¿cuánto…?» must not quote bill A."""
    monkeypatch.setattr(
        transcribe_module, "read_text", AsyncMock(side_effect=[_BILL, VisionError("blurred")])
    )
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "lee esto", "lee esto", "¿Cuánto tengo que pagar?")
    _models(monkeypatch)

    spoken = await _turns("/transcribe", True, True, True)

    assert spoken[1] == COULD_NOT_READ
    assert "12.345" not in spoken[2]


@pytest.mark.parametrize("route", _ROUTES)
async def test_a_question_that_asks_to_interpret_hears_the_fixed_phrase(
    paper: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "lee esto", "¿Es grave?")
    prompts = _models(monkeypatch)

    spoken = await _turns(route, True, True)

    assert spoken[1] == PAPER_NOT_INTERPRETED
    assert prompts == []


async def test_a_reading_with_nobody_identified_answers_no_question(
    paper: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR 0041 decision 5: read aloud to anyone, answered to nobody unknown."""
    _hear(monkeypatch, "lee esto", "¿Cuánto tengo que pagar?")
    _models(monkeypatch)

    spoken = await _turns("/transcribe", True, True)  # no face is ever seen

    assert spoken[1] == PAPER_NEEDS_IDENTITY
    assert "12.345" not in spoken[1]


async def test_the_owner_s_paper_asked_with_no_face_in_view_answers_nothing(
    paper: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, "lee esto", "¿Cuánto tengo que pagar?", "¿Cuánto tengo que pagar?")
    _models(monkeypatch)

    spoken = await _turns("/transcribe", True, False, True)

    assert spoken[1] == PAPER_NEEDS_IDENTITY  # the unknown turn reads nothing ...
    assert spoken[2] == "Según el papel: Total a pagar: $12.345"  # ... and ends nothing
