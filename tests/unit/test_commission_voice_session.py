"""The voice enrolment session: a read script, several references, a level check (Plan 0072).

ADR 0024 decision 15. Every adapter is injected, so the session tests without a microphone or HTTP.
It survives the 503 the endpoint returns when speaker authentication is off, re-captures a clip that
fails the level check, and logs no clip or token; the endpoint embeds and discards the audio.
"""

from __future__ import annotations

import logging

import pytest
from server.commission_session import (
    READING_SCRIPT,
    CommissionError,
    SpeakerAuthDisabledError,
    run_voice_session,
)

pytestmark = pytest.mark.unit

_TOKEN = "unlock-token-canary"  # noqa: S105 — a fake token for the stubbed adapter, not a secret
_CLIP = b"RIFFwav-bytes-canary"


def _adapters(
    *,
    level_results: list[bool] | None = None,
    enroll_raises: Exception | None = None,
    unlock_raises: bool = False,
):
    calls = {"record": 0, "unlock": 0, "enroll": 0}
    levels = list(level_results) if level_results is not None else None

    async def unlock() -> str:
        calls["unlock"] += 1
        if unlock_raises:
            raise CommissionError("PIN rechazado")
        return _TOKEN

    def record() -> bytes:
        calls["record"] += 1
        return _CLIP

    def level_check(clip: bytes) -> bool:
        assert clip == _CLIP
        return True if levels is None else levels.pop(0)

    async def enroll(token: str, clip: bytes) -> str:
        calls["enroll"] += 1
        assert token == _TOKEN
        assert clip == _CLIP
        if enroll_raises is not None:
            raise enroll_raises
        return f"voiceprint-{calls['enroll']}"

    return unlock, record, level_check, enroll, calls


async def test_three_good_clips_enrol_three_references_and_print_the_script() -> None:
    unlock, record, level_check, enroll, calls = _adapters()
    lines: list[str] = []

    count = await run_voice_session(
        unlock=unlock,
        record=record,
        level_check=level_check,
        enroll=enroll,
        write_text=lines.append,
        references=3,
    )

    assert count == 3
    assert calls == {"record": 3, "unlock": 3, "enroll": 3}
    assert READING_SCRIPT in lines


async def test_a_clip_that_fails_the_level_check_is_recaptured() -> None:
    unlock, record, level_check, enroll, calls = _adapters(level_results=[False, True, True, True])

    count = await run_voice_session(
        unlock=unlock,
        record=record,
        level_check=level_check,
        enroll=enroll,
        write_text=lambda _: None,
        references=3,
    )

    assert count == 3
    assert calls["record"] == 4  # the first clip failed the level check and did not count
    assert calls["enroll"] == 3


async def test_speaker_authentication_off_returns_zero_without_crashing() -> None:
    unlock, record, level_check, enroll, _ = _adapters(
        enroll_raises=SpeakerAuthDisabledError("speaker authentication disabled")
    )
    lines: list[str] = []

    count = await run_voice_session(
        unlock=unlock,
        record=record,
        level_check=level_check,
        enroll=enroll,
        write_text=lines.append,
        references=3,
    )

    assert count == 0
    assert any("no se enrol" in line.lower() for line in lines)


async def test_an_unlock_that_raises_propagates() -> None:
    unlock, record, level_check, enroll, _ = _adapters(unlock_raises=True)

    with pytest.raises(CommissionError):
        await run_voice_session(
            unlock=unlock,
            record=record,
            level_check=level_check,
            enroll=enroll,
            write_text=lambda _: None,
            references=3,
        )


async def test_no_clip_or_token_reaches_a_log(caplog: pytest.LogCaptureFixture) -> None:
    unlock, record, level_check, enroll, _ = _adapters()

    with caplog.at_level(logging.DEBUG):
        await run_voice_session(
            unlock=unlock,
            record=record,
            level_check=level_check,
            enroll=enroll,
            write_text=lambda _: None,
            references=3,
        )

    assert all(
        _TOKEN not in entry.getMessage() and "wav-bytes-canary" not in entry.getMessage()
        for entry in caplog.records
    )


async def test_the_microphone_waits_for_the_countdown_before_recording() -> None:
    events: list[str] = []

    async def unlock() -> str:
        events.append("unlock")
        return _TOKEN

    def record() -> bytes:
        events.append("record")
        return _CLIP

    async def enroll(token: str, clip: bytes) -> str:
        return "voiceprint"

    async def sleep(seconds: float) -> None:
        events.append(f"sleep:{seconds}")

    await run_voice_session(
        unlock=unlock,
        record=record,
        level_check=lambda _: True,
        enroll=enroll,
        write_text=lambda _: None,
        references=1,
        countdown_s=3.0,
        sleep=sleep,
    )

    assert events == ["sleep:3.0", "record", "unlock"]
