"""The admin_local write channel (Plan 0073 Task 2, ADR 0025 decision 4).

`admin_local` is a write channel like the others, but it is **not** an import channel and not a
voice channel: the import-channel architecture guard must not capture it, and the importer's
retraction (which deletes by `IMPORT_CHANNELS`) must never touch an admin write.
"""

from __future__ import annotations

import pytest
from server.memory.write_types import IMPORT_CHANNELS, VOICE_CHANNELS, WriteChannel

pytestmark = pytest.mark.unit


def test_admin_local_is_a_write_channel() -> None:
    assert WriteChannel.ADMIN_LOCAL == "admin_local"


def test_admin_local_is_not_an_import_or_voice_channel() -> None:
    assert WriteChannel.ADMIN_LOCAL not in IMPORT_CHANNELS
    assert WriteChannel.ADMIN_LOCAL not in VOICE_CHANNELS
