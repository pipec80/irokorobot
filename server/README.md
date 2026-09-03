# Server runtime configuration

## Capacity policy (Plan 0038)

The server runs as **one Uvicorn worker, always** — `uvicorn_workers` is
`Literal[1]` in `Settings`; owner-unlock grants, SQLite state, and background
jobs are process-local (ADR-0010), so a second worker would silently split
them across processes instead of sharing them.

Two runtime knobs bound load, and **neither one creates capacity**:

- `UVICORN_LIMIT_CONCURRENCY` (default `100`, uncalibrated) — once this many
  connections are open at once, Uvicorn returns `503 Service Unavailable` to
  any new one. It does not queue them, and it does not make the process
  handle more work; it only decides where the line is drawn.
- `UVICORN_MAX_REQUESTS` (default unset) — if set, Uvicorn exits the worker
  process after handling that many requests. **This requires a supervisor
  that restarts the process** (systemd, a container orchestrator, a process
  manager). Iroko has none today. Setting this without one turns a normal
  request into an outage: the server simply stops and stays stopped. Leave
  it unset until a real supervisor exists and is verified to restart the
  process reliably.

### Measuring real capacity

`100` is the value this project already ran with before Plan 0038 — carried
forward, not newly chosen. No specific number in this document is a measured
production target; measure on the actual target hardware before trusting one.

To measure, run a real load tool (e.g. `hey`, `wrk`, or `locust`) against a
running `just run-server` instance, and record — for **your real target
hardware**, not this laptop — latency and error rate at each of:

| Concurrency | p50 latency | p99 latency | Error rate | Notes |
|---:|---|---|---|---|
| 2 | | | | |
| 4 | | | | |
| 8 | | | | |
| 100 (current default) | | | | |

A turn touches Whisper, Ollama, and Piper in sequence — CPU- and
memory-bound, not I/O-bound — so the useful concurrency ceiling on a home
server is likely far below `100`. Lower `UVICORN_LIMIT_CONCURRENCY` only
after a real measurement says so; raising it without measurement risks
paging the machine into swap under real load instead of returning a fast
`503`.

### Graceful shutdown

`UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN` (default `30` seconds) bounds how long
Uvicorn waits for in-flight requests to finish before forcing a stop —
important here because a single turn (STT → LLM → TTS) can itself take
several seconds. `UVICORN_TIMEOUT_KEEP_ALIVE` (default `5` seconds) is the
existing, unchanged HTTP keep-alive idle timeout.
