"""The routes' «today» is the household's day, never the machine's (found by Plan 0084's CI).

A server in UTC (CI, a container, a board) and a household in Chile disagree on the date for
three hours a night; «¿qué hice ayer?» then searched the wrong day. Two zones 25 hours apart make
the check deterministic: at any moment at least one of them is on another date than the machine.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from server.characters import current_date_es
from server.memory.household_time import household_today
from server.routers import chat, transcribe, vision
from server.settings import settings

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("zone", ["Pacific/Kiritimati", "Pacific/Pago_Pago"])
def test_every_route_reads_the_household_day(monkeypatch: pytest.MonkeyPatch, zone: str) -> None:
    monkeypatch.setattr(settings, "household_timezone", zone)
    expected = datetime.now(UTC).astimezone(ZoneInfo(zone)).date()

    assert household_today() == expected
    assert chat._today() == expected
    assert transcribe._today() == expected
    assert vision._today() == expected


@pytest.mark.parametrize("zone", ["Pacific/Kiritimati", "Pacific/Pago_Pago"])
def test_the_prompt_says_the_household_day(monkeypatch: pytest.MonkeyPatch, zone: str) -> None:
    monkeypatch.setattr(settings, "household_timezone", zone)
    expected = datetime.now(UTC).astimezone(ZoneInfo(zone)).date()

    assert current_date_es() == current_date_es(expected)
