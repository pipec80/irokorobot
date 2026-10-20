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


@pytest.mark.api
def test_transcribe_stream_200_is_documented_as_ndjson() -> None:
    """The streaming route's success body is `application/x-ndjson`, never JSON.

    FastAPI infers `application/json` with an empty schema from a bare
    `-> StreamingResponse` return; the real runtime contract (Plan 0041) is
    one JSON object per line. Plan 0048 makes the generated schema say so.
    """
    op = app.openapi()["paths"]["/transcribe/stream"]["post"]
    content = op["responses"]["200"]["content"]

    assert "application/x-ndjson" in content
    assert "application/json" not in content
    # The documented body references the streaming event line shapes.
    assert "schema" in content["application/x-ndjson"]


@pytest.mark.api
def test_transcribe_stream_documents_the_optional_short_reply_field() -> None:
    """Plan 0067: an additive, optional request field; the classic route does not take it."""
    schemas = app.openapi()["components"]["schemas"]
    stream_ref = app.openapi()["paths"]["/transcribe/stream"]["post"]["requestBody"]
    stream_body = schemas[
        stream_ref["content"]["multipart/form-data"]["schema"]["$ref"].split("/")[-1]
    ]
    classic_ref = app.openapi()["paths"]["/transcribe"]["post"]["requestBody"]
    classic_body = schemas[
        classic_ref["content"]["multipart/form-data"]["schema"]["$ref"].split("/")[-1]
    ]

    assert "short_reply" in stream_body["properties"]
    assert "short_reply" not in stream_body.get("required", [])
    assert "short_reply" not in classic_body["properties"]
