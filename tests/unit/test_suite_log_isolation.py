"""The test suite must never write the owner's real log file (found 2026-10-21)."""

import os

import pytest
from server.settings import settings


@pytest.mark.unit
def test_the_suite_does_not_log_to_the_owners_file() -> None:
    configured = os.environ.get(
        "LOG_TO_FILE"
    )  # one value, so a failure never prints the environment

    assert configured == "false"
    assert settings.log_to_file is False  # server.main builds its app from this at import
