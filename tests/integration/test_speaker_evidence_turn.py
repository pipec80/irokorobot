"""The speaker resolver is inert with the flag off and produces untrusted
evidence with it on (Plan 0053, Task 6).

Mirrors `tests/integration/test_face_authenticated_turn.py`'s fixtures and
`_client()` helper. `VOICE` evidence never identifies the actor —
`_RESOLVABLE_SOURCES` is unedited — so even a positively-verified speaker
match must still deny a protected question without a PIN or a face.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import io
from pathlib import Path
import subprocess
import sys
from unittest.mock import AsyncMock
from uuid import uuid4
import wave

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
import numpy as np
from pydantic import SecretStr
import pytest
from server.cognition import speaker_authentication as speaker_auth_module
from server.cognition.identity import HouseholdRole, IdentityEvidenceSource
from server.cognition.models import CognitiveEvent
from server.cognition.owner_authentication import owner_unlock_service
from server.cognition.response_plan import TextTurnPayload
from server.main import app
from server.memory.household_authorization import get_active_role, revoke_active_role
from server.memory.voice_consent import grant_voice_consent
from server.personal_setup import PersonalSetupInput, PersonalSetupResult, apply_personal_setup
from server.resources import AppResources
from server.settings import settings
from server.voice.speaker_embedding import SpeakerBackendError, model_id as _speaker_model_id
from server.voice.voiceprints import enroll_voiceprint

from server import db, llm, stt, tts

_CHILD_QUESTION = "¿Quienes son mis hijos?"
_PIN = "482173"
_OWNER_NAME = "Pipec"


@pytest.fixture
async def turn_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[PersonalSetupResult]:
    """Open a fresh temp DB with the north-star owner/children/PIN setup applied."""
    db_path = tmp_path / "speaker-evidence-turn.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    result = await apply_personal_setup(
        PersonalSetupInput(
            owner_name=_OWNER_NAME,
            child_names=("Joaquin", "Martina"),
            pin=SecretStr(_PIN),
        )
    )
    yield result
    await db.close_db()
    db._conn = None


async def _enroll_speaker(owner_entity_id: int) -> None:
    """Grant voice consent and store 3 real, distinct references for the owner."""
    await grant_voice_consent(owner_entity_id)
    for axis in range(3):
        vector = np.zeros(192, dtype=np.float32)
        vector[axis] = 1.0
        await enroll_voiceprint(owner_entity_id, vector, _OWNER_NAME, _speaker_model_id())


def _matching_probe() -> np.ndarray:
    """A 192-d vector matching one of `_enroll_speaker`'s references exactly."""
    probe = np.zeros(192, dtype=np.float32)
    probe[0] = 1.0
    return probe


@asynccontextmanager
async def _client() -> AsyncIterator[AsyncClient]:
    """Yield an async client without running application lifespan.

    Plan 0039: routers depend on `request.app.state.resources`
    (`ResourcesDep`), which the real lifespan sets — assign a lightweight
    `AppResources` here since that lifespan never runs in this helper.
    """
    async with AsyncClient() as http_client:
        app.state.resources = AppResources(
            http_client=http_client, owner_unlock_service=owner_unlock_service
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


def _mock_stt_tts(monkeypatch: pytest.MonkeyPatch, *, text: str) -> None:
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value=text))
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("AAAA", 42)))


def _tone_wav(seconds: float = 3.0, amplitude: int = 8_000) -> bytes:
    """A deterministic synthetic 'utterance' — never a human recording.

    Loud and long enough to clear both `has_voiced_energy` and
    `meets_verification_duration` for real, unlike `silence_wav_bytes`.
    """
    t = np.linspace(0.0, seconds, int(16_000 * seconds), endpoint=False)
    samples = (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(samples.tobytes())
    return buffer.getvalue()


def test_flag_off_never_imports_the_backend(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, silence_wav_bytes: bytes
) -> None:
    """With the default settings, torch must not be imported by a turn."""
    monkeypatch.setattr(settings, "speaker_authentication_enabled", False)
    monkeypatch.delitem(sys.modules, "torch", raising=False)
    client.post("/transcribe", files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")})
    assert "torch" not in sys.modules


@pytest.mark.integration
def test_flag_off_leaves_the_response_shape_unchanged(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the flag off (default), the response carries exactly the pre-0053 fields."""
    monkeypatch.setattr(settings, "speaker_authentication_enabled", False)
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value="hola"))
    monkeypatch.setattr(llm, "generate_response", AsyncMock(return_value=("hola", "joy")))
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("QQ==", 42)))

    response = client.post(
        "/transcribe",
        files={"audio": ("ok.wav", _tone_wav(), "audio/wav")},
    )

    assert response.status_code == 200
    assert set(response.json()) == {
        "text_heard",
        "llm_response",
        "audio_base64",
        "duration_ms",
        "emotion",
        "vision_requested",
        "stt_ms",
        "llm_ms",
        "tts_ms",
        "total_ms",
        "authentication_consumed",
        "identity_source",
    }


@pytest.mark.integration
async def test_flag_on_still_denies_a_protected_question_without_pin_or_face(
    turn_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even a positively-verified speaker match cannot disclose — VOICE is
    unresolvable by construction (`_RESOLVABLE_SOURCES` is unedited)."""
    monkeypatch.setattr(settings, "speaker_authentication_enabled", True)
    await _enroll_speaker(turn_db.owner_entity_id)
    monkeypatch.setattr(speaker_auth_module, "embed_wav", AsyncMock(return_value=_matching_probe()))
    _mock_stt_tts(monkeypatch, text=_CHILD_QUESTION)

    async with _client() as client:
        response = await client.post(
            "/transcribe", files={"audio": ("clip.wav", _tone_wav(), "audio/wav")}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["authentication_consumed"] is False
    assert body["identity_source"] is None
    assert "Joaquin" not in body["llm_response"]
    assert "Martina" not in body["llm_response"]


@pytest.mark.integration
async def test_flag_on_reads_the_audio_exactly_once(
    turn_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-6: at most one embedding per request, even though the controller can
    call the actor resolver more than once while deciding a protected turn."""
    monkeypatch.setattr(settings, "speaker_authentication_enabled", True)
    await _enroll_speaker(turn_db.owner_entity_id)
    embed = AsyncMock(return_value=_matching_probe())
    monkeypatch.setattr(speaker_auth_module, "embed_wav", embed)
    _mock_stt_tts(monkeypatch, text=_CHILD_QUESTION)

    async with _client() as client:
        response = await client.post(
            "/transcribe", files={"audio": ("clip.wav", _tone_wav(), "audio/wav")}
        )

    assert response.status_code == 200
    embed.assert_awaited_once()


@pytest.mark.integration
async def test_a_backend_failure_does_not_fail_the_turn(
    turn_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dead speaker backend degrades to no evidence — the turn still completes."""
    monkeypatch.setattr(settings, "speaker_authentication_enabled", True)
    await _enroll_speaker(turn_db.owner_entity_id)
    monkeypatch.setattr(
        speaker_auth_module,
        "embed_wav",
        AsyncMock(side_effect=SpeakerBackendError("model unavailable")),
    )
    _mock_stt_tts(monkeypatch, text=_CHILD_QUESTION)

    async with _client() as client:
        response = await client.post(
            "/transcribe", files={"audio": ("clip.wav", _tone_wav(), "audio/wav")}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["authentication_consumed"] is False
    assert body["identity_source"] is None


@pytest.mark.integration
async def test_flag_on_stream_route_consults_the_speaker_once(
    turn_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review I-3: the wiring was duplicated in the streaming route and untested there."""
    monkeypatch.setattr(settings, "speaker_authentication_enabled", True)
    await _enroll_speaker(turn_db.owner_entity_id)
    embed = AsyncMock(return_value=_matching_probe())
    monkeypatch.setattr(speaker_auth_module, "embed_wav", embed)
    _mock_stt_tts(monkeypatch, text=_CHILD_QUESTION)

    async with _client() as client:
        response = await client.post(
            "/transcribe/stream", files={"audio": ("clip.wav", _tone_wav(), "audio/wav")}
        )

    assert response.status_code == 200
    embed.assert_awaited_once()
    assert "Joaquin" not in response.text
    assert "Martina" not in response.text


def _event() -> CognitiveEvent[TextTurnPayload]:
    now = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    return CognitiveEvent(
        event_id=uuid4(),
        schema_version=1,
        event_type="text.turn",
        occurred_at=now,
        recorded_at=now,
        source="audio.transcribe",
        correlation_id=uuid4(),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message="canary", conversation_id="canary-scope"),
    )


@pytest.mark.integration
async def test_a_role_change_takes_effect_on_the_next_turn(
    turn_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review Focus 5 / M-7: real DB, real `get_active_role`, real default wiring."""
    monkeypatch.setattr(speaker_auth_module, "embed_wav", AsyncMock(return_value=_matching_probe()))
    await _enroll_speaker(turn_db.owner_entity_id)
    owner = turn_db.owner_entity_id
    assert await get_active_role(owner) is HouseholdRole.OWNER

    before = await speaker_auth_module.build_default_speaker_resolver(
        _tone_wav(), owner
    ).resolve_actor(_event())
    await revoke_active_role(person_entity_id=owner)
    after = await speaker_auth_module.build_default_speaker_resolver(
        _tone_wav(), owner
    ).resolve_actor(_event())

    assert [item.source for item in before.evidence] == [IdentityEvidenceSource.VOICE]
    assert after.evidence == ()


def test_importing_the_app_never_loads_the_speaker_stack() -> None:
    """Review M-7: prove the lazy imports in a clean interpreter, not via `sys.modules`.

    Deleting `torch` from `sys.modules` in-process says nothing about whether a
    fresh server with the flag off would load it; a subprocess does.
    """
    code = (
        "import sys; import server.main, server.routers.transcribe, server.routers.auth; "
        "bad = [m for m in ('torch', 'torchaudio', 'speechbrain') if m in sys.modules]; "
        "sys.exit(1 if bad else 0)"
    )
    result = subprocess.run(  # noqa: S603 -- fixed argv, no user input
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
