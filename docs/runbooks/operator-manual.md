# Operator manual

> **Status:** Canonical. Living day-to-day reference for running, isolating,
> and testing Iroko on the development PC. This is not a dated acceptance
> record — see [`p0-runtime-acceptance.md`](p0-runtime-acceptance.md) for
> that. When this manual and the code disagree, the code wins; update this
> file in the same change that changes behavior.

## 0. Fresh clone — from zero to running

Verified against the actual code and scripts (2026-08-26), not assumed.
`CONTRIBUTING.md`'s "Development setup" only covers `just setup` — treat
this section as the current source of truth for actually running Iroko,
not just contributing code to it.

**Outside the repo, nothing here automates these** — install them yourself
first: `git`, `uv` (≥0.6.0, `pyproject.toml`'s `[tool.uv] required-version`),
`just`, and **Ollama itself** (the application, not just its models). Python
3.12 does not need a separate install — `uv`'s `python-preference = "managed"`
fetches it.

```powershell
just setup                    # deps + pre-commit hooks + secrets baseline + Silero VAD (2.3 MB, bundled — see below)
Copy-Item .env.example .env   # NOT automated anywhere — do this manually
```

Edit the new `.env` — at minimum confirm `PIPER_VOICE` matches the voice
you're about to fetch below.

**Model downloads — verified one by one, each traced to its actual source
in the installed packages, nothing guessed:**

| Model | Auto? | How to get it |
|---|---|---|
| Whisper (STT) | Yes | Cached from HuggingFace on first call, offline after (`stt.py`) — nothing to run |
| InsightFace (face) | Yes | ~300 MB, downloaded on first face detection/enrollment call (`vision/faces.py`) — nothing to run |
| Silero VAD | Bundled into `just setup` (2.3 MB) | Was previously a separate step — `just fetch-vad-model` still works standalone if you skipped `setup` |
| **Piper (TTS voice)** | **No — one command, run once per voice** | `just fetch-piper-voice` — wraps the official `piper.download_voices` module already bundled in the `piper-tts` dependency this project uses; source is `huggingface.co/rhasspy/piper-voices` (verified from the installed package's own code, not guessed). Defaults to `.env`'s `PIPER_VOICE`; pass `--voice <name>` for a different one, `--force` to re-fetch |
| Ollama models (chat/embed/consolidation/vision) | No — opt-in, multi-GB | `just services` only checks and reports `[MISSING]`; run `just pull-models` when you're ready to commit the bandwidth/disk — it pulls exactly the missing ones and is safe to rerun after a partial failure |

```powershell
just fetch-piper-voice        # once per voice — safe to rerun, skips files that already exist
just services                 # starts Ollama, reports which models are still missing
just pull-models              # opt-in — actually downloads the missing ones (can be several GB)
```

Once the server can actually boot and speak, set up the owner:

```powershell
just setup-personal status   # non-interactive: prints owner_count, credential_count, etc — safe to run anytime
just setup-personal          # the interactive wizard (requires run-server/run-robot stopped)
```

The wizard's exact prompt sequence (`personal_setup.py::run_personal_setup_wizard`):
`Owner name:` → `Child names (comma or space separated):` → `PIN (6-12
digits):` (hidden) → `Confirm PIN:` (hidden) → a summary, then `Type CONFIRM
to confirm:` before anything is written. Re-running with the same PIN is a
no-op; a different PIN rotates the credential.

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

Prompts once at startup, via `getpass` — never echoed. Works with both
classic and streaming mode (Plan 0027 added streaming parity for the PIN
token; there is no start-time guard between `ROBOT_OWNER_UNLOCK_PROMPT` and
`ROBOT_STREAMING` — an older comment in `.env.example` claimed one existed,
corrected 2026-08-26; the only real robot startup guard is
`ROBOT_STREAMING` vs. the server's `VISION_ENABLED`, see §4).
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
| `ROBOT_OWNER_UNLOCK_PROMPT` | `false` | Prompt once for the PIN at robot startup (`getpass`) — works in both classic and streaming mode |
| `ROBOT_STREAMING` | `false` | Use `/transcribe/stream` instead of classic `/transcribe` |
| `VISION_ENABLED` | `false` | Server: enables `/vision/describe`, `/vision/respond` scene description (unrelated to face auth) |
| `FACE_AUTHENTICATION_ENABLED` | `false` | Server: attempt face resolution when a frame is attached to a protected turn |
| `FACE_AUTHENTICATION_MATCH_THRESHOLD` | `0.25` | Stricter, separate match bound for authentication (layered on top of `FACE_MATCH_THRESHOLD`) |
| `ROBOT_FACE_AUTH_ENABLED` | `false` | Robot: capture and attach one webcam frame per turn |
| `FACE_MATCH_THRESHOLD` | `0.4` | Generic conversational face-recognition threshold (unrelated to authentication) |
| `UVICORN_WORKERS` | `1` | Must stay `1` — owner/face grants are process-local; the server refuses to start otherwise |

**The one real startup guard:** `ROBOT_STREAMING=true` on the robot plus
`VISION_ENABLED=true` on the server makes the robot refuse to start
(`SystemExit`, checked once at boot via `check_vision_enabled()`) — streaming
has no code path for visual questions yet (F-08). Every other flag
combination above is safe to mix.

## 5. Where the evidence lives

- Per-plan real-hardware acceptance records: `project-history/acceptance/*`
  (gitignored — local history, never cited as a plan's required reading).
- The combined P0 operator runbook:
  [`p0-runtime-acceptance.md`](p0-runtime-acceptance.md).
- What's actually implemented right now, including open gaps:
  [`current-state.md`](../architecture/current-state.md).
- What's authorized to build next: [`docs/plans/README.md`](../plans/README.md).

## 6. What `just setup-personal` actually does, and a dead feature it should not be confused with

Verified 2026-08-26 by reading `personal_setup.py` end to end, not assumed.
This is the **only** thing that answers "Pipec is your owner" — nothing
conversational does this, see below.

### The exact write sequence

```powershell
just setup-personal          # requires run-server/run-robot stopped — single SQLite connection
```

Three writes, in order, all inside `apply_personal_setup()`:

1. **`_confirm_owner_entity`** — `upsert_entity(name=owner_name, type="person")`, then
   `bootstrap_initial_owner(person_entity_id, confirmed_person_entity_id)`. This is
   the actual anchor: one row in `household_role_assignments` with `role='owner'`,
   enforced singleton (`_active_owner_exists()` raises if one already exists).
   Reruns with the same name reuse the same entity — it does not duplicate.
2. **`_confirm_children`** — one entity + one `child_of` relation per name, in
   `entity_relations_v4`, pointed at the owner entity from step 1.
3. **`_confirm_credential`** — hashes the PIN with scrypt (`hash_pin`), stores it
   via `save_owner_pin_credential`. Reusing the same PIN is a no-op; a different
   one rotates the credential.

Everything the rest of this manual's Tier 1/Tier 2 sections depend on — `get_active_role()`,
the PIN unlock, the face resolver's owner check — reads back exactly these three writes.
There is no fourth, hidden mechanism.

### A dead feature that looks like an alternative onboarding — it is not one

The character prompt (`characters/iroko.py`) has a real, well-built conversational
onboarding block:

```
PRIMER ENCUENTRO — acabás de despertar y conocés a una persona del hogar por primera vez:
- Presentate en máximo 2 oraciones...
- Qué preguntar lo indica el PRÓXIMO OBJETIVO más abajo...
- UNA sola pregunta por turno...
```

Backed by an 8-slot checklist (`onboarding.py`): `nombre → fecha_nacimiento → vive_en
→ pareja_de → hijo_de → mascota_de → trabaja_en → le_gusta`. It looks like it should be
the conversational path to "the robot learns who its owner is." **It is not, for two
independent reasons, both verified against the current code:**

1. **It could never create the owner even if it worked.** The gate at
   `text_turn.py`'s `prepare_text_turn()` — `if manual_evidence is None: ...
   onboarding=False` — means this interview only starts for an ALREADY-identified
   actor. It was designed as a "get to know you better" layer on top of an
   existing owner, never as the mechanism that establishes one. `just setup-personal`
   has no conversational alternative today.
2. **It is fully disconnected, right now.** The one function that could pass real
   values into it always hardcodes them away:
   ```python
   async def _memory_prompt_state(
       message: str,
   ) -> tuple[MemoryContext | None, bool, OnboardingSlot | None]:
       """Resolve legacy-compatible persistent context without global onboarding."""
       context = await build_context(message)
       return context, False, None
   ```
   `onboarding.py::next_missing_slot()` has zero live callers anywhere in the
   repo — confirmed by grep, not inference. This matches what
   [ADR-0007](../adr/0007-first-boot-and-default-posture.md) flagged as
   "built, tested, zero production callers" back on 2026-08-19; it is still true
   after everything Plan 0029 added.

**Do not reconnect this as-is if it ever comes up.** Its checklist reads/writes the
legacy v3 fact tables (`load_entity_with_facts`, `find_facts_by_predicate`), not the
v4 tables (`entity_relations_v4`) `setup-personal` uses — reconnecting it verbatim
would ask "¿tenés hijos?" again and store the answer somewhere `get_children()` never
looks. Any future reconnection needs its own bounded plan: migrate the checklist to
v4, then decide whether it should still gate on an existing owner or be scoped
narrower (e.g. only the optional/non-security slots — birthday, work, likes).

### The symptom this explains: "los hijos son Max..." instead of "tus hijos son Max..."

Before the deterministic child-name tool existed (or when a question's phrasing
doesn't match the intent resolver's known patterns and falls through to generic
LLM generation), the ONLY path available was free LLM generation over memory
context. That path carries an explicit rule (`_PRESENTATION_GUIDANCE` in
`characters/__init__.py`):

```
- Do not infer relationships, personal facts, or authorization from it.
```

Even with a name available in context, the LLM is forbidden from concluding
"so these are YOUR children" — it has no deterministic authorization to make that
claim. That is structurally why it degrades to third person. The fix is not a
prompt tweak: it's routing the question through the deterministic tool
(`controller.py::_household_tool_plan`, `response = f"Tus hijos son {names}."`,
never touching the LLM), which is what Plans 0021/0025–0028 already built and this
plan's Tier 1/Tier 2 sections describe. If this symptom reappears, the fault is
almost always an unrecognized phrasing in `cognition/intent_resolution.py`, not the
character prompt.
