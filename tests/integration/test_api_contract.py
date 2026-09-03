"""Locks the current HTTP surface before Plan 0040 touches it (Task 1).

Every route present today must remain present with the same operation ID
after this plan lands — these tests pin that baseline. The version and
security-scheme assertions RED against today's code on purpose: they name
two real gaps this plan closes (Task 5, Task 2).
"""

from __future__ import annotations

import importlib.metadata
from typing import Any

from fastapi.testclient import TestClient
import httpx
import pytest
from server.cognition.owner_authentication import owner_unlock_service
from server.main import app
from server.resources import AppResources
from server.routers import transcribe as transcribe_module

# (method, path) for every route this plan must not remove or rename.
_EXISTING_ROUTES = {
    ("GET", "/health"),
    ("POST", "/auth/owner/unlock"),
    ("POST", "/auth/owner/face/enroll"),
    ("POST", "/auth/owner/face/revoke"),
    ("POST", "/chat"),
    ("POST", "/transcribe"),
    ("POST", "/transcribe/stream"),
    ("POST", "/vision/describe"),
    ("POST", "/vision/enroll"),
    ("POST", "/vision/respond"),
}


def _operations() -> dict[tuple[str, str], dict[str, Any]]:  # Any: heterogeneous OpenAPI operation
    """Return {(method, path): operation} for every path in the schema."""
    schema = app.openapi()
    return {
        (method.upper(), path): operation
        for path, methods in schema["paths"].items()
        for method, operation in methods.items()
    }


@pytest.mark.api
def test_every_existing_route_is_still_present() -> None:
    """No core route may disappear or change path/method in this plan."""
    operations = _operations()
    missing = _EXISTING_ROUTES - set(operations)
    assert not missing, f"routes missing from the schema: {missing}"


@pytest.mark.api
def test_operation_ids_are_unique() -> None:
    """A duplicate operationId breaks generated client codegen silently."""
    operations = _operations()
    operation_ids = [op["operationId"] for op in operations.values()]
    assert len(operation_ids) == len(set(operation_ids))


@pytest.mark.api
def test_every_operation_has_tag_summary_and_typed_response() -> None:
    """Every route needs a tag, a summary, and a declared success response.

    A 204 (e.g. face revoke) legitimately carries no body/schema; every
    other 2xx must declare its response content.
    """
    operations = _operations()
    for (method, path), operation in operations.items():
        assert operation.get("tags"), f"{method} {path} has no tag"
        assert operation.get("summary"), f"{method} {path} has no summary"
        responses = operation.get("responses", {})
        success_codes = [code for code in responses if code.startswith("2")]
        assert success_codes, f"{method} {path} has no 2xx response"
        for code in success_codes:
            if code == "204":
                continue
            assert "content" in responses[code], f"{method} {path}'s {code} response has no schema"


@pytest.mark.api
def test_installed_server_package_version_is_advertised() -> None:
    """The schema must report the real installed package version, not a hardcoded one."""
    schema = app.openapi()
    assert schema["info"]["version"] == importlib.metadata.version("server")


@pytest.mark.api
def test_identity_token_header_is_a_declared_optional_security_scheme() -> None:
    """X-Iroko-Identity-Token must appear in components.securitySchemes,
    without making any public endpoint require it."""
    schema = app.openapi()
    schemes = schema.get("components", {}).get("securitySchemes", {})
    assert schemes, "no security scheme declared in the OpenAPI schema"
    identity_scheme = next(
        (s for s in schemes.values() if s.get("name") == "X-Iroko-Identity-Token"),
        None,
    )
    assert identity_scheme is not None, "X-Iroko-Identity-Token is not a declared security scheme"
    assert identity_scheme["type"] == "apiKey"
    assert identity_scheme["in"] == "header"

    operations = _operations()
    for (method, path), operation in operations.items():
        required_security = [
            requirement
            for requirement in operation.get("security", [])
            if any(requirement.values())
        ]
        assert not required_security, f"{method} {path} must not require identity token security"


#: (method, path) -> the non-2xx/422 status codes that route can actually
#: raise today (from its own `HTTPException(status_code=...)` call sites) —
#: 422 is excluded since FastAPI already documents it automatically for
#: every route via its own request-validation machinery.
_EXPECTED_ERROR_CODES = {
    ("POST", "/auth/owner/unlock"): {401, 403, 429},
    ("POST", "/auth/owner/face/enroll"): {401, 403, 413, 503},
    ("POST", "/auth/owner/face/revoke"): {401, 403},
    ("POST", "/transcribe"): {413},
    ("POST", "/transcribe/stream"): {413},
    ("POST", "/vision/describe"): {413, 503},
    ("POST", "/vision/enroll"): {503},
    ("POST", "/vision/respond"): {503},
}


@pytest.mark.api
def test_every_raised_error_code_is_documented_with_the_detail_shape() -> None:
    """Every non-validation 4xx/5xx a route can actually raise must appear
    in its documented `responses`, with the real `{"detail": str}` wire
    shape — not the auto-generated `HTTPValidationError` shape 422 gets."""
    operations = _operations()
    for route, expected_codes in _EXPECTED_ERROR_CODES.items():
        responses = operations[route].get("responses", {})
        documented = {int(code) for code in responses if code.isdigit()}
        missing = expected_codes - documented
        assert not missing, f"{route} is missing documented codes: {missing}"
        for code in expected_codes:
            schema_ref = responses[str(code)]["content"]["application/json"]["schema"]["$ref"]
            assert schema_ref.endswith("ErrorResponse"), (
                f"{route}'s {code} response doesn't use the shared ErrorResponse shape"
            )


@pytest.mark.api
def test_an_unexpected_exception_never_leaks_internal_detail(
    silence_wav_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A genuinely unexpected failure must still answer with a generic 500 body.

    Regression guard, not a fix — this already passes today (FastAPI's
    default unhandled-exception path never echoes the exception), so it's
    proof, not new behavior. Builds its own client with
    `raise_server_exceptions=False` so the 500 becomes a real response
    instead of re-raising the exception into the test.
    """

    async def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("secret internal detail that must never reach the client")

    monkeypatch.setattr(transcribe_module, "_run_stt", _boom)
    app.state.resources = AppResources(
        http_client=httpx.AsyncClient(), owner_unlock_service=owner_unlock_service
    )

    unsafe_client = TestClient(app, raise_server_exceptions=False)
    response = unsafe_client.post(
        "/transcribe", files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")}
    )

    assert response.status_code == 500
    assert "secret internal detail" not in response.text
    assert "RuntimeError" not in response.text
    assert "Traceback" not in response.text


@pytest.mark.api
def test_every_tag_used_by_a_route_has_generated_metadata() -> None:
    """Every tag a route declares must appear in the top-level `tags` block
    with a real description — otherwise Swagger UI groups routes under a
    bare, undocumented heading."""
    schema = app.openapi()
    used_tags = {tag for op in _operations().values() for tag in op.get("tags", [])}
    documented = {entry["name"]: entry.get("description", "") for entry in schema.get("tags", [])}
    missing = used_tags - set(documented)
    assert not missing, f"tags with no top-level metadata: {missing}"
    empty = {tag for tag in used_tags if not documented.get(tag)}
    assert not empty, f"tags with an empty description: {empty}"


@pytest.mark.api
def test_docs_redoc_and_openapi_json_are_reachable(client: TestClient) -> None:
    """The generated docs UIs and schema endpoint must always resolve.

    Uses the shared, lifespan-free `client` fixture — none of these three
    routes need a real resource, so paying for Whisper/Piper/DB startup
    would only slow this contract test down for nothing.
    """
    for path in ("/docs", "/redoc", "/openapi.json"):
        response = client.get(path)
        assert response.status_code == 200, f"{path} returned {response.status_code}"
