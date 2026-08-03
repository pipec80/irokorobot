# 0002 — Separate server (brain) and robot (senses)

- **Status:** Accepted
- **Date:** 2026-08-03

## Context
Heavy AI work (STT, LLM, TTS, memory, vision) needs compute a Raspberry Pi
cannot provide, while audio and camera capture must run on the robot itself.

## Decision
Split into two independent packages that share only a documented HTTP/audio API:

- **server** — a generic audio/text API; it does not know a robot exists.
- **robot** — a generic client; it does not know about STT/LLM/TTS.

Neither side may reach across this boundary except through the API contract
(see `CONTRIBUTING.md`).

## Alternatives considered
- **Monolith on the Pi**: infeasible — models exceed Pi compute/RAM.
- **Everything on the server, robot streams raw audio only**: acceptable, but the
  VAD/half-duplex logic still belongs on the robot.

## Consequences
### Positive
- Each side evolves independently; the server is reusable beyond this robot.
- Clear testing boundary — mock the API.

### Negative
- Network dependency and latency between the two.
- Two deploy targets to manage.

## Review
Revisit if the robot gains enough compute to run the brain locally, or if a
transport other than local HTTP (e.g. WebRTC) is adopted.
