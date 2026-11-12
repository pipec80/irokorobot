# 0033 — The home server: the brain in a container on the laptop, the body a client

- **Status:** Proposed (2026-11-11). Written from the roadmap row of 2026-11-06, ADRs 0013, 0025 and
  0035, the code read that day and Pipec's four decisions of 2026-11-11 (see *Pipec's decisions and
  where they land*). It becomes `Accepted` when the plan that implements it closes.
- **Date:** 2026-11-11
- **Builds on:** [ADR 0002](0002-server-robot-separation.md) (server and robot share only the API),
  [ADR 0013](0013-local-http-network-posture.md) (local-first network posture),
  [ADR 0025](0025-remote-administration-backup-updates-and-telemetry.md) (administration and backup),
  [ADR 0032](0032-block-c-hygiene-correct-forget-and-years.md) (the deletion register),
  [ADR 0035](0035-deployment-worlds.md) (the body, the server, the dashboard).
- **Amends:** [ADR 0013](0013-local-http-network-posture.md) (a named local peer and the LAN rules,
  decision 2); lifts **Docker** from the project's «Future — do not implement» list and the
  container non-goal of `server-production-baseline.md`.
- **Delivers:** row 10 of the
  [path to the finish line](../roadmap/cognitive-roadmap.md#closing-path-of-conversational-memory)
  («the laptop is only the home server»). Reserved since 2026-11-06.

## Context

1. **The finish line is a server, not a development session.** Today the server runs from VS Code
   with `just run-server` beside the development tools. ADR 0035 places the brain on this laptop now
   and on a Raspberry Pi or Jetson class board later; the body (the ESP32, today the laptop's
   microphone, webcam and speakers) is a client of the API.
2. **The unlock and the enrolment trust loopback.** `routers/auth.py` serves the owner's PIN unlock
   and the face and voice enrolment only to a peer whose address is loopback. Inside a container,
   a client on the same laptop arrives from the container network's gateway, not from loopback, so
   both would refuse.
3. **The models are heavy and partly GPU-bound.** Ollama serves the chat, vision and embedding
   models; Whisper `medium` runs on the GPU when the optional `cuda` extra is installed (ADR 0023);
   the speaker model and Whisper read the Hugging Face cache, which must be present offline. The
   laptop's GPU has 2 GB.
4. **Nothing is backed up and nothing is encrypted at rest.** ADR 0025 decision 6 decided the shape
   of a backup (SQLite's online backup, encrypted, a restore tested before it is trusted, face and
   voice embeddings excluded by default) but no backup runs. ADR 0032 requires a restore to re-apply
   the deletion register.
5. **The last turn is written after the reply** (ADR 0032 decision 7), so how the server stops
   matters.

## Decision

### 1. One container for the server; Ollama stays native on Windows (*Pipec, 2026-11-11*)

- The server runs in one container built from the uv workspace (Python 3.12), started by
  `docker compose` with a restart policy, without VS Code. The robot client is a separate process
  (today on the same laptop, later the ESP32), so the hard boundary of ADR 0002 holds in practice.
- **Ollama stays native on Windows** with its GPU; the container reaches it at
  `host.docker.internal` through the existing `OLLAMA_URL` setting. Only the server is
  containerized.
- **Whisper on the GPU** uses the NVIDIA support of Docker Desktop on WSL2 when present, with the
  CPU as the safe fallback (ADR 0023's `cuda` extra in the image; a start-up line says which).
- **Volumes:** `data/` (the database, the deletion register and the commissioning acta) is a host
  directory mounted read-write; the model caches (Piper, InsightFace, the speaker model, the
  Hugging Face cache) are mounted read-only from the host, so the container needs no network to
  start. The offline run (a cross-cutting row, before this) proves it.

### 2. The network: the laptop only until the body connects (*Pipec, 2026-11-11*)

- The container listens on all its interfaces, and compose publishes the port **on the host's
  `127.0.0.1` only**. Nothing on the LAN reaches it.
- **A named local peer** (this ADR amends ADR 0013): a setting names the container network's
  gateway as the one peer treated as local for the PIN unlock and the enrolment. It is honoured only
  when the server is told the port is published on loopback; the start-up refuses the combination
  of a named local peer and a LAN publication. The loopback check stays the only route to those
  endpoints; there is no new login.
- **The LAN rules, written now and switched on with the body:** publication on the LAN interface
  only, `TrustedHostMiddleware` with the configured host names, a per-device key the body presents
  on every request (issued and revoked with `iroko-admin`), the unlock and the enrolment still
  limited to the named local peer, no CORS, no proxy headers unless a named proxy. TLS waits for a
  real topology, as ADR 0013 says.

### 3. Administration runs inside the container's world

`just commission`, `iroko-admin` and `just seed-import` run as one-off containers from the same
image and volume (`docker compose run --rm`), with the server container stopped when the command
needs it stopped, exactly as today. The camera and microphone steps of the commissioning
(enrolment) run in the robot client on the host and call the API through the named local peer.

### 4. Backups: daily, encrypted with restic, kept locally first (*Pipec, 2026-11-11*)

- Once a day, and before an update, the server takes a consistent snapshot with SQLite's online
  backup (never a copy of the open file) into a staging folder; `restic` encrypts it into a
  repository on the laptop or a separate disk. The key is the owner's (and the builder's, as
  ADR 0025 says); it is never in the image or the repository.
- Face and voice embeddings are excluded by default (ADR 0025). The deletion register (ADR 0032)
  is backed up too.
- **A restore** (an `iroko-admin` command, server stopped) puts the snapshot back, then re-applies
  every deletion-register line newer than the snapshot, then runs the integrity checks of ADR 0032
  before the server starts. A test restores a backup older than a deletion and finds nothing.
- Retention of snapshots and the homelab or cloud copies follow ADR 0025, after the line.

### 5. Encryption at rest is the disk's: BitLocker now, LUKS on the board (*Pipec, 2026-11-11*)

The laptop's system drive is encrypted with BitLocker, which covers the database, the local
backups, the caches and the logs with no change to the code; on the future board, LUKS. The
restic repository is encrypted on its own (decision 4). SQLCipher is not used: it would change the
SQLite driver and the vector extension's loading for a protection the disk already gives.

### 6. Health and an orderly stop

- `/health` reports whether Ollama answers (today it does not, roadmap); `/ready` stays the
  readiness probe. A failed Ollama start-up probe is visible to the operator, not only in a log.
- On `docker compose stop` the server stops accepting turns, lets the turn in flight finish and
  its record write land, stops the background jobs, closes the database (`PRAGMA optimize`) and
  exits, within a grace period set in compose. A turn cut by a power loss is ADR 0032 decision 7.

## Pipec's decisions and where they land

| # | Decision | Date | Where |
|---|---|---|---|
| 1 | The server in Docker on the laptop before block D; the robot a separate client | 2026-11-06 | Decision 1 |
| 2 | The port published on the laptop only until the body connects; the LAN rules written now | 2026-11-11 | Decision 2 |
| 3 | Ollama native on Windows, reached from the container | 2026-11-11 | Decision 1 |
| 4 | A daily backup, encrypted with restic, kept locally first | 2026-11-11 | Decision 4 |
| 5 | Encryption at rest by BitLocker (LUKS on the board) | 2026-11-11 | Decision 5 |

The author's calls, for Pipec's review: the named local peer as the answer to the loopback check;
the per-device key for the LAN; administration as one-off containers; the read-only model mounts;
the restore order (snapshot, register, integrity checks).

## Not decided here

| Subject | Owner |
|---|---|
| The ESP32 body's client and its protocol | After the line (ADR 0035) |
| The remote dashboard, VPN, support sessions, updates and telemetry | ADR 0025's remote half, after the line |
| The board the server moves to, and its measurements | ADR 0035, after the line |
| A second local model or a cloud provider | ADR 0036 (Proposed), P4.1 |

## Alternatives considered

- **Ollama in its own container.** Rejected by Pipec: the 2 GB GPU would be split between
  containers, and Ollama runs well natively.
- **Publishing on the LAN now.** Rejected by Pipec: nothing on the LAN needs it before the body.
- **A login for the unlock instead of the loopback check.** Rejected: it adds a credential path;
  naming the one local peer keeps ADR 0013's rule.
- **SQLCipher.** Rejected: a driver change for what disk encryption already covers.
- **Litestream continuous replication.** Rejected for now: a daily snapshot fits a home robot; it
  stays an option after the line.

## Consequences

### Positive

- The laptop runs the brain as a service; the body is a real client of the API.
- The same image moves to the board later; the data and the models are volumes.
- Backups exist, are encrypted, and a restore cannot bring back what was forgotten.

### Negative

- Docker Desktop's VM takes RAM on a laptop that already shares it with Ollama and Whisper; the
  saving comes from closing the development tools.
- GPU support for Whisper depends on Docker Desktop and the NVIDIA driver under WSL2; the CPU
  fallback is slower.
- One more moving part (compose, the image) to keep updated.

## Test consequences

- The container starts with the network off and the caches mounted; `/health` says when Ollama is
  down.
- The unlock and the enrolment work from the host client and are refused from any other peer; the
  start-up refuses a named local peer together with a LAN publication.
- A full voice turn from the robot client against the container; an orderly stop loses no record
  write; a restore older than a deletion finds nothing; a backup holds no face or voice embedding
  by default.

## Docs to update

The ADR index; `AGENTS.md` and `CLAUDE.md` (Docker leaves the «Future» list); the roadmap (row 10,
the deployment row); `server-production-baseline.md` (the container non-goal); `server/README.md`
and the operator manual (compose, backup, restore, BitLocker); `current-state.md` and the
architecture diagrams when the plan closes; ADR 0013 (an *Amended by ADR 0033* note, when accepted).
