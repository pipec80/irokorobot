# Operator manual

> **Status:** Canonical. Living day-to-day reference for running, isolating,
> and testing Iroko on the development PC. This is not a dated acceptance
> record — see [`p0-runtime-acceptance.md`](p0-runtime-acceptance.md) for
> that. When this manual and the code disagree, the code wins; update this
> file in the same change that changes behavior.

## 1. Starting the system

```powershell
just services       # Ollama + local models (skip if already running)
just run-server      # the "brain" — loads .env, binds loopback by default
just run-robot        # the "senses" — mic + speaker + webcam, talks to run-server
```

`just run-robot` needs a real microphone/speaker and, with face auth on, a
webcam. For headless iteration without the physical loop, use the tools in
§2 instead of the full robot.

First time only: `just setup` (dependencies + hooks), then
`just setup-personal` (owner, confirmed children, PIN — requires
`run-server`/`run-robot` stopped).

## 2. QA tools, by what they isolate

Iroko's turn is `mic → STT → LLM → TTS → speaker`, plus an HTTP boundary
between the robot and the server. Each tool below isolates one slice so a
problem can be localized without running the whole loop.

| Tool | Command | Isolates | Needs server? | Needs `.env`? |
|---|---|---|:---:|:---:|
| `mic_test.py` | `uv run python scripts/mic_test.py` | Mic capture → Whisper STT only | No | No |
| `piper_test.py` | `uv run python scripts/piper_test.py --text ...` | Text → Piper TTS → speaker only | No | No |
| `pipeline_test.py` | `just test-pipeline` | Full `mic → STT → LLM → TTS → speaker`, real production code, no HTTP | No | Yes (Ollama) |
| `client_test.py` | `just test-client` | Full HTTP round trip through the real running server | Yes | No |
| `chat_test.py` | `just chat-test` | `/chat` text-only: continuity, isolation, interactive mode | Yes | No |
| `memory_test.py` | `just memory-test --session` / `--show-db` | Public voice channel + raw SQLite memory state | Yes (except `--show-db`) | No |
| `vision_demo.py` | `just vision-demo` | Webcam frame → `/vision/describe` (scene only, no identity) | Yes, `VISION_ENABLED=true` | No |
| `faces_demo.py` | `just faces-demo --see` | Webcam/photo → `/vision/respond` scene dialogue (still no biometrics) | Yes | No |
| `face_auth_demo.py` | `just face-auth-demo --enroll` / `--revoke` | The Plan 0029 admin endpoints — enroll/revoke the owner's face | Yes, owner+PIN configured | No |
| `manage_household_roles.py` | `uv run python scripts/manage_household_roles.py bootstrap-owner` | Local role bootstrap, direct DB, no HTTP | No | No |
| `migrate_memory_v4.py` | `uv run python scripts/migrate_memory_v4.py --apply` | Legacy-fact migration into v4, dry-run first | No | No |
| `eval_chat.py` / `eval_consolidation.py` | `just eval-chat` / `just eval-memory` | Response/extraction quality against real Ollama — not `pytest` | Needs `just services` | Yes |

Rule of thumb: audio sounds wrong → `mic_test.py`/`piper_test.py` first (they
need nothing else running). The answer is wrong but audio is fine →
`pipeline_test.py` (bypasses HTTP, exercises the real LLM path directly).
Something only breaks through the real server → `client_test.py`/`chat_test.py`.

## 3. Security ladder — what Iroko can do at each tier

This is the actual, current state of progressive authentication (ADR-0008,
ADR-0009). Each tier is strictly additive: a later tier never removes an
earlier one, and the PIN stays a full, independent recovery path at every
tier above it.

### Tier 0 — No authentication (default, unknown speaker)

Always available, nothing to turn on.

- **Can:** perceive mic/camera under existing local privacy settings,
  transcribe, hold bounded general conversation, speak through TTS, keep an
  isolated request-local "unknown" context.
- **Cannot:** read, enumerate, or confirm personal/household memory;
  attribute a statement to the owner; mutate memory/identity/consent/
  credentials; control a device or the PC; enroll any biometric.
- A stranger asking *"¿quiénes son mis hijos?"* gets a non-disclosing
  denial — no name, no count, no hint the data exists.

### Tier 1 — PIN unlock (Plans 0025–0028, closed, real-hardware confirmed)

One spoken/typed local PIN issues one opaque, one-use grant (60 s TTL) that
authorizes exactly one `personal_protected_read` of `child_data` — nothing
else.

```powershell
$env:ROBOT_OWNER_UNLOCK_PROMPT = "true"   # or set in .env
just run-robot
```

Prompts once at startup (classic mode only, via `getpass` — never echoed).
**Limitation, by design:** this proves possession of the local secret, not
the physical identity of the speaker. One-use scope and the short TTL are
the accepted mitigation.

### Tier 2 — Face evidence (Plan 0029, code/tests merged 2026-08-25)

```env
FACE_AUTHENTICATION_ENABLED=true          # server
FACE_AUTHENTICATION_MATCH_THRESHOLD=0.25  # stricter than the generic 0.4
ROBOT_FACE_AUTH_ENABLED=true              # robot
```

Enroll once (needs a fresh PIN unlock internally, one time):

```powershell
just face-auth-demo --enroll
```

After that, a protected question is answered from the webcam frame attached
to that same turn — no PIN needed for it. Two-or-more detected faces is a
hard denial that does **not** fall back to asking for the PIN (a stranger
sharing the frame would still overhear the answer). Revoke with
`just face-auth-demo --revoke`, which really deletes the stored face
profiles, not a soft flag.

**Known gap, not yet closed:** no liveness/anti-spoofing — a photo of the
owner held to the camera authenticates. No real-camera calibration
(false-accept/reject rates, lighting, distance, glasses) exists yet. See
[`current-state.md`](../architecture/current-state.md) for the full
disclosure. Real-camera acceptance is a future plan, not yet written.

### Tier 3 — Voice evidence (PC-3, not started)

Planned: a real speaker-enrollment/verification adapter through the same
typed evidence contract. STT/VAD are not voice identity by themselves.

### Tier 4 — Conservative fusion (PC-4, not started)

Planned: combine one-use/face/voice evidence without a second authorization
system. Agreement may lower friction; conflict becomes `ambiguous`, never a
best-score guess. The PIN remains available even if every biometric fails.

## 4. Feature-flag reference

| Variable | Default | Effect |
|---|---|---|
| `ROBOT_OWNER_UNLOCK_PROMPT` | `false` | Classic mode only — prompt once for the PIN at robot startup |
| `ROBOT_STREAMING` | `false` | Use `/transcribe/stream` instead of classic `/transcribe` |
| `FACE_AUTHENTICATION_ENABLED` | `false` | Server: attempt face resolution when a frame is attached to a protected turn |
| `FACE_AUTHENTICATION_MATCH_THRESHOLD` | `0.25` | Stricter, separate match bound for authentication (layered on top of `FACE_MATCH_THRESHOLD`) |
| `ROBOT_FACE_AUTH_ENABLED` | `false` | Robot: capture and attach one webcam frame per turn |
| `FACE_MATCH_THRESHOLD` | `0.4` | Generic conversational face-recognition threshold (unrelated to authentication) |
| `VISION_ENABLED` | `false` | Enables `/vision/describe`, `/vision/respond` scene description |
| `UVICORN_WORKERS` | `1` | Must stay `1` — owner/face grants are process-local; the server refuses to start otherwise |

## 5. Where the evidence lives

- Per-plan real-hardware acceptance records: `project-history/acceptance/*`
  (gitignored — local history, never cited as a plan's required reading).
- The combined P0 operator runbook:
  [`p0-runtime-acceptance.md`](p0-runtime-acceptance.md).
- What's actually implemented right now, including open gaps:
  [`current-state.md`](../architecture/current-state.md).
- What's authorized to build next: [`docs/plans/README.md`](../plans/README.md).
