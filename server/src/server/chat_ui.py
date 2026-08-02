"""Local static user interface for diagnostic text conversations."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

_CHAT_UI_DIRECTORY = Path(__file__).parent / "static" / "chat"


def mount_chat_ui(app: FastAPI) -> None:
    """Mount the package-local diagnostic chat assets.

    Args:
        app: FastAPI application that owns the local chat endpoint.
    """
    app.mount(
        "/chat-ui",
        StaticFiles(directory=_CHAT_UI_DIRECTORY, html=True),
        name="chat-ui",
    )
