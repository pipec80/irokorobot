"""Console and file log formatting for the server process.

The console stays human-readable for an operator watching ``just run-server``.
The rotating file is JSON Lines — exactly one JSON object per line — so any
analysis system ingests it without a custom parser.

Rotated files keep the ``.log`` extension: ``server.2026-07-27.log`` instead of
the stdlib default ``server.log.2026-07-27``. Python's rotation cleanup
regenerates candidate names through this same namer, so daily retention keeps
working.
"""

from datetime import datetime
import json
import logging
import logging.config
import logging.handlers
from pathlib import Path
from typing import TYPE_CHECKING, Any

from server.request_context import RequestIdFilter

if TYPE_CHECKING:
    from server.settings import Settings

# Attributes every LogRecord already carries; anything else is a caller extra.
_RESERVED_RECORD_KEYS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class JsonLinesFormatter(logging.Formatter):
    """Render each record as one compact JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        """Return the record as a single JSON line.

        Args:
            record: Record emitted by any logger in this process.

        Returns:
            One JSON object carrying a timezone-aware ISO 8601 ``ts``, the
            level, the logger name, the message, every structured extra passed
            by the caller, and a formatted ``exc`` when an exception is logged.
        """
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created)
            .astimezone()
            .isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update(
            {
                key: value
                for key, value in record.__dict__.items()
                if key not in _RESERVED_RECORD_KEYS
            }
        )
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # default=str keeps an unexpected extra from breaking the whole line.
        return json.dumps(payload, ensure_ascii=False, default=str)


def rotated_log_name(default_name: str) -> str:
    """Move the rotation date before the extension.

    Args:
        default_name: Name the stdlib would use, e.g. ``logs/server.log.2026-07-27``.

    Returns:
        The same path as ``logs/server.2026-07-27.log``.
    """
    rotated = Path(default_name)
    base = Path(rotated.stem)
    return str(rotated.with_name(f"{base.stem}.{rotated.suffix.lstrip('.')}{base.suffix}"))


def configure_logging(settings: "Settings") -> None:
    """Apply the process's full logging configuration (Plan 0039).

    Explicit, not an import-time side effect: creating the log directory and
    calling `dictConfig` used to run as bare module-level statements in
    `main.py`, so merely importing `server.main` created `logs/` on disk even
    if the app never started. Callers (normally `create_app()`) invoke this
    once, deliberately.

    Args:
        settings: Application settings — reads `log_to_file`, `log_dir`,
            `log_retention_days`, and `log_level`.
    """
    handlers: dict[str, Any] = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "filters": ["request_id"],
        },
    }
    root_handler_names = ["console"]

    if settings.log_to_file:
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        # JSON Lines on disk for analysis tools; the console stays human-readable.
        handlers["file"] = {
            "()": build_file_handler,
            "path": settings.log_dir / "server.log",
            "retention_days": settings.log_retention_days,
            "filters": ["request_id"],
        }
        root_handler_names.append("file")

    # logging.config.dictConfig requires dict[str, Any] — no precise type exists for this schema
    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {"request_id": {"()": RequestIdFilter}},
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s — %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": handlers,
        "root": {"handlers": root_handler_names, "level": settings.log_level.upper()},
        "loggers": {
            "uvicorn": {"propagate": True},
            "uvicorn.access": {"propagate": True},
            "uvicorn.error": {"propagate": True},
        },
    }
    logging.config.dictConfig(config)


def build_file_handler(path: Path, retention_days: int) -> logging.Handler:
    """Create the daily-rotating JSON Lines file handler.

    Args:
        path: Active log file, e.g. ``logs/server.log``.
        retention_days: Rotated files kept before the oldest is deleted.

    Returns:
        A handler that rotates at midnight and writes UTF-8 JSON Lines.
    """
    handler = logging.handlers.TimedRotatingFileHandler(
        path,
        when="midnight",
        backupCount=retention_days,
        encoding="utf-8",
    )
    handler.namer = rotated_log_name
    handler.setFormatter(JsonLinesFormatter())
    return handler
