# Consented Local Face Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Status:** Approved by Pipec on 2026-08-25 as Plan 0029. Not yet implemented.

**Goal:** Let a protected voice turn resolve the owner from a webcam frame
attached to the same request, emitting typed `IdentityEvidenceSource.FACE`
evidence that flows through the exact same authorization pipeline the PIN
already uses (Plan 0026) — with no token, no gesture, and no new capability.

**Product framing:** the PIN proved the security layer works (P1.1). It is
scaffolding, not the product. The target model is the one already familiar
from a phone: face and voice resolve identity instantly; the PIN remains the
recovery path when biometrics fail. This plan delivers the face half of that
model — PC-2 of
[Plan 0015](0015-personal-companion-design.md). Voice (PC-3) and fusion (PC-4)
are explicitly out of scope.

**Architecture:** `CognitiveController` already calls `active_person_resolver`
only from protected branches (`controller.py` — `_protected_household_plan`,
`_active_identity_plan`, `_own_children_plan`). Placing the face match inside a
new resolver makes camera inference free on every non-protected turn: the
frame is never decoded unless the intent is protected. The face resolver
produces evidence in-request — no token, no `IdentitySessionRegistry` entry —
because the frame and the question arrive together; there is nothing to
replay. Face resolution runs first (frictionless path); an unresolved face
falls through to the existing `OwnerRequestResolver` (PIN) unchanged. Two or
more detected faces is a terminal `AMBIGUOUS` denial — it does not fall
through to the PIN, because a stranger present during a PIN-authenticated
answer would still overhear it.

**Tech Stack:** Python 3.12, FastAPI/Pydantic V2, existing `vision/faces.py`
(InsightFace `buffalo_l`, ONNX/CPU, sqlite-vec KNN), existing
`cognition/identity.py` and `owner_authentication.py` seams, SQLite/aiosqlite,
pytest.

**Spec:** [Plan 0015 — Personal companion design](0015-personal-companion-design.md)
(PC-2), [ADR 0008 — Progressive owner authentication](../../adr/0008-progressive-owner-authentication.md),
[ADR 0009 — Locked posture and scoped capabilities](../../adr/0009-locked-posture-and-scoped-capabilities.md)

## Global Constraints

- Read `AGENTS.md`, Plan 0015 (PC-2/PC-3/PC-4 sections), ADR 0008, ADR 0009,
  Plan 0026 (the PIN pattern this plan mirrors), `vision/faces.py`,
  `vision/perception.py`, `cognition/identity.py`,
  `cognition/identity_sessions.py`, and `cognition/owner_authentication.py`
  completely before editing.
- Face evidence is evidence, never permission. `evaluate_authorization`
  remains the sole authorizer and is not modified by this plan.
- A non-protected turn never opens, decodes, or runs inference on an attached
  frame. This must be proven with an explicit test asserting the face model
  boundary is not invoked.
- No frame is ever persisted — only embeddings, exactly as `vision/faces.py`
  already does. No frame, embedding, PIN, or token may appear in any log or
  audit row.
- Zero faces or two-or-more faces in a frame resolve to `UNKNOWN` /
  `AMBIGUOUS` respectively and deny without disclosing that protected data
  exists. `AMBIGUOUS` is terminal — it does not fall through to the PIN
  resolver for the same request.
- Face evidence carries no persistent `authenticated = true` flag, global or
  per-person. It is produced fresh, in-request, and discarded after the turn.
- A face-authenticated grant authorizes exactly `personal_protected_read` +
  `child_data` — identical scope to the PIN grant in Plan 0026. It confers no
  memory-mutation, biometric-administration, home-control, or actuator
  capability.
- The PIN remains a complete, independent recovery path. Nothing in this plan
  may make face authentication the sole route to protected data.
- Enrollment requires a fresh, PIN-consumed `X-Iroko-Identity-Token`, is
  loopback-only (same origin check as `routers/auth.py`), and enrolls only the
  owner bound to that token — no `name` field, no third-party enrollment
  (that is PC-6, out of scope).
- Revoking face consent must purge `face_profiles` and `vec_faces` rows for
  that person in the same transaction — a real deletion, not a soft flag.
- The face-match authentication threshold is a new, separate setting from
  `settings.face_match_threshold` (the existing generic conversational match
  threshold, default 0.4) and must default stricter. Do not repurpose the
  existing setting.
- Both server (`FACE_AUTHENTICATION_ENABLED`) and robot
  (`ROBOT_FACE_AUTH_ENABLED`) default this feature to `false`. With the flag
  off, behavior must be byte-identical to current `main`.
- `POST /vision/enroll` remains quarantined (503,
  `_BIOMETRIC_ENROLLMENT_UNAVAILABLE`); its existing test
  (`tests/integration/test_vision_enroll_service.py`) must stay green
  unmodified.
- Do not touch `cognition/controller.py`, `cognition/authorization.py`,
  `cognition/household_tools.py`, `memory/policy_gated_v4_reader.py`,
  `cognition/owner_authentication.py`, `vision/perception.py`,
  `vision/faces.py`, `routers/chat.py`, or `routers/vision.py`. If any of
  these appears to need a change, stop and report — it signals the design
  drifted from this plan.
- No InsightFace model load in CI. Every face-related test uses synthetic
  embeddings against a disposable temp DB, following the existing pattern in
  `tests/integration/test_faces.py` (`_unit_vector()` helper).
- All public functions have complete type hints and Google docstrings.
- Use `apply_patch`; do not commit directly to `main`.
- Voice recognition, fusion, real-camera calibration/acceptance, and
  `/chat`/`/vision/respond` changes are explicitly out of scope for this
  plan.

---

## File map

| File | Responsibility |
|---|---|
| `server/src/server/memory/migration_007_biometric_consent.sql` | New: `face_consent_grants` table. |
| `server/src/server/db.py` | Register migration 007 only. |
| `server/src/server/memory/biometric_consent.py` | New: grant/revoke/read consent, purge profiles on revoke. |
| `server/src/server/cognition/identity.py` | Add `FACE` to trusted identified sources. |
| `server/src/server/cognition/face_authentication.py` | New: pure verdict function + request-scoped resolver + composition with the PIN resolver. |
| `server/src/server/settings.py`, `.env.example` | Face-auth threshold and opt-in flags. |
| `server/src/server/schemas_auth.py` | Enroll/revoke request/response contracts. |
| `server/src/server/routers/auth.py` | Face enrollment and revocation endpoints. |
| `server/src/server/routers/transcribe.py` | Optional `frame` field on classic and streaming; compose face + PIN resolvers. |
| `robot/src/robot/server_client.py` | Optional `frame` bytes on the transcribe multipart call. |
| `robot/src/robot/app.py`, `robot/src/robot/app_streaming.py`, `robot/src/robot/settings.py`, `.env.example` | Opt-in frame capture before each turn. |
| tests listed per task below | RED/GREEN and denial proof. |

No other production file is in scope.

---

### Task 1: Add biometric consent schema and repository

**Files:**

- Create: `server/src/server/memory/migration_007_biometric_consent.sql`
- Modify: `server/src/server/db.py`
- Create: `server/src/server/memory/biometric_consent.py`
- Create: `tests/integration/test_biometric_consent_schema.py`

**Interfaces:**

```python
async def grant_face_consent(person_entity_id: int) -> int: ...
async def revoke_face_consent(person_entity_id: int) -> None: ...
async def has_active_face_consent(person_entity_id: int) -> bool: ...
```

- [ ] **Step 1: Write RED tests**

Prove: migration creates `face_consent_grants` with a partial unique index on
`person_entity_id WHERE revoked_at IS NULL` (mirror
`migration_006_owner_credentials.sql`'s pattern); a second active grant for
the same person violates that index; `revoke_face_consent` purges every
`face_profiles` row (and the paired `vec_faces` row) for that person in the
same transaction; revoking twice is idempotent; `has_active_face_consent`
returns `False` after revocation.

- [ ] **Step 2: Observe RED**

```powershell
uv run pytest -n0 tests/integration/test_biometric_consent_schema.py -q
```

- [ ] **Step 3: Implement the migration and repository**

Follow `migration_006_owner_credentials.sql`'s column/index style. Purge logic
deletes `face_profiles` rows for the person, then their matching
`vec_faces` rows by `rowid`, inside one transaction alongside setting
`revoked_at`.

- [ ] **Step 4: Run focused tests**

```powershell
uv run pytest -n0 tests/integration/test_biometric_consent_schema.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add server/src/server/memory/migration_007_biometric_consent.sql server/src/server/db.py server/src/server/memory/biometric_consent.py tests/integration/test_biometric_consent_schema.py
git commit -m "feat(memory): add biometric consent grant/revoke with real purge"
```

---

### Task 2: Trust FACE as an identified evidence source

**Files:**

- Modify: `server/src/server/cognition/identity.py`
- Modify: `tests/unit/test_active_person_identity.py`

**Interfaces:**

```python
_TRUSTED_IDENTIFIED_SOURCES = frozenset(
    {IdentityEvidenceSource.MANUAL, IdentityEvidenceSource.LOCAL_UNLOCK, IdentityEvidenceSource.FACE}
)
```

- [ ] **Step 1: Write RED tests**

Prove: unexpired `FACE` evidence for a verified person resolves to
`IDENTIFIED`; expired `FACE` evidence resolves to `UNKNOWN`; `FACE` +
`LOCAL_UNLOCK` evidence pointing at different persons resolves to
`AMBIGUOUS`; `VOICE` and `CONTEXT` remain unresolved (they stay out of
`_RESOLVABLE_SOURCES` — PC-3/PC-4 territory). Confirm existing `LOCAL_UNLOCK`
tests from Plan 0026 remain green.

- [ ] **Step 2: Observe RED**

```powershell
uv run pytest -n0 tests/unit/test_active_person_identity.py -q
```

- [ ] **Step 3: Implement the minimal change**

Add `IdentityEvidenceSource.FACE` to `_TRUSTED_IDENTIFIED_SOURCES` in
`identity.py`. `FACE` is currently in the enum but outside
`_RESOLVABLE_SOURCES`, so it is silently ignored — this is the only line that
changes that.

- [ ] **Step 4: Run focused tests**

```powershell
uv run pytest -n0 tests/unit/test_active_person_identity.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add server/src/server/cognition/identity.py tests/unit/test_active_person_identity.py
git commit -m "feat(cognition): trust FACE evidence as identified"
```

---

### Task 3: Pure face verdict and request-scoped resolver

**Files:**

- Create: `server/src/server/cognition/face_authentication.py`
- Create: `tests/unit/test_face_authentication.py`
- Modify: `server/src/server/settings.py`, `.env.example`

**Interfaces:**

```python
class FaceAuthenticationVerdict(StrEnum):
    IDENTIFIED = "identified"
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"


def evaluate_face_authentication(
    *,
    detected_face_count: int,
    match: FaceMatch | None,
    consent_active: bool,
    role: HouseholdRole,
) -> FaceAuthenticationVerdict: ...


class FaceRequestResolver:
    consumed: bool

    async def resolve_actor(self, event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext: ...
    async def resolve_consent(self, event, actor) -> ConsentStatus: ...


def compose_face_then_pin_resolver(
    face: FaceRequestResolver, pin: OwnerRequestResolver
) -> tuple[ActivePersonResolver, ConsentResolver]: ...
```

New setting: `face_authentication_match_threshold` (stricter default than
`face_match_threshold`, e.g. `0.25`), separate from the existing generic
conversational threshold.

- [ ] **Step 1: Write RED tests for the pure verdict function**

Cover the full table with no I/O:

```text
0 faces                          -> UNKNOWN
2+ faces                         -> AMBIGUOUS
1 face, no match                 -> UNKNOWN
1 face, match, consent inactive  -> UNKNOWN
1 face, match, consent, non-owner role -> UNKNOWN
1 face, match, consent, owner role -> IDENTIFIED
```

- [ ] **Step 2: Write RED tests for `FaceRequestResolver`**

Using synthetic embeddings (per `test_faces.py`'s `_unit_vector()` pattern)
and injected boundaries (clock, consent reader, role reader, person reader,
face detect/match functions): prove lazy evaluation (frame is not decoded
until `resolve_actor` is first called), single-inference caching across two
calls in the same turn, no frame/embedding/token in `caplog`, and a
`VisionError` from the face pipeline degrading to `UNKNOWN` without raising.

- [ ] **Step 3: Write RED tests for the composed resolver**

Prove: a resolved `FACE` actor short-circuits — the PIN resolver's
`resolve_actor` is never awaited; an `AMBIGUOUS` face verdict also
short-circuits and denies without consulting the PIN (`OwnerRequestResolver`
not awaited); any other unresolved face verdict falls through to the PIN
resolver unchanged, preserving all Plan 0026/0027 behavior when no frame is
supplied.

- [ ] **Step 4: Observe RED**

```powershell
uv run pytest -n0 tests/unit/test_face_authentication.py -q
```

- [ ] **Step 5: Implement**

The pure function has no I/O. `FaceRequestResolver` wraps an optional frame,
calls `vision.faces.detect_faces` / `match_face` only on first
`resolve_actor` invocation, and caches the `ActivePersonContext` for the rest
of the turn. It produces `IdentityEvidence(source=FACE, ...)` in-memory only
— it must not call `IdentitySessionRegistry.issue_for_person` or any token
issuance path. `resolve_consent` returns `GRANTED` only after this exact
resolver produced an `IDENTIFIED` owner actor for this event.

- [ ] **Step 6: Run focused tests**

```powershell
uv run pytest -n0 tests/unit/test_face_authentication.py tests/unit/test_active_person_identity.py -q
```

- [ ] **Step 7: Commit**

```powershell
git add server/src/server/cognition/face_authentication.py server/src/server/settings.py .env.example tests/unit/test_face_authentication.py
git commit -m "feat(cognition): resolve owner identity from in-turn face evidence"
```

---

### Task 4: Authenticated face enrollment and revocation endpoints

**Files:**

- Modify: `server/src/server/schemas_auth.py`
- Modify: `server/src/server/routers/auth.py`
- Create: `tests/integration/test_owner_face_enrollment.py`

**Interfaces:**

```python
class FaceEnrollResponse(BaseModel):
    profile_id: int
    enrolled_at: datetime


POST /auth/owner/face/enroll   (loopback-only, requires X-Iroko-Identity-Token, multipart image)
  200 -> FaceEnrollResponse
  401 -> {"detail": "..."}   (absent/expired/consumed token)
  403 -> {"detail": "Local access only"}
  422 -> {"detail": "..."}   (no_face / multiple_faces / low_quality / face_too_small)

POST /auth/owner/face/revoke   (loopback-only, requires X-Iroko-Identity-Token)
  204
  401 -> {"detail": "..."}
  403 -> {"detail": "Local access only"}
```

- [ ] **Step 1: Write RED tests**

Assert: no token → 401 before the face model is touched; expired/consumed
token → 401; non-loopback → 403 before token verification;
`multiple_faces`/`low_quality`/`face_too_small`/`no_face` → 422 carrying the
rejection `code`, and nothing persisted; success grants consent (Task 1's
repository) and creates exactly one `face_profiles` row for the token's
owner, with no `name` field accepted anywhere in the request; revoke purges
consent and profiles; `POST /vision/enroll` still returns 503 with its
existing unmodified test green.

- [ ] **Step 2: Observe RED**

```powershell
uv run pytest -n0 tests/integration/test_owner_face_enrollment.py tests/integration/test_vision_enroll_service.py -q
```

- [ ] **Step 3: Implement**

Reuse `_is_loopback()` from `routers/auth.py`. Resolve the token via
`owner_unlock_service.for_request(token)` the same way Plan 0026's flow does,
requiring a consumed `PERSONAL_PROTECTED_READ`-equivalent grant scoped instead
to `ENROLL_BIOMETRIC` through `evaluate_authorization` (already covers owner +
consent in `_evaluate_sensitive_owner_action`). Delegate frame handling to the
existing `enroll_person()` in `vision/faces.py` unmodified, then call
`grant_face_consent()`.

- [ ] **Step 4: Run focused and regression tests**

```powershell
uv run pytest -n0 tests/integration/test_owner_face_enrollment.py tests/integration/test_owner_unlock_endpoint.py tests/integration/test_vision_enroll_service.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add server/src/server/schemas_auth.py server/src/server/routers/auth.py tests/integration/test_owner_face_enrollment.py
git commit -m "feat(api): add authenticated owner face enrollment and revocation"
```

---

### Task 5: Optional frame on classic and streaming transcribe

**Files:**

- Modify: `server/src/server/routers/transcribe.py`
- Modify: `server/src/server/schemas.py` (streaming `done` event payload if needed)
- Create: `tests/integration/test_face_authenticated_turn.py`

**Interfaces:**

```text
Optional multipart field: frame (JPEG/PNG/WebP/GIF/BMP, image contract)
Additive response field: identity_source: "face" | "local_unlock" | null
```

- [ ] **Step 1: Write RED scenarios**

Using a disposable DB with `apply_personal_setup()` and synthetic embeddings
enrolled directly via the Task 1 repository + `vision.faces.enroll_face()`:
owner's frame + protected question → exact `"Tus hijos son Máximo y
Dominga."` with no token/header at all; stranger's frame → non-disclosing
denial, `PolicyGatedV4Reader` never called; two faces in frame → denial;
generic question + owner frame → frame is never decoded (assert the face
detection boundary is not invoked); no frame at all → Plan 0026/0027 behavior
unchanged, byte-for-byte; `FACE_AUTHENTICATION_ENABLED=false` → frame field is
accepted but never inspected. Cover both classic `/transcribe` and
`/transcribe/stream`.

- [ ] **Step 2: Observe RED**

```powershell
uv run pytest -n0 tests/integration/test_face_authenticated_turn.py -q
```

- [ ] **Step 3: Implement**

Add an optional `frame: UploadFile | None` parameter, validated through the
existing `_read_contract_image()` pattern (mirror `routers/vision.py`,
duplicating the minimal validation call rather than importing the vision
router). Build a `FaceRequestResolver` from the frame (when
`settings.face_authentication_enabled` and a frame was supplied) and compose
it with the existing `OwnerRequestResolver` via
`compose_face_then_pin_resolver()`. Pass the composed resolver/consent pair
into `_voice_controller()` exactly where `request_identity` is passed today.
Add `identity_source` to `TranscribeResponse` and the streaming terminal
`done` event, populated only from which resolver actually produced the
`IDENTIFIED` actor — never a name or protected value.

- [ ] **Step 4: Run focused and full regression**

```powershell
uv run pytest -n0 tests/integration/test_face_authenticated_turn.py tests/integration/test_owner_authenticated_turn.py tests/integration/test_owner_authenticated_stream.py tests/integration/test_transcribe_pipeline.py tests/integration/test_transcribe_validation.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add server/src/server/routers/transcribe.py server/src/server/schemas.py tests/integration/test_face_authenticated_turn.py
git commit -m "feat(cognition): authorize protected turns from in-request face evidence"
```

---

### Task 6: Opt-in frame capture in the robot

**Files:**

- Modify: `robot/src/robot/server_client.py`
- Modify: `robot/src/robot/app.py`, `robot/src/robot/app_streaming.py`
- Modify: `robot/src/robot/settings.py`, `.env.example`
- Modify: `tests/unit/test_server_client.py`, `tests/unit/test_robot_app.py`

**Interfaces:**

```python
async def transcribe(
    audio: bytes, *, identity_token: str | None = None, frame: bytes | None = None
) -> TranscribeResult: ...
```

Setting: `ROBOT_FACE_AUTH_ENABLED=false`

- [ ] **Step 1: Write RED tests**

Prove: setting `false` never opens the camera and never attaches a `frame`
field; setting `true` captures via the existing `capture_frame()` (see
`robot/camera_capture.py`) through `asyncio.to_thread` before each transcribe
call and attaches it; a `CameraError` during capture degrades to sending the
turn without a frame — never raises, never blocks the turn; the frame bytes
are not logged.

- [ ] **Step 2: Observe RED**

```powershell
uv run pytest -n0 tests/unit/test_server_client.py tests/unit/test_robot_app.py -q
```

- [ ] **Step 3: Implement**

Add the optional `frame` keyword to `transcribe()`, attached to the multipart
body alongside `audio`. Capture happens in the app loop before calling
`transcribe()`, gated by the new setting, with the same fail-open-without-frame
posture the plan requires. Document the known latency cost (webcam open is
hundreds of ms per turn, since the robot cannot know in advance whether a
turn will be protected) as a code comment — do not attempt to solve it here;
real measurement is Plan 0030.

- [ ] **Step 4: Run focused tests**

```powershell
uv run pytest -n0 tests/unit/test_server_client.py tests/unit/test_robot_app.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add robot/src/robot/server_client.py robot/src/robot/app.py robot/src/robot/app_streaming.py robot/src/robot/settings.py .env.example tests/unit/test_server_client.py tests/unit/test_robot_app.py
git commit -m "feat(robot): capture opt-in frame for face-authenticated turns"
```

---

### Task 7: Close automated Plan 0029 gates

**Files:**

- Modify: `docs/architecture/current-state.md`
- Modify: `docs/roadmap/personal-companion-delivery-map.md`
- Modify: `docs/plans/README.md`
- Modify: `docs/plans/open/0029-consented-local-face-evidence.md`

- [ ] **Step 1: Run the complete focused security scenario**

```powershell
uv run pytest -n0 tests/integration/test_biometric_consent_schema.py tests/unit/test_active_person_identity.py tests/unit/test_face_authentication.py tests/integration/test_owner_face_enrollment.py tests/integration/test_face_authenticated_turn.py tests/unit/test_server_client.py tests/unit/test_robot_app.py -q
```

- [ ] **Step 2: Run PC-1 regression to prove the PIN path is untouched**

```powershell
uv run pytest -n0 tests/integration/test_owner_authenticated_turn.py tests/integration/test_owner_authenticated_stream.py tests/integration/test_vision_enroll_service.py tests/unit/test_cognitive_controller.py -q
```

- [ ] **Step 3: Run all repository gates**

```powershell
just lint
just typecheck
just test
just audit
just check
git diff --check
```

- [ ] **Step 4: Review threat cases**

Manually inspect tests/evidence for: unknown face, ambiguous (2+ faces)
terminal denial, revoked consent, non-owner role, expired evidence, no
frame supplied, flag-disabled parity with `main`, no camera decode on
non-protected turns, enrollment without a fresh token, enrollment
non-loopback, and no secret/embedding/frame in any log or audit row.

- [ ] **Step 5: Update documentation honestly**

Record automated evidence only. State explicitly in `current-state.md` that
this plan has no liveness/anti-spoofing defense — a photograph of the owner
held to the camera authenticates under this slice — and that the real
mitigation is PC-4 (voice fusion), planned but not yet built. State that
real-camera calibration and acceptance (threshold tuning, false accept/reject
rate, lighting, distance, glasses) remain open under Plan 0030.

- [ ] **Step 6: Request independent review**

Review identity/authentication/authorization separation, the face-then-PIN
precedence and AMBIGUOUS short-circuit, consent revocation's real purge,
secret/frame handling, lazy single-inference resolution, and the
server↔robot boundary. Resolve findings and rerun affected gates before
merge.

## Completion criteria

Plan 0029 is complete only when:

- with `FACE_AUTHENTICATION_ENABLED=true` and an enrolled, consented owner
  face, a protected question through a frame-carrying classic or streaming
  turn returns the exact confirmed child names with no PIN, no token, and no
  gesture;
- an unknown face, zero faces, two-or-more faces, revoked consent, or a
  non-owner role all deny without disclosure, and the v4 reader is never
  invoked;
- a non-protected turn never decodes an attached frame or invokes face
  detection, proven by an explicit test;
- revoking face consent leaves `face_profiles` and `vec_faces` empty for that
  person, verified against the database;
- the PIN path (Plans 0026/0027) passes unmodified — no test in those suites
  changes;
- with the flag off, behavior is identical to current `main`;
- the face grant authorizes only `personal_protected_read` + `child_data` —
  no mutation, biometric administration, or physical/digital action capability;
- no frame, embedding, PIN, or token appears in any log or audit row;
- full repository gates pass;
- `POST /vision/enroll` remains quarantined;
- the photo-spoofing limitation is recorded in `current-state.md`, not
  omitted;
- voice recognition, fusion, and real-camera acceptance remain explicitly
  open under PC-3, PC-4, and Plan 0030 respectively.
