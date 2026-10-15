"""SQL parameters never reach a log (ADR 0021 decision 12): aiosqlite is held at WARNING."""

from collections.abc import Generator
import logging

import pytest
from server.logging_setup import configure_logging
from server.settings import Settings, settings

pytestmark = pytest.mark.unit


@pytest.fixture
def _restore_logging() -> Generator[None, None, None]:
    """Configure logging again from the process settings after the test."""
    yield
    configure_logging(settings)


@pytest.mark.usefixtures("_restore_logging")
def test_the_sql_driver_is_held_at_warning_even_when_the_app_logs_debug() -> None:
    """At DEBUG aiosqlite prints each statement with its parameters: a taste would be logged."""
    configure_logging(Settings(log_level="DEBUG", log_to_file=False))

    assert logging.getLogger().getEffectiveLevel() == logging.DEBUG
    assert logging.getLogger("aiosqlite").getEffectiveLevel() == logging.WARNING
