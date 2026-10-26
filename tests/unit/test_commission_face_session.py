"""The face enrolment session: several frames, one unlock each (Plan 0072, ADR 0024 dec 15).

Every adapter is injected (unlock, capture, enroll), so the session tests without a camera or HTTP.
No frame, token or image byte is logged; the real endpoint embeds and discards the image.
"""

from __future__ import annotations

import logging

import pytest
from server.commission_session import CommissionError, run_face_session

pytestmark = pytest.mark.unit

_TOKEN = "unlock-token-canary"  # noqa: S105 — a fake token for the stubbed adapter, not a secret
_FRAME = b"\xff\xd8jpeg-bytes-canary\xff\xd9"


def _adapters(*, reject_at: int | None = None, unlock_raises: bool = False):
    calls = {"unlock": 0, "capture": 0, "enroll": 0}

    async def unlock() -> str:
        calls["unlock"] += 1
        if unlock_raises:
            raise CommissionError("PIN rechazado")
        return _TOKEN

    def capture() -> bytes:
        calls["capture"] += 1
        return _FRAME

    async def enroll(token: str, frame: bytes) -> str:
        calls["enroll"] += 1
        assert token == _TOKEN
        assert frame == _FRAME
        if reject_at is not None and calls["enroll"] == reject_at:
            raise CommissionError("no_face")
        return f"profile-{calls['enroll']}"

    return unlock, capture, enroll, calls


async def test_five_good_frames_enrol_five_times_each_with_its_own_unlock() -> None:
    unlock, capture, enroll, calls = _adapters()

    count = await run_face_session(
        unlock=unlock, capture=capture, enroll=enroll, write_text=lambda _: None, frames=5
    )

    assert count == 5
    assert calls == {"unlock": 5, "capture": 5, "enroll": 5}


async def test_the_frame_prompts_appear_in_order() -> None:
    unlock, capture, enroll, _ = _adapters()
    lines: list[str] = []

    await run_face_session(
        unlock=unlock, capture=capture, enroll=enroll, write_text=lines.append, frames=5
    )

    takes = [line for line in lines if "Toma " in line]
    assert [f"Toma {n} de 5" in line for n, line in enumerate(takes, start=1)] == [True] * 5


async def test_a_rejected_frame_stops_and_counts_the_successes() -> None:
    unlock, capture, enroll, calls = _adapters(reject_at=3)

    count = await run_face_session(
        unlock=unlock, capture=capture, enroll=enroll, write_text=lambda _: None, frames=5
    )

    assert count == 2
    assert calls["enroll"] == 3  # the third was attempted and rejected, then the session stopped
    assert calls["unlock"] == 3


async def test_an_unlock_that_raises_propagates() -> None:
    unlock, capture, enroll, _ = _adapters(unlock_raises=True)

    with pytest.raises(CommissionError):
        await run_face_session(
            unlock=unlock, capture=capture, enroll=enroll, write_text=lambda _: None, frames=5
        )


async def test_no_frame_or_token_reaches_a_log(caplog: pytest.LogCaptureFixture) -> None:
    unlock, capture, enroll, _ = _adapters()

    with caplog.at_level(logging.DEBUG):
        await run_face_session(
            unlock=unlock, capture=capture, enroll=enroll, write_text=lambda _: None, frames=5
        )

    assert all(
        _TOKEN not in record.getMessage() and "jpeg-bytes-canary" not in record.getMessage()
        for record in caplog.records
    )
