"""Opt-in, console-only log of what was heard and what is spoken (Plan 0052).

Household content stays out of every log by default (Plans 0031/0032). An
operator debugging their own machine can switch it on with
``LOG_CONVERSATION_TEXT=true``; ``logging_setup.configure_logging`` then enables
this logger and attaches the console handler to it and to nothing else.

Three properties make that safe and are enforced here and in the tests:

- the logger is **disabled** until ``set_enabled(True)``, so by default a record
  is dropped before any handler — including a test's capture handler — sees it;
- ``propagate`` is ``False``, so a record never reaches the root handlers and
  therefore never the JSON Lines file under ``logs/``;
- only transcripts and spoken sentences pass through this module. PINs, tokens,
  biometrics and household values from the memory layer stay unlogged.
"""

import logging

CONVERSATION_LOGGER_NAME = "server.conversation_text"

_logger = logging.getLogger(CONVERSATION_LOGGER_NAME)
_logger.propagate = False
_logger.disabled = True


def set_enabled(enabled: bool) -> None:
    """Turn the conversation text log on or off for the whole process.

    Args:
        enabled: ``True`` only when the operator opted in with
            ``LOG_CONVERSATION_TEXT=true``.
    """
    _logger.disabled = not enabled


def log_heard(text: str) -> None:
    """Record what the speech-to-text stage heard, when the operator opted in.

    Args:
        text: Transcript of the user's speech (already decoded from the 16 kHz
            mono int16 WAV the STT received).
    """
    _logger.info("Heard: %s", text)


def log_spoken(text: str) -> None:
    """Record a sentence about to be synthesized, when the operator opted in.

    Args:
        text: Text handed to the text-to-speech stage (its output is 16 kHz
            mono int16 WAV).
    """
    _logger.info("Spoken: %s", text)
