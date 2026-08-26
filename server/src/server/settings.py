"""Application settings loaded from environment variables."""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings from environment variables."""

    llm_provider: Literal["ollama"] = "ollama"
    # Spoken when the LLM backend is unreachable — TTS is local, so the
    # robot can always apologize out loud instead of going silent.
    llm_fallback_phrase: str = (
        "Uy, mi cerebro todavía se está despertando. Dame unos segundos y volvé a hablarme."
    )
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    # CPU-only chat calls reach 20+ s with a grown prompt (observed live
    # 2026-07-13); must comfortably exceed the slowest real turn.
    ollama_timeout_s: float = 120.0
    whisper_model: str = "small"
    whisper_language: str = "es"
    whisper_compute_type: str = "int8"
    whisper_device: str = "cpu"
    whisper_beam_size: int = 5
    whisper_initial_prompt: str = "Conversación con un robot doméstico llamado Iroko."
    whisper_hotwords: str | None = None
    whisper_hallucination_silence_threshold: float = 2.0
    whisper_vad_min_silence_ms: int = 500
    piper_voice: str = "es_MX-ald-medium"
    piper_speed: float = 1.4
    piper_noise_scale: float = 0.8
    piper_noise_w_scale: float = 0.8
    piper_use_cuda: bool = False
    models_dir: Path = Path("models")
    # Desktop development stays local by default. LAN deployments opt in via
    # SERVER_HOST=0.0.0.0 after their network policy is configured.
    server_host: str = "127.0.0.1"
    server_port: int = 8000
    log_level: str = "INFO"
    log_to_file: bool = True
    log_dir: Path = Path("logs")
    log_retention_days: int = 14
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB — well above any realistic utterance

    uvicorn_workers: int = 1
    uvicorn_proxy_headers: bool = False
    uvicorn_limit_concurrency: int = 100
    uvicorn_max_requests: int = 1000

    # ---------------- Brain & Memory ----------------
    brain_db_path: Path = Path("data/omnibot.db")

    embedding_model: str = "nomic-embed-text"

    consolidation_model: str = "qwen2.5:3b"

    working_memory_size: int = 20
    semantic_top_k: int = 6

    default_user_id: str = "pipec"
    memory_enabled: bool = True
    robot_character: str = "iroko"
    # Re-read character markdown profiles from disk on every request when
    # they change (prompt-engineering aid). OFF by default: production loads
    # each profile once and caches it, so behavior stays reproducible from a
    # commit. Turn ON only in a dev shell.
    character_hot_reload: bool = False

    # ---------------- Vision (V0) ----------------
    # Kill-switch, same pattern as memory_enabled — off by default.
    vision_enabled: bool = False
    # Instruct variant on purpose: thinking tags exceed every CPU timeout
    # (lesson from R8). Homelab production can raise to qwen3-vl:8b.
    vlm_model: str = "qwen3-vl:2b-instruct"
    # Spoken immediately when a visual question is detected — buys the VLM
    # its inference time without a silent robot (V0.5).
    vision_look_phrase: str = "A ver, déjame mirar..."
    # ---------------- Vision V1: faces ----------------
    face_model: str = "buffalo_l"
    # Cosine-DISTANCE upper bound for a face match (0 = identical face).
    # Default from doc 05 §3 — calibrate with the real family and record
    # the final value in the bitácora.
    face_match_threshold: float = 0.4
    # Separate, STRICTER threshold for owner authentication (Plan 0029): a
    # face allowed to unlock protected data must clear a tighter bound than
    # the generic conversational recognition above — never repurpose
    # face_match_threshold for authentication decisions.
    face_authentication_match_threshold: float = 0.25
    # Master on/off for in-request face authentication (Plan 0029, Task 5):
    # gates whether /transcribe and /transcribe/stream will ever attempt to
    # build a face resolver from an attached frame. Off by default — a
    # frame field stays present but completely inert until enabled.
    face_authentication_enabled: bool = False
    # Enrollment quality gates: a blurry or tiny face makes a bad profile
    # that mismatches forever — reject it upfront with a clear reason.
    face_enroll_min_score: float = 0.5
    face_enroll_min_width: int = 80
    # Drop-folder for enrollment photos: `--image foto.jpg` resolves here.
    # Contents are gitignored — family photos never reach the repo.
    images_dir: Path = Path("server/src/server/images")

    # ---------------- Sensors ----------------
    sensor_debounce_seconds: int = 30
    sensor_delta_threshold: float = 0.5
    sensor_retention_hours: int = 72
    sensor_aggregation_interval_seconds: int = 3600

    # ---------------- Dashboard ----------------
    dashboard_enabled: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()  # pyright: ignore[reportCallIssue] — required fields are read from env vars by pydantic-settings
