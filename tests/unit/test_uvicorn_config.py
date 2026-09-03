"""Unit tests for the pure Uvicorn kwargs builder (Plan 0038).

`build_uvicorn_kwargs` exists so the process's actual runtime flags are a
testable, reviewable value instead of buried inline inside `uvicorn.run()`.
"""

import pytest
from server.main import build_uvicorn_kwargs
from server.settings import Settings


def _settings(**overrides: object) -> Settings:
    """A real Settings instance with no env-file/env-var interference."""
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


@pytest.mark.unit
def test_build_uvicorn_kwargs_disables_reload() -> None:
    """Reload is a dev-only feature; the runtime process never enables it."""
    kwargs = build_uvicorn_kwargs(_settings())
    assert kwargs["reload"] is False


@pytest.mark.unit
def test_build_uvicorn_kwargs_disables_proxy_headers_by_default() -> None:
    """No forwarded address is trusted without an explicit, reviewed proxy (ADR-0013)."""
    kwargs = build_uvicorn_kwargs(_settings())
    assert kwargs["proxy_headers"] is False


@pytest.mark.unit
def test_build_uvicorn_kwargs_disables_server_header() -> None:
    """Never advertise the Uvicorn version to a caller."""
    kwargs = build_uvicorn_kwargs(_settings())
    assert kwargs["server_header"] is False


@pytest.mark.unit
def test_build_uvicorn_kwargs_leaves_max_requests_unset_by_default() -> None:
    """The server must not self-terminate after a fixed request count by default."""
    kwargs = build_uvicorn_kwargs(_settings())
    assert kwargs["limit_max_requests"] is None


@pytest.mark.unit
def test_build_uvicorn_kwargs_disables_access_log() -> None:
    """RequestContextMiddleware (Plan 0032) already logs every request with timing
    and a correlation id — Uvicorn's own access log would just duplicate it."""
    kwargs = build_uvicorn_kwargs(_settings())
    assert kwargs["access_log"] is False


@pytest.mark.unit
def test_build_uvicorn_kwargs_uses_declared_timeouts() -> None:
    kwargs = build_uvicorn_kwargs(
        _settings(uvicorn_timeout_keep_alive=7, uvicorn_timeout_graceful_shutdown=45)
    )
    assert kwargs["timeout_keep_alive"] == 7
    assert kwargs["timeout_graceful_shutdown"] == 45


@pytest.mark.unit
def test_build_uvicorn_kwargs_uses_declared_host_and_port() -> None:
    kwargs = build_uvicorn_kwargs(_settings(server_host="0.0.0.0", server_port=9000))  # noqa: S104 — value under test, never bound
    assert kwargs["host"] == "0.0.0.0"  # noqa: S104 — value under test, never bound
    assert kwargs["port"] == 9000


@pytest.mark.unit
def test_build_uvicorn_kwargs_carries_declared_concurrency_limit() -> None:
    """Preserves the current, uncalibrated default rather than silently changing it."""
    kwargs = build_uvicorn_kwargs(_settings())
    assert kwargs["limit_concurrency"] == 100
