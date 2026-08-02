# 🤖 OMNiBot 2000

> A vintage 1980s Omnibot robot, modernized with a local voice AI pipeline.
> Speaks Spanish. Runs offline. Lives at home.

![Python](https://img.shields.io/badge/Python-3.12-blue)
![uv](https://img.shields.io/badge/managed%20by-uv-purple)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-phase%201%20%E2%80%94%20active-brightgreen)

---

## What is this

OMNiBot 2000 is a personal robotics project that brings a vintage Omnibot toy back to life
with modern AI capabilities. The robot listens, understands Spanish, and responds with a
synthesized voice — entirely offline, running on local hardware at home.

This repository contains the voice AI pipeline: the server that processes audio and
the client that runs on the robot.

---

## Architecture

The system is split into two independent components that communicate over local WiFi.

```
┌─────────────────────────────────┐         ┌──────────────────────────────────┐
│         OMNiBot (Pi 5)          │         │        Homelab Server            │
│                                 │         │                                  │
│  Microphone → audio capture     │──WAV───▶│  faster-whisper  → text          │
│  VAD → silence detection        │         │  Claude API      → response      │
│  Speaker ← audio playback       │◀──WAV───│  Piper TTS       → audio         │
└─────────────────────────────────┘         └──────────────────────────────────┘
         Raspberry Pi 5                          i5-12500T · 16GB RAM
```

**Key design decision:** The server is a generic audio API. It does not know a robot exists.
The robot is a generic audio client. It does not know what STT, LLM, or TTS are.
They share only a single API contract.

---

## Tech Stack

### Server — runs on homelab
| Component | Technology | Notes |
|-----------|-----------|-------|
| API Framework | FastAPI + uvicorn | Async, production-grade |
| Speech-to-Text | faster-whisper | Whisper model via CTranslate2 |
| Language Model | Claude API (Haiku) | Local Ollama in phase 2 |
| Text-to-Speech | Piper TTS | Voice: `es_MX-claude-high` |
| Validation | Pydantic v2 | Settings + request/response models |

### Robot client — runs on Raspberry Pi 5
| Component | Technology | Notes |
|-----------|-----------|-------|
| Audio capture | sounddevice | Microphone input |
| Audio output | sounddevice | Speaker playback |
| VAD | Energy RMS | Simple silence detection |
| HTTP client | httpx | Async, with retry logic |
| DSP | numpy | Audio format conversion |

### Development
| Tool | Purpose |
|------|---------|
| uv | Package manager + workspace |
| Ruff | Linter + formatter |
| mypy | Static type checker |
| pre-commit | Automated code quality hooks |
| GitHub Actions | CI pipeline |

---

## Project Structure

```
omnibot/
├── CLAUDE.md                    ← Claude Code rules (persistent AI memory)
├── README.md                    ← This file
├── pyproject.toml               ← uv workspace + shared tool config
├── uv.lock                      ← Dependency lockfile
├── .env.example                 ← Environment variable reference
├── .pre-commit-config.yaml      ← Git hooks
│
├── server/                      ← Homelab server
│   ├── pyproject.toml
│   └── src/server/
│       ├── main.py              ← FastAPI app + /transcribe endpoint
│       ├── stt.py               ← faster-whisper wrapper
│       ├── llm.py               ← Claude API client
│       ├── tts.py               ← Piper TTS wrapper
│       ├── settings.py          ← Pydantic settings from env vars
│       └── exceptions.py        ← Custom exceptions
│
└── robot/                       ← Raspberry Pi 5 client
    ├── pyproject.toml
    └── src/robot/
        ├── audio_capture.py     ← Microphone + VAD
        └── server_client.py     ← HTTP client to server
```

---

## API Contract

```
POST /transcribe
Content-Type: multipart/form-data
Body: audio (WAV · 16kHz · mono · int16)

Response 200 OK:
{
  "text_heard":   "enciende la luz de la cocina",
  "llm_response": "Entendido, encendiendo la luz de la cocina.",
  "audio_base64": "<base64 WAV>",
  "duration_ms":  1840,
  "emotion":      "neutral"
}

Response 422: Validation error
Response 500: Internal server error with detail
```

Audio format is the only exchange format. The robot sends voice, receives voice.
Everything else is internal to the server.

---

## Getting Started

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) installed
- Anthropic API key
- Piper voice model downloaded (`es_MX-claude-high`)
- A microphone and speakers

### Installation

```powershell
# Clone the repository
git clone https://github.com/pipec80/irokorobot.git
cd irokorobot

# Install all dependencies
uv sync --all-groups

# Copy and configure environment variables
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### Download Piper voice model

```powershell
# Create models directory
mkdir -p models/piper

# Download voice (Linux/Mac)
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/claude/high/es_MX-claude-high.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/claude/high/es_MX-claude-high.onnx.json

# Move to models directory
mv es_MX-claude-high.* models/piper/
```

### Run in development (single machine)

```powershell
# Terminal 1 — Start the server
uv run --env-file .env --package server server

# Terminal 2 — Start the robot client
uv run --env-file .env --package robot robot
```

Press **Enter** to activate recording, speak, press **Enter** again to send.
The robot responds through your speakers.

---

## Environment Variables

See `.env.example` for the full reference. Key variables:

```env
# Required
ANTHROPIC_API_KEY=sk-ant-...

# STT
WHISPER_MODEL=small          # small | medium | large-v3
WHISPER_LANGUAGE=es
WHISPER_COMPUTE_TYPE=int8

# TTS
PIPER_VOICE=es_MX-claude-high
PIPER_MODELS_DIR=./models/piper

# Server
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# Robot
SERVER_URL=http://localhost:8000   # change to homelab IP in production
```

---

## Development Roadmap

### Phase 1 — Voice pipeline (current)
- [x] Project structure and tooling
- [ ] Server: STT + LLM + TTS pipeline
- [ ] Robot: audio capture + HTTP client
- [ ] End-to-end: speak → hear → respond

### Phase 2 — Intelligence
- [ ] Wake word detection ("Hey OMNiBot") via OpenWakeWord
- [ ] Migrate LLM to Ollama local (llama3.2 or mistral)
- [ ] Migrate TTS to Chatterbox Turbo (requires GPU)
- [ ] Emotion-aware response modulation

### Phase 3 — Autonomy
- [ ] OAK-D Lite stereo camera integration
- [ ] YOLO object detection
- [ ] Person recognition (family members)
- [ ] ROS2 integration for motor control

### Phase 4 — Teleoperation
- [ ] LiveKit WebRTC transport
- [ ] Mobile app for remote control
- [ ] SLAM navigation (ROS2 Nav2)
- [ ] Docker containerization

---

## Hardware

| Component | Model | Notes |
|-----------|-------|-------|
| Robot body | Omnibot 2000 (1984) | Vintage, mechanically restored |
| Compute | Raspberry Pi 5 (8GB) | Robot brain |
| Vision | OAK-D Lite | Stereo depth + AI |
| Motors | TB6612FNG driver | Replaces original motor driver |
| Microphone | ReSpeaker USB Array | 4-mic array, echo cancellation |
| Server | OptiPlex 7010 MFF | i5-12500T · 16GB RAM |

---

## Code Quality

This project follows strict coding standards defined in `CLAUDE.md`:

- **SOLID, DRY, KISS, YAGNI** principles enforced
- **Type hints** mandatory on all functions
- **Google-style docstrings** on all public APIs
- **No bare except**, no magic strings, no print()
- PEP 8, PEP 257, PEP 484 compliance via Ruff + mypy

```powershell
# Lint
uv run ruff check .

# Format
uv run ruff format .

# Type check
uv run mypy server/src robot/src

# All checks (runs automatically on commit)
pre-commit run --all-files
```

---

## Contributing

This is a personal project but contributions are welcome.
See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Report bugs via [GitHub Issues](../../issues).
For security vulnerabilities, see [SECURITY.md](SECURITY.md).

---

## License

MIT — see [LICENSE](LICENSE) for details.

---

## Acknowledgements

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — SYSTRAN
- [Piper TTS](https://github.com/OHF-Voice/piper1-gpl) — Open Home Foundation
- [Anthropic Claude](https://anthropic.com) — LLM backbone
- [uv](https://github.com/astral-sh/uv) — Astral
- Original Omnibot 2000 — Tomy Corporation (1984)
