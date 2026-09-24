"""Opt-in, console-only log of what the robot heard and speaks (Plan 0052).

The robot's counterpart of ``server.conversation_log``: household content stays
out of every log by default (Plans 0031/0032) and ``LOG_CONVERSATION_TEXT=true``
is the one deliberate, local, debugging exception. The two packages share only
the API contract, so this is a small deliberate copy, not an import.

Safety properties, pinned by the tests:

- the logger is **disabled** until ``enable_console`` runs, so by default a
  record is dropped before any handler sees it;
- ``propagate`` is ``False``, so a record never reaches the root handlers and
  therefore never the JSON Lines file under ``logs/``.
"""

import logging

CONVERSATION_LOGGER_NAME = "robot.conversation_text"

_logger = logging.getLogger(CONVERSATION_LOGGER_NAME)
_logger.propagate = False
_logger.disabled = True


def enable_console(formatter: logging.Formatter) -> None:
    """Print conversation text on the console, and only there.

    Args:
        formatter: The console formatter the rest of the robot logs use.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)
    _logger.disabled = False


def log_heard(text: str) -> None:
    """Record what the server transcribed from the user's speech.

    Args:
        text: The transcript the server returned for the captured utterance
            (16 kHz mono int16 WAV on the wire).
    """
    _logger.info("Heard: %s", text)


def log_spoken(text: str) -> None:
    """Record a sentence the robot is about to play.

    Args:
        text: The sentence whose audio (16 kHz mono int16 WAV) is played.
    """
    _logger.info("Spoken: %s", text)
