"""Local static user interface for diagnostic text conversations."""

from pathlib import Path

from fastapi import FastAPI

_CHAT_UI_DIRECTORY = Path(__file__).parent / "static" / "chat"


def mount_chat_ui(app: FastAPI) -> None:
    """Serve the package-local diagnostic chat assets as low-priority routes.

    Uses `app.frontend()` (Plan 0044) rather than a manual
    `StaticFiles` mount: FastAPI path operations are always checked first,
    and these frontend files only if no normal route matched — a guarantee
    a manual mount does not give regardless of registration order.

    Args:
        app: FastAPI application that owns the local chat endpoint.
    """
    app.frontend("/chat-ui", directory=_CHAT_UI_DIRECTORY)
