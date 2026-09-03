"""FastAPI application entrypoint — assembles routers and starts the server."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging
import logging.config
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.body_limit import RequestBodyLimitMiddleware
import uvicorn

from server import stt, tts
from server.chat_ui import mount_chat_ui
from server.db import close_db, open_db, run_migrations
from server.logging_setup import build_file_handler
from server.memory import retention
from server.request_context import RequestContextMiddleware, RequestIdFilter
from server.routers import auth, chat, system, transcribe, vision
from server.settings import Settings, settings

_LOG_HANDLERS: dict[str, Any] = {
    "console": {
        "class": "logging.StreamHandler",
        "formatter": "default",
        "filters": ["request_id"],
    },
}
_ROOT_HANDLER_NAMES = ["console"]

if settings.log_to_file:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    # JSON Lines on disk for analysis tools; the console stays human-readable.
    _LOG_HANDLERS["file"] = {
        "()": build_file_handler,
        "path": settings.log_dir / "server.log",
        "retention_days": settings.log_retention_days,
        "filters": ["request_id"],
    }
    _ROOT_HANDLER_NAMES.append("file")

# logging.config.dictConfig requires dict[str, Any] — no precise type exists for this schema
_LOG_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": RequestIdFilter}},
    "formatters": {
        "default": {
            "format": "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s — %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": _LOG_HANDLERS,
    "root": {"handlers": _ROOT_HANDLER_NAMES, "level": settings.log_level.upper()},
    "loggers": {
        "uvicorn": {"propagate": True},
        "uvicorn.access": {"propagate": True},
        "uvicorn.error": {"propagate": True},
    },
}

logging.config.dictConfig(_LOG_CONFIG)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Load ML models and optionally initialize the brain memory subsystem."""
    if settings.uvicorn_workers != 1:
        raise RuntimeError(
            "Owner unlock grants are process-local: UVICORN_WORKERS must be 1, "
            f"got {settings.uvicorn_workers}."
        )
    logger.info("OMNiBot 2000 starting — loading models...")
    stt.preload()
    tts.preload()

    if settings.memory_enabled:
        await open_db()
        await run_migrations()
        retention.start_background_job()
        logger.info("Brain memory enabled: %s", settings.brain_db_path)
    else:
        logger.info("Memory disabled via MEMORY_ENABLED")

    logger.info(
        "OMNiBot server ONLINE ✅ — listening on http://%s:%d "
        "| health: GET /health | memory: %s | LLM: %s",
        settings.server_host,
        settings.server_port,
        "on" if settings.memory_enabled else "off",
        settings.llm_provider,
    )
    yield

    if settings.memory_enabled:
        await retention.stop_background_job()
        await close_db()
        logger.info("Brain memory closed.")

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


app = FastAPI(
    title="OMNiBot 2000 Core API",
    description=(
        "Core API of the robotic brain. Handles perception (Audio/Vision), "
        "semantic memory, and LLM inference."
    ),
    version="0.2.0",
    lifespan=lifespan,
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
# `FastAPI(...)` does not accept `max_body_size` — only `Starlette.__init__`
# does (Plan 0034) — so the raw ceiling is a middleware, not a constructor
# argument. It rejects a body over budget before any router or multipart
# parsing runs, which matters because a field the app never reads (an
# optional frame with face auth disabled) would otherwise never be sized at
# all: `_read_optional_frame` simply never executes for it.
app.add_middleware(RequestBodyLimitMiddleware, max_body_size=settings.max_request_body_bytes)
# Added last so it wraps everything above, including the body-limit
# middleware: the correlation id must be stamped even on a 413, and the
# context must cover the whole request.
app.add_middleware(RequestContextMiddleware)
app.add_exception_handler(RequestValidationError, _validation_error_without_input)  # type: ignore[arg-type]  # FastAPI narrows the handler's exception type

app.include_router(system.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(transcribe.router)
app.include_router(vision.router)
mount_chat_ui(app)


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
