"""Robot settings loaded from environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Robot settings from environment variables."""

    server_url: str = "http://localhost:8000"
    # Full STT→LLM→TTS pipeline can exceed 30s on CPU-only Ollama backends;
    # generous default so the robot outlasts the brain's slowest turn.
    server_timeout_s: float = 120.0
    # "silero" (neural, needs vad_model_path) or "rms" (energy threshold).
    # Silero load failures degrade to RMS automatically — see robot.vad.
    vad_engine: str = "silero"
    vad_silence_threshold_rms: int = 100
    vad_preroll_ms: int = 400
    vad_silence_ms: int = 800
    # Not vendored in git (see .gitignore *.onnx) — fetch with
    # scripts/fetch_silero_vad_model.py before enabling vad_engine=silero.
    vad_model_path: Path = Path("models/silero_vad.onnx")
    log_level: str = "INFO"
    log_to_file: bool = True
    log_dir: Path = Path("logs")
    log_retention_days: int = 14
    # R3: use POST /transcribe/stream + sentence-by-sentence playback instead
    # of the classic single-shot /transcribe. Default off — opt-in per robot
    # until validated on real hardware.
    robot_streaming: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()  # pyright: ignore[reportCallIssue]
