"""FastAPI application entrypoint — assembles routers and starts the server."""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
import httpx
from starlette.middleware.body_limit import RequestBodyLimitMiddleware
import uvicorn

from server import stt, tts
from server.chat_ui import mount_chat_ui
from server.cognition.owner_authentication import owner_unlock_service
from server.db import close_db, open_db, run_migrations
from server.logging_setup import configure_logging
from server.memory import retention
from server.request_context import RequestContextMiddleware
from server.resources import AppResources
from server.routers import auth, chat, system, transcribe, vision
from server.settings import Settings, settings

logger = logging.getLogger(__name__)

# General-purpose bound for the lifecycle-owned client — Ollama calls that
# need longer than this override the read timeout per request (see
# llm_transport.py); nothing else this client is used for should ever take
# this long.
_HTTP_CLIENT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)
_HTTP_CLIENT_LIMITS = httpx.Limits(max_connections=10, max_keepalive_connections=5)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Own every long-lived resource for exactly one request-serving period.

    Resources are entered in acquisition order through one `AsyncExitStack`,
    so a failure partway through startup (e.g. TTS preload after the HTTP
    client already opened) still unwinds everything already acquired, in
    reverse order — nothing leaks on a partial failure. `_app.state.ready`
    is `True` only between a fully successful startup and the start of
    shutdown; `_app.state.resources` exists as soon as the HTTP client does,
    even if a later startup step then fails.
    """
    if settings.uvicorn_workers != 1:
        raise RuntimeError(
            "Owner unlock grants are process-local: UVICORN_WORKERS must be 1, "
            f"got {settings.uvicorn_workers}."
        )
    logger.info("OMNiBot 2000 starting — loading models...")

    async with AsyncExitStack() as stack:
        http_client = await stack.enter_async_context(
            httpx.AsyncClient(timeout=_HTTP_CLIENT_TIMEOUT, limits=_HTTP_CLIENT_LIMITS)
        )
        _app.state.resources = AppResources(
            http_client=http_client,
            owner_unlock_service=owner_unlock_service,
        )

        stt.preload()
        tts.preload()

        if settings.memory_enabled:
            await open_db()
            stack.push_async_callback(close_db)
            await run_migrations()
            retention.start_background_job()
            stack.push_async_callback(retention.stop_background_job)
            logger.info("Brain memory enabled: %s", settings.brain_db_path)
        else:
            logger.info("Memory disabled via MEMORY_ENABLED")

        _app.state.ready = True
        logger.info(
            "OMNiBot server ONLINE ✅ — listening on http://%s:%d "
            "| health: GET /health | memory: %s | LLM: %s",
            settings.server_host,
            settings.server_port,
            "on" if settings.memory_enabled else "off",
            settings.llm_provider,
        )
        yield
        _app.state.ready = False
        logger.info("OMNiBot 2000 shutting down.")


async def _validation_error_without_input(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return a 422 that names the broken rule but never echoes the value.

    FastAPI's default validation body includes an ``input`` field carrying the
    rejected value verbatim. For `POST /auth/owner/unlock` that value is a
    candidate PIN, so the default response would hand a credential back to the
    caller and into any proxy log. The rule and its location are enough for a
    client to fix its request (Plan 0033).

    Args:
        _request: Unused; the handler never inspects the request.
        exc: The validation error raised while parsing the request body.

    Returns:
        A 422 whose errors keep ``type``, ``loc`` and ``msg`` only.
    """
    redacted = [
        {key: value for key, value in error.items() if key in {"type", "loc", "msg"}}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": redacted})


def create_app() -> FastAPI:
    """Compose the FastAPI application: logging, middleware, routers, lifespan.

    Configuring logging is the first thing this does, and only this does —
    importing `server.main` alone must not create a log directory or any
    other side effect (Plan 0039); only calling `create_app()` does.

    Returns:
        A fully assembled, not-yet-started `FastAPI` instance. Resource
        construction (the HTTP client, DB, background jobs) is the
        lifespan's job, not this factory's — building the app object never
        opens a resource.
    """
    configure_logging(settings)

    new_app = FastAPI(
        title="OMNiBot 2000 Core API",
        description=(
            "Core API of the robotic brain. Handles perception (Audio/Vision), "
            "semantic memory, and LLM inference."
        ),
        version="0.2.0",
        lifespan=lifespan,
    )
    new_app.add_middleware(GZipMiddleware, minimum_size=1000)
    # `FastAPI(...)` does not accept `max_body_size` — only `Starlette.__init__`
    # does (Plan 0034) — so the raw ceiling is a middleware, not a constructor
    # argument. It rejects a body over budget before any router or multipart
    # parsing runs, which matters because a field the app never reads (an
    # optional frame with face auth disabled) would otherwise never be sized at
    # all: `_read_optional_frame` simply never executes for it.
    new_app.add_middleware(
        RequestBodyLimitMiddleware, max_body_size=settings.max_request_body_bytes
    )
    # Added last so it wraps everything above, including the body-limit
    # middleware: the correlation id must be stamped even on a 413, and the
    # context must cover the whole request.
    new_app.add_middleware(RequestContextMiddleware)
    new_app.add_exception_handler(RequestValidationError, _validation_error_without_input)  # type: ignore[arg-type]  # FastAPI narrows the handler's exception type

    new_app.include_router(system.router)
    new_app.include_router(auth.router)
    new_app.include_router(chat.router)
    new_app.include_router(transcribe.router)
    new_app.include_router(vision.router)
    mount_chat_ui(new_app)
    return new_app


app = create_app()


def build_uvicorn_kwargs(runtime_settings: Settings) -> dict[str, object]:
    """Build the exact Uvicorn runtime flags from typed settings (Plan 0038).

    A pure function, not inline kwargs on `uvicorn.run()`, so the runtime's
    actual flags are a value that tests can construct and inspect directly —
    reload, proxy trust, and the request-recycling ceiling are safety
    invariants, not incidental config.

    Args:
        runtime_settings: The settings instance to read runtime flags from.

    Returns:
        Keyword arguments for `uvicorn.run()` — everything except the ASGI
        app import string, which is the caller's own concern.
    """
    return {
        "host": runtime_settings.server_host,
        "port": runtime_settings.server_port,
        "log_config": None,  # logging already configured via dictConfig above
        "workers": runtime_settings.uvicorn_workers,
        "reload": False,
        "proxy_headers": runtime_settings.uvicorn_proxy_headers,
        "server_header": False,
        # RequestContextMiddleware (Plan 0032) already logs every request
        # with timing and a correlation id — Uvicorn's own access log would
        # just duplicate it.
        "access_log": False,
        "limit_concurrency": runtime_settings.uvicorn_limit_concurrency,
        "limit_max_requests": runtime_settings.uvicorn_max_requests,
        "timeout_keep_alive": runtime_settings.uvicorn_timeout_keep_alive,
        "timeout_graceful_shutdown": runtime_settings.uvicorn_timeout_graceful_shutdown,
    }


def main() -> None:
    """Entry point for the serve script."""
    uvicorn.run(
        "server.main:app",
        **build_uvicorn_kwargs(settings),  # type: ignore[arg-type]  # dict[str, object] can't statically match uvicorn.run's heterogeneous **kwargs; build_uvicorn_kwargs itself is unit-tested directly
    )
