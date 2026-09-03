"""Application settings loaded from environment variables."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, PositiveInt, field_validator
from pydantic_settings import BaseSettings


def _coerce_to_int(value: object) -> object:
    """Parse a raw env-var string before the `Literal[1]` check runs.

    `pydantic-settings` coerces a plain `int` field from its env string
    automatically, but not a `Literal[int]` field — env parsing decides by
    outer type, and `Literal` isn't `int`. Left uncoerced, `UVICORN_WORKERS=1`
    in `.env` fails validation against the literal `1` because `"1" != 1`.
    """
    return int(value) if isinstance(value, str) else value


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
    server_port: Annotated[int, Field(gt=0, le=65535)] = 8000
    log_level: str = "INFO"
    log_to_file: bool = True
    log_dir: Path = Path("logs")
    log_retention_days: int = 14

    # ---------------- Uploads (Plan 0034) ----------------
    # Per-file semantic budgets, checked after the raw ASGI body limit.
    # Separate settings because /transcribe can carry both audio and an
    # optional face frame in the same multipart body — one shared ceiling
    # would either reject a valid combined request or let either file alone
    # grow past what its own contract needs.
    max_audio_upload_bytes: int = 10 * 1024 * 1024  # 10 MB — well above any realistic utterance
    max_image_upload_bytes: int = 5 * 1024 * 1024  # 5 MB — well above a 1280x720 frame
    max_image_pixels: int = 1280 * 720
    max_audio_duration_s: float = 30.0  # well above any realistic utterance
    # Raw ASGI body ceiling for the combined audio+frame route: the two
    # per-file budgets above, plus multipart framing overhead.
    max_request_body_bytes: int = max_audio_upload_bytes + max_image_upload_bytes + 64 * 1024

    # Owner-unlock grants, SQLite state, and background jobs are process-local
    # (ADR-0010): a second worker would silently split them across processes.
    # Literal[1] fails at construction, before the app ever imports — a
    # stronger guarantee than a runtime check inside lifespan (which stays,
    # as defense-in-depth, for the unlikely case Settings is constructed via
    # model_construct() and skips validation).
    uvicorn_workers: Literal[1] = 1
    uvicorn_proxy_headers: bool = False
    # Uncalibrated (Plan 0038): preserves the pre-existing value rather than
    # guessing a new one. Measure on real target hardware before changing it —
    # see server/README.md's capacity policy.
    uvicorn_limit_concurrency: int = 100
    # Unset by default: recycling the process on a fixed request count only
    # helps with a supervisor that restarts it — none exists yet, so the old
    # default of 1000 made the server self-terminate with nothing to bring it
    # back (Plan 0038).
    uvicorn_max_requests: PositiveInt | None = None
    uvicorn_timeout_keep_alive: PositiveInt = 5
    uvicorn_timeout_graceful_shutdown: PositiveInt = 30

    # One-use owner PIN unlock grant (Plan 0026): how long an issued token
    # stays valid before its first (and only) protected use. Was a fixed
    # 60s; raised to a configurable default so a real conversational pause
    # between unlocking and asking the protected question doesn't silently
    # expire the grant. Still exactly one-use — this only widens the window
    # to spend it, never how many times it can be spent.
    owner_unlock_ttl_seconds: int = 300

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
    # Value measured by Plan 0030's real-camera calibration (2026-08-27,
    # provisional session): 36 genuine samples (3 lighting x 2 distance x
    # 2 glasses) vs 18 impostor samples across 3 unrelated identities, using
    # the 3-enrolled-profile matching policy. Zero false accepts and zero
    # false rejects held at every round as the impostor set grew from 6 to
    # 18 samples. Midpoint of [0.277, 0.886] — margin 0.610. Provisional:
    # narrower than a mature study would want; see
    # project-history/acceptance/2026-08-27-real-camera-face-acceptance-provisional.md
    # (untracked) for the full sweep and the plan for widening the impostor
    # set further.
    face_authentication_match_threshold: float = 0.5815
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

    _coerce_uvicorn_workers = field_validator("uvicorn_workers", mode="before")(_coerce_to_int)


settings = Settings()  # pyright: ignore[reportCallIssue] — required fields are read from env vars by pydantic-settings
