"""Test package.

Imported before `tests/conftest.py`, and therefore before the module-level
`settings` singletons read the developer's local `.env`.
"""

import os

# Debug aids in a developer's `.env` must not change what the suite asserts. With
# LOG_CONVERSATION_TEXT=true, every privacy sentinel would see household text
# (Plan 0052). The environment variable outranks the `.env` file.
os.environ["LOG_CONVERSATION_TEXT"] = "false"
