"""When a told event happened, through the real voice routes (Plan 0083 Task 7, D-1, D-10, D-15).

Face detection, speech and the local model are doubles; the identity store, the policy, the audit,
the recall units and their search are real. Every value is an invented canary.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock
from uuid import uuid4

from pydantic import SecretStr
import pytest
from server.cognition import controller as controller_module
from server.cognition.occurred_time import occurred_window
from server.cognition.response_plan import NO_MEMORY
from server.cognition.spoken_dates import date_label, occurred_label
from server.memory import continuity, recall_store
from server.memory.biometric_consent import grant_face_consent
from server.memory.conversation_types import RecordedTurn, TurnVerdict
from server.memory.recall_search import household_zone
from server.personal_setup import PersonalSetupInput, PersonalSetupResult, apply_personal_setup
from server.settings import settings
from server.vision.faces import enroll_face
import yaml

from server import db
from tests.integration.test_recall_routes import (
    _ANSWER,
    _GENERIC,
    _OWNER_FACE,
    _ROUTES,
    _client,
    _files,
    _hear,
    _models,
    _see_the_owner,
    _spoken,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from server.cognition.spoken_dates import DayWindow

pytestmark = pytest.mark.integration

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures"
_STORIES = yaml.safe_load((_FIXTURE / "occurred_times.yaml").read_text(encoding="utf-8"))
_QUESTIONS = yaml.safe_load((_FIXTURE / "recall_cues_occurred.yaml").read_text(encoding="utf-8"))
_SATURDAY_STORY = str(_STORIES[0]["heard"])  # «El sábado fui a la playa con mi hermana.»
_LAST_YEAR_STORY = str(_STORIES[5]["heard"])  # «El año pasado fui a la nieve.»
_WHEN_BEACH = str(_QUESTIONS[4]["message"])  # «¿Se acuerda cuándo fui a la playa?»
_WHAT_YESTERDAY = str(_QUESTIONS[3]["message"])  # «¿Qué hice ayer?»


@pytest.fixture
async def household(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[PersonalSetupResult]:
    """A face-enrolled owner, memory and recall on, the occurred time off."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "occurred-routes.db")
    monkeypatch.setattr(settings, "face_authentication_enabled", True)
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "recall_enabled", True)
    monkeypatch.setattr(settings, "occurred_time_enabled", False)
    continuity.reset()
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    result = await apply_personal_setup(
        PersonalSetupInput(owner_name="Canary", child_names=("Hija Uno",), pin=SecretStr("482173"))
    )
    await grant_face_consent(result.owner_entity_id)
    await enroll_face(result.owner_entity_id, _OWNER_FACE, label="Canary")
    yield result
    continuity.reset()
    await db.close_db()
    db._conn = None


def _yesterday() -> datetime:
    return datetime.now(UTC) - timedelta(days=1)


async def _told_yesterday(owner: int, heard: str, *, with_episode: bool = False) -> DayWindow:
    """Store a verified story told yesterday with its occurred interval, as the capture would."""
    said = _yesterday()
    occurred = occurred_window(heard, said_day=said.astimezone(household_zone()).date())
    assert occurred is not None
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "INSERT INTO conversation_records (owner_entity_id, started_at, last_turn_at, "
            "closed_at, expires_at) VALUES (?, 't', 't', 't', ?)",
            (owner, (datetime.now(UTC) + timedelta(days=30)).isoformat()),
        )
        record_id = int(cursor.lastrowid or 0)
        await cursor.close()
        turn = RecordedTurn(
            at=said, heard=heard, said="ok", voice=TurnVerdict.VERIFIED, correlation_id=uuid4()
        )
        await recall_store.insert_turn_unit(
            conn, record_id=record_id, owner_entity_id=owner, turn=turn, occurred=occurred
        )
        if with_episode:
            iso = said.isoformat(timespec="microseconds")
            cursor = await conn.execute(
                "INSERT INTO conversation_episodes (owner_entity_id, source_record_id, "
                "visibility, sensitivity, summary, model, created_at, expires_at) "
                "VALUES (?, ?, 'personal', 'normal', 'zzsummaryzz', 'zzmodelzz', ?, ?)",
                (owner, record_id, iso, (datetime.now(UTC) + timedelta(days=30)).isoformat()),
            )
            episode_id = int(cursor.lastrowid or 0)
            await cursor.close()
            await recall_store.insert_episode_unit(
                conn,
                record_id=record_id,
                episode_id=episode_id,
                owner_entity_id=owner,
                summary="zzsummaryzz",
                sensitivity="normal",
                said_at=iso,
            )
    return occurred


@pytest.mark.parametrize("route", _ROUTES)
async def test_when_on_each_voice_route(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    occurred = await _told_yesterday(household.owner_entity_id, _SATURDAY_STORY)
    monkeypatch.setattr(settings, "occurred_time_enabled", True)
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, _WHEN_BEACH)
    prompts, wording = _models(monkeypatch)
    zone = household_zone()
    today = datetime.now(UTC).astimezone(zone).date()

    async with _client() as client:
        response = await client.post(route, files=_files())

    assert response.status_code == 200
    told = date_label(_yesterday(), today=today, tz=zone)
    assert (
        _spoken(response, route)
        == f"Fue {occurred_label(occurred, today=today)}. Me lo contaste {told}."
    )
    assert prompts == []
    wording.assert_not_awaited()
    if route == "/transcribe/stream":
        done = [line for line in response.text.splitlines() if '"done"' in line]
        assert done
        assert "occurred" not in done[-1]


@pytest.mark.parametrize("route", _ROUTES)
async def test_the_last_year_story_told_yesterday(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    """D-15 end to end: found for «¿qué hice ayer?» with the switch off, not with it on."""
    await _told_yesterday(household.owner_entity_id, _LAST_YEAR_STORY, with_episode=True)
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, _WHAT_YESTERDAY, _WHAT_YESTERDAY)
    _models(monkeypatch)

    async with _client() as client:
        before = await client.post(route, files=_files())
        monkeypatch.setattr(settings, "occurred_time_enabled", True)
        after = await client.post(route, files=_files())

    assert _spoken(before, route) == _ANSWER
    assert _spoken(after, route) == NO_MEMORY


@pytest.mark.parametrize("route", _ROUTES)
@pytest.mark.parametrize("message", [_SATURDAY_STORY, _WHEN_BEACH, _WHAT_YESTERDAY, _GENERIC])
@pytest.mark.parametrize("recall", [True, False])
async def test_with_the_switch_off_every_route_is_byte_identical(
    household: PersonalSetupResult,
    monkeypatch: pytest.MonkeyPatch,
    route: str,
    message: str,
    *,
    recall: bool,
) -> None:
    """Off, nothing of Plan 0083 runs: no cue is read with the flag, no store read with it."""
    await _told_yesterday(household.owner_entity_id, _SATURDAY_STORY)
    monkeypatch.setattr(settings, "recall_enabled", recall)
    seen: list[dict[str, object]] = []
    original = controller_module.classify_recall_cue

    def spy(text: str, **kwargs: object) -> object:
        seen.append(kwargs)
        return original(text, **kwargs)  # type: ignore[arg-type]  # the spy forwards as is

    monkeypatch.setattr(controller_module, "classify_recall_cue", spy)
    stores = Mock(side_effect=AssertionError("a store read with the occurred flag"))
    for name in ("lexical_hits", "vector_hits", "units_by_id", "recent_units"):
        real = getattr(recall_store, name)

        async def guarded(*args: object, _real: object = real, **kwargs: object) -> object:
            if kwargs.get("occurred"):
                stores()
            return await _real(*args, **kwargs)  # type: ignore[operator]  # the real read

        monkeypatch.setattr(f"server.memory.recall_search.{name}", guarded)
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, message)
    _models(monkeypatch)

    async with _client() as client:
        response = await client.post(route, files=_files())

    assert response.status_code == 200
    assert all(kwargs.get("occurred") is not True for kwargs in seen)
    stores.assert_not_called()
    # Today's spoken reply, exactly: only «¿qué hice ayer?» with recall on finds the story (by
    # the day it was told); everything else is the generic model's reply.
    expected = _ANSWER if recall and message == _WHAT_YESTERDAY else "Hola."
    assert _spoken(response, route) == expected


@pytest.mark.parametrize("route", _ROUTES)
async def test_the_switch_needs_recall(
    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    await _told_yesterday(household.owner_entity_id, _SATURDAY_STORY)
    monkeypatch.setattr(settings, "recall_enabled", False)
    monkeypatch.setattr(settings, "occurred_time_enabled", True)
    _see_the_owner(monkeypatch)
    _hear(monkeypatch, _WHEN_BEACH)
    prompts, wording = _models(monkeypatch)

    async with _client() as client:
        response = await client.post(route, files=_files())

    assert _spoken(response, route) == "Hola."
    assert len(prompts) == 1
    wording.assert_not_awaited()
