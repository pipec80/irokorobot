"""Guards the generated OpenAPI schema itself (Plan 0037).

Belongs in the deterministic CI gate, not Plan 0040's own contract work:
this test protects the gate from a schema that silently stops generating
(a broken route, a bad response model) — Plan 0040 later adds per-endpoint
assertions on top of a schema this test already proved exists and is valid.

This locks down behavior that is already correct today — FastAPI generates
a valid OpenAPI document from the app's routes with no extra wiring — so it
cannot RED against current code. It exists as a regression guard for the
gate itself, the same category as `test_close_db_leaves_get_conn_raising`
in Plan 0035's `test_db.py`.
"""

import pytest
from server.main import app


@pytest.mark.api
def test_openapi_schema_is_valid() -> None:
    """`/docs` depends on this schema; it must never silently stop generating."""
    schema = app.openapi()

    assert schema["openapi"].startswith("3.")
    assert schema["paths"]
