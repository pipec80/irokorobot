"""HTTP client to the OMNiBot server API."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
import json
import logging

import httpx

from robot.exceptions import NoSpeechError, ServerError
from robot.settings import settings
from robot.stream_events import StreamEvent, parse_stream_event

logger = logging.getLogger(__name__)

# The server answers 422 when Whisper finds no speech in the audio.
_HTTP_NO_SPEECH = 422
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Return the shared AsyncClient, creating it on first use.

    Reusing one client enables connection pooling — the robot talks to a
    single server for its whole lifetime.
    """
    global _client  # noqa: PLW0603
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=settings.server_timeout_s)
    return _client


async def close_client() -> None:
    """Close the shared HTTP client. Idempotent — safe to call at shutdown."""
    global _client  # noqa: PLW0603
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


@dataclass(frozen=True)
class TranscribeResult:
    """Parsed response from POST /transcribe or /vision/respond."""

    text_heard: str
    llm_response: str
    audio_base64: str
    duration_ms: int
    emotion: str
    # Server wants ONE camera frame — capture and call respond_vision().
    # Generic protocol flag: the robot does not know WHY the server looks.
    vision_requested: bool = False


def _parse_result(data: dict[str, object]) -> TranscribeResult:
    """Build a TranscribeResult from a response body.

    Known fields only — the API contract allows the server to ADD fields
    at any time, and unknown kwargs would crash the dataclass.
    """
    return TranscribeResult(
        text_heard=str(data["text_heard"]),
        llm_response=str(data["llm_response"]),
        audio_base64=str(data["audio_base64"]),
        duration_ms=int(data["duration_ms"]),  # type: ignore[call-overload]  # contract: int
        emotion=str(data.get("emotion", "neutral")),
        vision_requested=bool(data.get("vision_requested", False)),
    )


async def transcribe(audio: bytes) -> TranscribeResult:
    """Send audio to the server and return the transcription result.

    Args:
        audio: Raw WAV bytes at 16kHz mono int16.

    Returns:
        TranscribeResult with all pipeline outputs.

    Raises:
        NoSpeechError: If the server found no speech in the audio (HTTP 422).
        ServerError: If the server returns any other non-200 response.
        ValueError: If audio is empty.
    """
    if not audio:
        raise ValueError("Audio bytes are empty")
    client = _get_client()
    try:
        response = await client.post(
            f"{settings.server_url}/transcribe",
            files={"audio": ("audio.wav", audio, "audio/wav")},
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == _HTTP_NO_SPEECH:
            raise NoSpeechError("Server heard no speech in the audio") from exc
        raise ServerError(f"Server returned {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise ServerError("Could not reach server") from exc
    data = response.json()
    logger.info("Server response: %s", data.get("text_heard", ""))
    return _parse_result(data)


async def check_vision_enabled() -> bool:
    """Ask GET /health whether the server has vision (VLM) enabled.

    Used only at robot startup when ``settings.robot_streaming`` is True, to
    guard against the unsupported streaming + vision combination (F-08 in
    docs/c-audit/auditoria-forense-codigo-2026-07-21.md) — the robot asks the
    API it already calls instead of reading the server's own settings, which
    would cross the client/server boundary.

    Returns:
        True if the server reports ``vision_enabled``. Missing field (older
        server) is treated as False.

    Raises:
        ServerError: If the server is unreachable or returns non-200.
    """
    client = _get_client()
    try:
        response = await client.get(f"{settings.server_url}/health")
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ServerError(f"Server returned {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise ServerError("Could not reach server") from exc
    return bool(response.json().get("vision_enabled", False))


async def respond_vision(text: str, image: bytes) -> TranscribeResult:
    """Send a camera frame plus the visual question to /vision/respond.

    Second round of a vision turn: the /transcribe response carried
    ``vision_requested=True``, so the robot captured ONE frame and asks
    the server to answer the question with it.

    Args:
        text: The transcribed question the server asked a frame for.
        image: JPEG bytes — contract: max 1280x720 · quality 85 · one frame.

    Returns:
        TranscribeResult with the spoken answer.

    Raises:
        ServerError: If the server is unreachable or returns non-200.
        ValueError: If image or text is empty.
    """
    if not image:
        raise ValueError("Image bytes are empty")
    if not text.strip():
        raise ValueError("Question text is empty")
    client = _get_client()
    try:
        response = await client.post(
            f"{settings.server_url}/vision/respond",
            files={"image": ("frame.jpg", image, "image/jpeg")},
            data={"text": text},
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ServerError(f"Server returned {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise ServerError("Could not reach server") from exc
    return _parse_result(response.json())


async def transcribe_stream(audio: bytes) -> AsyncIterator[StreamEvent]:
    """Send audio to POST /transcribe/stream and yield NDJSON events (R3).

    Behind ``settings.robot_streaming`` — the classic ``transcribe()`` above
    is unaffected. Since this is an async generator, validation errors
    surface on the first iteration rather than immediately on call, same as
    any other async-generator API.

    Args:
        audio: Raw WAV bytes at 16kHz mono int16.

    Yields:
        Parsed StreamEvent variants in server order: text_heard, emotion,
        audio (one per sentence), then done.

    Raises:
        NoSpeechError: If the server found no speech in the audio (HTTP 422).
        ServerError: If the server returns any other non-200 response, the
            connection fails, or a line does not parse as a known event.
        ValueError: If audio is empty.
    """
    if not audio:
        raise ValueError("Audio bytes are empty")
    client = _get_client()
    try:
        async with client.stream(
            "POST",
            f"{settings.server_url}/transcribe/stream",
            files={"audio": ("audio.wav", audio, "audio/wav")},
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                try:
                    yield parse_stream_event(json.loads(line))
                except (json.JSONDecodeError, ValueError, KeyError) as exc:
                    raise ServerError(f"Malformed stream event: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == _HTTP_NO_SPEECH:
            raise NoSpeechError("Server heard no speech in the audio") from exc
        raise ServerError(f"Server returned {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise ServerError("Could not reach server") from exc
