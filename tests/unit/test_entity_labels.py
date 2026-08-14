"""Unit tests for exact non-legacy person labels used by P0.5-B2."""

from unittest.mock import AsyncMock, Mock

import pytest
from server.memory.entity_labels import EntityLabel, get_person_label


@pytest.mark.asyncio
async def test_get_person_label_reads_only_one_exact_person(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return an immutable label from the exact person-ID query only."""
    cursor = AsyncMock()
    cursor.fetchone.return_value = (7, "Máximo")
    connection = Mock()
    connection.execute = AsyncMock(return_value=cursor)
    monkeypatch.setattr("server.memory.entity_labels.get_conn", lambda: connection)

    result = await get_person_label(entity_id=7)

    assert result == EntityLabel(entity_id=7, display_name="Máximo")
    connection.execute.assert_awaited_once_with(
        "SELECT id, name FROM entities WHERE id = ? AND type = ?",
        (7, "person"),
    )
    cursor.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_person_label_returns_unknown_for_no_exact_person(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Never turn a missing or non-person entity into a display label."""
    cursor = AsyncMock()
    cursor.fetchone.return_value = None
    connection = Mock()
    connection.execute = AsyncMock(return_value=cursor)
    monkeypatch.setattr("server.memory.entity_labels.get_conn", lambda: connection)

    result = await get_person_label(entity_id=8)

    assert result is None
    cursor.close.assert_awaited_once()
