"""Unit tests for server.settings and robot.settings."""

from pathlib import Path

from pydantic import ValidationError
import pytest
from robot.settings import Settings as RobotSettings
from server.settings import Settings as ServerSettings


@pytest.mark.unit
def test_server_settings_defaults_match_audio_contract() -> None:
    """Defaults must align with the documented audio contract and deploy target."""
    settings = ServerSettings(_env_file=None)  # type: ignore[call-arg]
    assert settings.whisper_model == "small"
    assert settings.whisper_language == "es"
    assert settings.whisper_compute_type == "int8"
    assert settings.whisper_device == "cpu"
    assert settings.piper_voice == "es_MX-ald-medium"
    assert settings.piper_use_cuda is False
    assert settings.models_dir == Path("models")
    assert settings.server_host == "127.0.0.1"
    assert settings.server_port == 8000
    assert settings.max_audio_upload_bytes == 10 * 1024 * 1024
    assert settings.max_image_upload_bytes == 5 * 1024 * 1024
    assert settings.max_audio_duration_s == 30.0


@pytest.mark.unit
def test_server_settings_llm_provider_default() -> None:
    settings = ServerSettings(_env_file=None)  # type: ignore[call-arg]
    assert settings.llm_provider == "ollama"


@pytest.mark.unit
def test_server_settings_rejects_nonlocal_llm_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cloud provider value must fail validation instead of selecting a fallback."""
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")

    with pytest.raises(ValidationError, match="llm_provider"):
        ServerSettings(_env_file=None)  # type: ignore[call-arg]


@pytest.mark.unit
def test_server_settings_reads_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    lan_host = ".".join(("0", "0", "0", "0"))
    monkeypatch.setenv("WHISPER_MODEL", "tiny")
    monkeypatch.setenv("PIPER_SPEED", "2.0")
    monkeypatch.setenv("SERVER_PORT", "9000")
    monkeypatch.setenv("SERVER_HOST", lan_host)
    settings = ServerSettings(_env_file=None)  # type: ignore[call-arg]
    assert settings.whisper_model == "tiny"
    assert settings.piper_speed == 2.0
    assert settings.server_port == 9000
    assert settings.server_host == lan_host


@pytest.mark.unit
def test_server_settings_ignores_unknown_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """extra='ignore' must let unrelated env vars pass without error."""
    monkeypatch.setenv("SOMETHING_COMPLETELY_UNRELATED", "hello")
    settings = ServerSettings(_env_file=None)  # type: ignore[call-arg]
    assert not hasattr(settings, "something_completely_unrelated")


@pytest.mark.unit
def test_server_settings_rejects_multiple_workers() -> None:
    """Owner-unlock grants are process-local (Plan 0038) — reject at construction."""
    with pytest.raises(ValidationError, match="uvicorn_workers"):
        ServerSettings(_env_file=None, uvicorn_workers=2)  # type: ignore[call-arg]


@pytest.mark.unit
def test_server_settings_max_requests_defaults_to_unset() -> None:
    """The server must not self-terminate after a fixed request count by default."""
    settings = ServerSettings(_env_file=None)  # type: ignore[call-arg]
    assert settings.uvicorn_max_requests is None


@pytest.mark.unit
@pytest.mark.parametrize("port", [0, -1, 65536])
def test_server_settings_rejects_out_of_range_port(port: int) -> None:
    with pytest.raises(ValidationError, match="server_port"):
        ServerSettings(_env_file=None, server_port=port)  # type: ignore[call-arg]


@pytest.mark.unit
@pytest.mark.parametrize("value", [0, -1])
def test_server_settings_rejects_nonpositive_keep_alive_timeout(value: int) -> None:
    with pytest.raises(ValidationError, match="uvicorn_timeout_keep_alive"):
        ServerSettings(_env_file=None, uvicorn_timeout_keep_alive=value)  # type: ignore[call-arg]


@pytest.mark.unit
@pytest.mark.parametrize("value", [0, -1])
def test_server_settings_rejects_nonpositive_graceful_shutdown_timeout(value: int) -> None:
    with pytest.raises(ValidationError, match="uvicorn_timeout_graceful_shutdown"):
        ServerSettings(_env_file=None, uvicorn_timeout_graceful_shutdown=value)  # type: ignore[call-arg]


@pytest.mark.unit
def test_robot_settings_defaults() -> None:
    settings = RobotSettings(_env_file=None)  # type: ignore[call-arg]
    assert settings.server_url == "http://localhost:8000"
    assert settings.vad_engine == "silero"
    assert settings.vad_silence_threshold_rms == 100
    assert settings.vad_preroll_ms == 400
    assert settings.vad_silence_ms == 800
    assert settings.vad_model_path == Path("models/silero_vad.onnx")


@pytest.mark.unit
def test_robot_settings_reads_server_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVER_URL", "http://homelab:8000")
    settings = RobotSettings(_env_file=None)  # type: ignore[call-arg]
    assert settings.server_url == "http://homelab:8000"
