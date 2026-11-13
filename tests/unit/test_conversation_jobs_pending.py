"""The conversation job names one pending topic per tick and deletes the expired (Plan 0084 Task 4).

D-5, D-6 and D-15. The store and the model are doubles; canaries only.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
import logging
from unittest.mock import AsyncMock

import httpx
import pytest
from server.exceptions import LLMError
from server.memory import conversation_jobs
from server.settings import settings

pytestmark = pytest.mark.unit

# 02:00Z on the 13th is still the 12th in Santiago.
_NOW = datetime(2026, 11, 13, 2, tzinfo=UTC)
_TODAY = date(2026, 11, 12)
_HEARD = "Mañana voy al banco a pagar una cuenta."


class _Store:
    """Doubles for the store's job-side functions, patched into the job module."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, unnamed: tuple[int, str] | None) -> None:
        self.delete_expired = AsyncMock(return_value=2)
        self.next_unnamed = AsyncMock(return_value=unnamed)
        self.set_topic = AsyncMock(return_value=True)
        self.drop = AsyncMock()
        self.count_naming_failure = AsyncMock(return_value=1)
        for name in ("delete_expired", "next_unnamed", "set_topic", "drop", "count_naming_failure"):
            monkeypatch.setattr(conversation_jobs, name, getattr(self, name))


@pytest.fixture(autouse=True)
def _quiet_job(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "conversation_record_enabled", True)
    monkeypatch.setattr(settings, "pending_topics_enabled", True)
    monkeypatch.setattr(settings, "conversation_episodes_enabled", False)
    monkeypatch.setattr(settings, "recall_enabled", False)
    monkeypatch.setattr(settings, "household_timezone", "America/Santiago")
    monkeypatch.setattr(conversation_jobs, "close_idle_records", AsyncMock(return_value=0))
    monkeypatch.setattr(conversation_jobs, "has_open_record", AsyncMock(return_value=False))


def _namer(monkeypatch: pytest.MonkeyPatch, reply: str | Exception | None) -> AsyncMock:
    mock = (
        AsyncMock(side_effect=reply)
        if isinstance(reply, Exception)
        else AsyncMock(return_value=reply)
    )
    monkeypatch.setattr(conversation_jobs, "name_topic", mock)
    return mock


def _outcomes(caplog: pytest.LogCaptureFixture, event: str) -> list[object]:
    return [r.__dict__.get("outcome") for r in caplog.records if r.__dict__.get("event") == event]


async def test_the_job_names_one_topic_per_tick(
    monkeypatch: pytest.MonkeyPatch,
    http_client: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    store = _Store(monkeypatch, unnamed=(5, _HEARD))
    namer = _namer(monkeypatch, "el banco")

    await conversation_jobs.run_once(http_client, _NOW)

    store.delete_expired.assert_awaited_once_with(today=_TODAY)
    namer.assert_awaited_once_with(http_client, _HEARD)
    store.set_topic.assert_awaited_once_with(5, "el banco")
    store.drop.assert_not_awaited()
    store.next_unnamed.assert_awaited_once()
    assert _outcomes(caplog, "pending.named") == ["named"]
    assert [
        r.__dict__.get("count")
        for r in caplog.records
        if r.__dict__.get("event") == "pending.expired"
    ] == [2]
    assert "banco" not in caplog.text


async def test_an_invented_name_drops_the_topic(
    monkeypatch: pytest.MonkeyPatch,
    http_client: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    store = _Store(monkeypatch, unnamed=(5, _HEARD))
    _namer(monkeypatch, None)

    await conversation_jobs.run_once(http_client, _NOW)

    store.drop.assert_awaited_once_with(5)
    store.set_topic.assert_not_awaited()
    assert _outcomes(caplog, "pending.named") == ["unnamed_dropped"]


@pytest.mark.parametrize(
    "error", [httpx.ConnectError("zzdownzz banco"), TimeoutError(), LLMError("zzdownzz banco")]
)
async def test_a_model_failure_keeps_the_topic_for_a_later_tick(
    monkeypatch: pytest.MonkeyPatch,
    http_client: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
) -> None:
    caplog.set_level(logging.INFO)
    store = _Store(monkeypatch, unnamed=(5, _HEARD))
    _namer(monkeypatch, error)

    await conversation_jobs.run_once(http_client, _NOW)

    store.drop.assert_not_awaited()
    store.set_topic.assert_not_awaited()
    store.count_naming_failure.assert_awaited_once_with(5)
    assert _outcomes(caplog, "pending.named") == ["model_failed"]
    assert "zzdownzz" not in caplog.text


async def test_the_third_model_failure_drops_the_topic(
    monkeypatch: pytest.MonkeyPatch,
    http_client: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A row the model keeps failing on is not retried until it expires (Task 8 review)."""
    caplog.set_level(logging.INFO)
    store = _Store(monkeypatch, unnamed=(5, _HEARD))
    store.count_naming_failure.return_value = 3
    _namer(monkeypatch, LLMError("zz"))

    await conversation_jobs.run_once(http_client, _NOW)

    store.drop.assert_awaited_once_with(5)
    assert _outcomes(caplog, "pending.named") == ["unnamed_dropped"]


async def test_nothing_unnamed_calls_no_model(
    monkeypatch: pytest.MonkeyPatch, http_client: httpx.AsyncClient
) -> None:
    store = _Store(monkeypatch, unnamed=None)
    namer = _namer(monkeypatch, "el banco")

    await conversation_jobs.run_once(http_client, _NOW)

    store.delete_expired.assert_awaited_once()
    namer.assert_not_awaited()


async def test_an_open_record_does_nothing(
    monkeypatch: pytest.MonkeyPatch, http_client: httpx.AsyncClient
) -> None:
    store = _Store(monkeypatch, unnamed=(5, _HEARD))
    namer = _namer(monkeypatch, "el banco")
    monkeypatch.setattr(conversation_jobs, "has_open_record", AsyncMock(return_value=True))

    await conversation_jobs.run_once(http_client, _NOW)

    store.delete_expired.assert_not_awaited()
    namer.assert_not_awaited()


async def test_the_switch_off_still_expires_but_names_nothing(
    monkeypatch: pytest.MonkeyPatch, http_client: httpx.AsyncClient
) -> None:
    """Rows kept while the switch was on still expire after it is turned off (Task 8 review)."""
    monkeypatch.setattr(settings, "pending_topics_enabled", False)
    store = _Store(monkeypatch, unnamed=(5, _HEARD))
    namer = _namer(monkeypatch, "el banco")

    await conversation_jobs.run_once(http_client, _NOW)

    store.delete_expired.assert_awaited_once_with(today=_TODAY)
    store.next_unnamed.assert_not_awaited()
    namer.assert_not_awaited()


@pytest.mark.parametrize("switch", ["memory_enabled", "conversation_record_enabled"])
async def test_without_memory_or_the_record_the_job_touches_no_topic(
    monkeypatch: pytest.MonkeyPatch,
    http_client: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
    switch: str,
) -> None:
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(settings, switch, False)
    store = _Store(monkeypatch, unnamed=(5, _HEARD))
    namer = _namer(monkeypatch, "el banco")

    await conversation_jobs.run_once(http_client, _NOW)

    store.delete_expired.assert_not_awaited()
    store.next_unnamed.assert_not_awaited()
    namer.assert_not_awaited()
    assert not [
        r for r in caplog.records if str(r.__dict__.get("event", "")).startswith("pending.")
    ]


async def test_no_expired_topic_logs_no_count(
    monkeypatch: pytest.MonkeyPatch,
    http_client: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    store = _Store(monkeypatch, unnamed=None)
    store.delete_expired.return_value = 0

    await conversation_jobs.run_once(http_client, _NOW)

    assert not [r for r in caplog.records if r.__dict__.get("event") == "pending.expired"]
