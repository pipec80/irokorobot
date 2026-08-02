# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

From the next release onward this file is maintained automatically by
[Commitizen](https://commitizen-tools.github.io/commitizen/) via `just release`.

## 0.1.0 (2026-08-02)

Initial public release of Iroko (OMNiBot 2000) — a local-first voice AI pipeline
for a modernized vintage Omnibot robot.

### Added

- **Audio API server** (FastAPI): `POST /transcribe` running the full
  speech-to-text → LLM → text-to-speech pipeline, plus a sentence-streaming
  variant for lower perceived latency.
- **Speech-to-text** via faster-whisper (CTranslate2), Spanish by default.
- **Language model** client supporting Claude (Anthropic) and local Ollama.
- **Text-to-speech** via Piper.
- **Text chat**: a `POST /chat` boundary and a local, same-origin **diagnostic
  chat UI** at `/chat-ui` (no microphone, camera, or TTS required).
- **Brain memory (v3)**: local persistence of entities, relations, and episodes
  with a deterministic, validatable context layer.
- **Vision**: image decoding/validation and consented face recognition.
- **Robot client** (Raspberry Pi 5): microphone capture with Silero VAD (RMS
  fallback) and an async `httpx` client to the server.
- **Tooling**: uv workspace, Ruff, mypy, Bandit, pip-audit, pre-commit,
  Commitizen, and a GitHub Actions CI quality gate.
