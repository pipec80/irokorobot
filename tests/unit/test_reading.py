"""«Iroko, lee esto» (Plan 0088 Task B9, D-17): the closed phrases, the VLM call, the slot.

Pure or with doubles: the VLM is a ``MockTransport``; the slot's clock is a parameter.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import json

import httpx
import pytest
from server.cognition.document_cues import is_keep_phrase, is_reading_request
from server.cognition.intent_resolution import resolve_information_need
from server.cognition.response_plan import InformationNeed
from server.exceptions import VisionError
from server.memory.reading_offer import PAPER_MAX_CHARS, ReadingSlot
from server.settings import settings
from server.vision.read_text import READ_PROMPT, read_text

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 11, 23, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    "message",
    [
        "Iroko, lee esto.",
        "léeme esto",
        "Lee lo que dice, por favor.",
        "¿Qué dice aquí?",
        "¿qué dice acá?",
    ],
)
def test_each_reading_shape_is_a_reading_request(message: str) -> None:
    assert is_reading_request(message)
    assert (
        resolve_information_need(message, documents=True, reading=True).need
        is InformationNeed.READ_TEXT
    )


@pytest.mark.parametrize(
    "message",
    ["Lee esto que te mando por correo y dime", "¿Qué dice el manual?", "Me leí esto ayer.", ""],
)
def test_the_traps_are_no_reading_request(message: str) -> None:
    assert not is_reading_request(message)


def test_without_the_reading_flag_a_reading_phrase_is_today_s() -> None:
    assert resolve_information_need("lee esto").need is InformationNeed.GENERIC_CONVERSATION


@pytest.mark.parametrize("message", ["Sí, guárdalo.", "si guardalo", "Guárdalo, por favor."])
def test_the_keep_phrase(message: str) -> None:
    assert is_keep_phrase(message)


@pytest.mark.parametrize("message", ["No lo guardes.", "Sí", "guárdalo en la memoria de Zeta"])
def test_not_the_keep_phrase(message: str) -> None:
    assert not is_keep_phrase(message)


async def test_read_text_sends_one_fixed_prompt_and_the_frame() -> None:
    sent: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        return httpx.Response(
            200, json={"message": {"role": "assistant", "content": " Leche 1 L "}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        text = await read_text(client, b"\xff\xd8canary")

    assert text == "Leche 1 L"
    (message,) = sent["messages"]  # type: ignore[misc]  # the JSON body of the request
    assert message["content"] == READ_PROMPT
    assert message["images"] == [base64.b64encode(b"\xff\xd8canary").decode()]


@pytest.mark.parametrize("reply", [httpx.ConnectError("down"), ""])
async def test_a_vlm_failure_or_nothing_read_raises(reply: Exception | str) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        if isinstance(reply, Exception):
            raise reply
        return httpx.Response(200, json={"message": {"role": "assistant", "content": reply}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(VisionError):
            await read_text(client, b"\xff\xd8canary")


@pytest.mark.parametrize(
    "reply, cause", [(httpx.ReadTimeout("slow"), "ReadTimeout"), ("", "nothing_read")]
)
async def test_a_failed_reading_logs_its_cause_and_no_text(
    reply: Exception | str, cause: str, caplog: pytest.LogCaptureFixture
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        if isinstance(reply, Exception):
            raise reply
        return httpx.Response(200, json={"message": {"role": "assistant", "content": reply}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with (
            caplog.at_level("WARNING", logger="server.vision.read_text"),
            pytest.raises(VisionError),
        ):
            await read_text(client, b"\xff\xd8canary")

    (record,) = [r for r in caplog.records if getattr(r, "event", None) == "vision.read_failed"]
    assert record.cause == cause  # type: ignore[attr-defined]  # set through ``extra``
    assert "canary" not in record.getMessage()


def test_the_paper_is_held_whole_for_its_speaker_until_silence() -> None:
    """ADR 0041 decision 3: the whole text waits for its speaker; silence ends it."""
    slot = ReadingSlot()
    slot.offer("zzpapel " * 600, speaker=7, now=_NOW)  # 4,800 characters

    held = slot.paper_for(7, _NOW + timedelta(seconds=100))
    assert held is not None
    assert len(held) == PAPER_MAX_CHARS
    assert slot.paper_for(8, _NOW + timedelta(seconds=100)) is None
    # A paper turn at 100 s restarts the silence: at 279 s it still waits, at 281 s it is gone.
    assert slot.paper_for(7, _NOW + timedelta(seconds=279)) is not None
    assert slot.paper_for(7, _NOW + timedelta(seconds=279 + 181)) is None
    assert not slot.is_open(_NOW + timedelta(seconds=279 + 181))


def test_another_identified_person_ends_the_paper_and_an_unknown_turn_does_not() -> None:
    slot = ReadingSlot()
    slot.offer("zzuno", speaker=7, now=_NOW)

    slot.observe(None, _NOW + timedelta(seconds=10))
    assert slot.paper_for(7, _NOW + timedelta(seconds=20)) == "zzuno"
    slot.observe(7, _NOW + timedelta(seconds=30))
    assert slot.paper_for(7, _NOW + timedelta(seconds=40)) == "zzuno"
    slot.observe(8, _NOW + timedelta(seconds=50))
    assert not slot.is_open(_NOW + timedelta(seconds=50))


def test_an_unknown_turn_does_not_extend_the_silence() -> None:
    slot = ReadingSlot()
    slot.offer("zzuno", speaker=7, now=_NOW)
    slot.observe(None, _NOW + timedelta(seconds=170))

    assert slot.paper_for(7, _NOW + timedelta(seconds=181)) is None


def test_keeping_gives_the_whole_text_to_its_speaker_and_the_paper_stays() -> None:
    """ADR 0041 decision 6: the keep verb works while the paper lives, even after questions."""
    slot = ReadingSlot()
    slot.offer("zzuno", speaker=7, now=_NOW)
    slot.paper_for(7, _NOW + timedelta(seconds=90))

    assert slot.take(8, _NOW + timedelta(seconds=120)) is None
    assert slot.take(7, _NOW + timedelta(seconds=120)) == "zzuno"
    assert slot.paper_for(7, _NOW + timedelta(seconds=130)) == "zzuno"


def test_a_reading_bound_to_nobody_keeps_no_text_and_a_new_reading_replaces_it() -> None:
    slot = ReadingSlot()
    slot.offer("zzuno", speaker=7, now=_NOW)
    slot.offer("zzdos", speaker=None, now=_NOW)

    assert slot.is_open(_NOW)
    assert slot.take(7, _NOW) is None
    assert slot.paper_for(7, _NOW) is None
    assert "zzdos" not in repr(slot)


def test_a_keep_needs_the_turn_before_to_be_about_the_paper() -> None:
    """Review finding 3 (Pipec, 2026-11-26): after other talk «sí, guárdalo» is not the paper's."""
    slot = ReadingSlot()
    slot.begin_turn()
    slot.offer("zzuno", speaker=7, now=_NOW)  # turn 1, the reading
    slot.begin_turn()
    assert slot.paper_for(7, _NOW) == "zzuno"  # turn 2, a question about it
    slot.begin_turn()
    assert slot.take(7, _NOW) == "zzuno"  # turn 3, right after: kept
    slot.begin_turn()  # turn 4, talk of something else
    slot.begin_turn()
    assert slot.take(7, _NOW) is None  # turn 5: not the paper's any more
    assert slot.paper_for(7, _NOW) == "zzuno"  # but it can still be asked about


def test_clearing_empties_the_slot() -> None:
    slot = ReadingSlot()
    slot.offer("zzuno", speaker=7, now=_NOW)
    slot.clear()

    assert slot.take(7, _NOW) is None
    assert not slot.is_open(_NOW)
    assert "zzuno" not in repr(slot)


async def test_a_good_reading_logs_vision_metrics(caplog: pytest.LogCaptureFixture) -> None:
    """Plan 0089 D-11: the reading says what it cost, in milliseconds and counts."""

    def handler(_request: httpx.Request) -> httpx.Response:
        body = {
            "message": {"role": "assistant", "content": "Leche 1 L"},
            "load_duration": 3_000_000,
            "eval_count": 5,
            "eval_duration": 7_000_000,
        }
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with caplog.at_level("INFO", logger="server.vision.read_text"):
            await read_text(client, b"\xff\xd8canary")

    (record,) = [r for r in caplog.records if getattr(r, "event", None) == "vision.metrics"]
    assert record.capability == "reading"  # type: ignore[attr-defined]  # set through ``extra``
    assert record.load_ms == 3  # type: ignore[attr-defined]
    assert record.eval_count == 5  # type: ignore[attr-defined]
    assert record.eval_ms == 7  # type: ignore[attr-defined]
    assert record.total_ms is None  # type: ignore[attr-defined]
    assert "canary" not in record.getMessage()


@pytest.fixture
def neutral_vlm(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "vlm_image_max_side",
        "vlm_num_ctx",
        "vlm_num_predict_scene",
        "vlm_num_predict_reading",
        "vlm_keep_alive",
    ):
        monkeypatch.setattr(settings, name, None)


def _capturing(sent: list[dict[str, object]]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "Leche"}})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_unset_settings_send_today_s_reading_payload(neutral_vlm: None) -> None:
    """Plan 0089 D-12: unset, the reading payload is byte-identical to before."""
    sent: list[dict[str, object]] = []
    async with _capturing(sent) as client:
        await read_text(client, b"\xff\xd8canary")

    (payload,) = sent
    assert set(payload) == {"model", "messages", "stream", "options"}
    assert payload["options"] == {"temperature": 0.0}


async def test_the_reading_cap_and_context_reach_the_reading(
    neutral_vlm: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "vlm_num_predict_reading", 400)
    monkeypatch.setattr(settings, "vlm_num_predict_scene", 120)
    monkeypatch.setattr(settings, "vlm_num_ctx", 4096)
    monkeypatch.setattr(settings, "vlm_keep_alive", "10m")
    sent: list[dict[str, object]] = []
    async with _capturing(sent) as client:
        await read_text(client, b"\xff\xd8canary")

    assert sent[0]["options"] == {"temperature": 0.0, "num_ctx": 4096, "num_predict": 400}
    assert sent[0]["keep_alive"] == "10m"
