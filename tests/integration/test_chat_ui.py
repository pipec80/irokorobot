"""Integration tests for the local diagnostic chat user interface."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from server.chat_ui import mount_chat_ui
from server.main import app

_CLIENT = TestClient(app)


@pytest.mark.integration
@pytest.mark.parametrize(
    "path,media_type",
    [
        ("/chat-ui/", "text/html"),
        ("/chat-ui/chat.css", "text/css"),
        ("/chat-ui/chat.js", "text/javascript"),
    ],
)
def test_chat_ui_serves_local_assets(path: str, media_type: str) -> None:
    """The diagnostic UI should serve its three package-local assets."""
    response = _CLIENT.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(media_type)


@pytest.mark.integration
def test_chat_ui_shell_is_same_origin_and_accessible() -> None:
    """The HTML shell should expose safe, accessible diagnostic regions."""
    html = _CLIENT.get("/chat-ui/").text

    assert "default-src 'self'" in html
    assert "connect-src 'self'" in html
    assert 'href="chat.css"' in html
    assert 'src="chat.js"' in html
    assert 'id="chat-form"' in html
    assert 'id="transcript"' in html
    assert 'id="conversation-id"' in html
    assert 'id="new-conversation"' in html
    assert 'role="status"' in html
    assert 'role="alert"' in html
    assert "https://" not in html
    assert "http://" not in html


@pytest.mark.integration
def test_chat_ui_mount_does_not_change_openapi_contract() -> None:
    """Static UI routes should stay outside OpenAPI while chat remains present."""
    paths = _CLIENT.get("/openapi.json").json()["paths"]

    assert "/chat" in paths
    assert all(not path.startswith("/chat-ui") for path in paths)


@pytest.mark.integration
def test_frontend_serving_lets_an_api_route_win_over_a_static_asset() -> None:
    """An API path operation must win over a same-path frontend asset,
    regardless of registration order (Plan 0044 Task 1) — a manual
    `app.mount(StaticFiles(...))` does not guarantee this; `app.frontend()`
    does. `/chat-ui/chat.css` is a real static asset; this proves a path
    operation declared after the frontend mount still wins that exact path.
    """
    test_app = FastAPI()
    mount_chat_ui(test_app)

    @test_app.get("/chat-ui/chat.css")
    def _api_route_sharing_the_static_path() -> dict[str, str]:
        return {"api": "wins"}

    response = TestClient(test_app).get("/chat-ui/chat.css")

    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"api": "wins"}


@pytest.mark.integration
def test_chat_ui_script_uses_isolated_safe_chat_contract() -> None:
    """The browser client should use only the safe text conversation boundary."""
    script = _CLIENT.get("/chat-ui/chat.js").text

    assert 'const CHAT_ENDPOINT = "/chat"' in script
    assert "fetch(CHAT_ENDPOINT" in script
    assert "sessionStorage" in script
    assert "crypto.randomUUID()" in script
    assert ".textContent" in script
    assert "JSON.stringify" in script
    assert "message," in script
    assert "conversation_id:" in script
    assert "innerHTML" not in script
    assert "localStorage" not in script
    assert "/transcribe" not in script
    assert "/stt" not in script.lower()
    assert "/tts" not in script.lower()
    assert "/vision" not in script.lower()
