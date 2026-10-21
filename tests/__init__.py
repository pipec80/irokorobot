"""Test package.

Imported before `tests/conftest.py`, and therefore before the module-level
`settings` singletons read the developer's local `.env`.
"""

import os

# Debug aids in a developer's `.env` must not change what the suite asserts. With
# LOG_CONVERSATION_TEXT=true, every privacy sentinel would see household text
# (Plan 0052). The environment variable outranks the `.env` file.
os.environ["LOG_CONVERSATION_TEXT"] = "false"

# The suite must not append to the owner's real `logs/server.log`: `server.main` builds the
# production app at import and `LOG_TO_FILE` defaults to on, so every gate run once added tens of
# thousands of test lines to the log a person reads to measure their own sessions (2026-10-21).
# Tests of the file handler pass their own `Settings(log_to_file=True, log_dir=tmp_path)`.
os.environ["LOG_TO_FILE"] = "false"
