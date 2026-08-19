"""FastAPI application entrypoint — assembles routers and starts the server."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging
import logging.config
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
import uvicorn

from server import stt, tts
from server.chat_ui import mount_chat_ui
from server.db import close_db, open_db, run_migrations
from server.logging_setup import build_file_handler
from server.memory import retention
from server.routers import chat, system, transcribe, vision
from server.settings import settings

_LOG_HANDLERS: dict[str, Any] = {
    "console": {
        "class": "logging.StreamHandler",
        "formatter": "default",
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
    }
    _ROOT_HANDLER_NAMES.append("file")

# logging.config.dictConfig requires dict[str, Any] — no precise type exists for this schema
_LOG_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s %(levelname)-8s %(name)s — %(message)s",
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

app.include_router(system.router)
app.include_router(chat.router)
app.include_router(transcribe.router)
app.include_router(vision.router)
mount_chat_ui(app)


def main() -> None:
    """Entry point for the serve script."""
    uvicorn.run(
        "server.main:app",
        host=settings.server_host,
        port=settings.server_port,
        log_config=None,  # logging already configured via dictConfig above
        workers=settings.uvicorn_workers,
        reload=False,
        proxy_headers=settings.uvicorn_proxy_headers,
        server_header=False,
        limit_concurrency=settings.uvicorn_limit_concurrency,
        limit_max_requests=settings.uvicorn_max_requests,
        timeout_keep_alive=5,
    )
