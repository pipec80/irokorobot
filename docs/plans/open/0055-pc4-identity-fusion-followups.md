# PC-4 Identity Fusion Follow-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL — use
> `superpowers:executing-plans` and implement this plan task by task in one
> session. `superpowers:subagent-driven-development` is **not** the default here:
> Pipec's standing rule is no subagents unless he asks. Steps use checkbox
> (`- [ ]`) syntax for tracking. Work on **one simple branch from `main`** —
> never a git worktree, even if a skill suggests one — and open one PR at the
> end. Also required: `superpowers:test-driven-development` for every task, and
> `superpowers:verification-before-completion` before any claim that a task or
> the plan is done.

- **Status:** `Draft` — written 2026-09-30 after Plan 0054 (PC-4) closed, from the
  deferred findings of its independent review and from what Pipec's real-hardware run
  showed. Not executable until Pipec reads it and promotes it to `NOW`
  ([`docs/plans/README.md`](../README.md#operational-board) is empty today).
- **Roadmap row:** none of its own. It hardens the closed PC-4 row
  ([portfolio row 4](../../roadmap/cognitive-roadmap.md#canonical-pre-electronics-delivery-portfolio))
  and changes no product behavior Pipec has not decided (see the decisions below).
- **Evidence it builds on:** [Plan 0054](../completed/0054-face-default-identity-fusion.md),
  its *Independent review* section and its real-hardware outcomes.

**Goal:** Close the small, known weaknesses PC-4 left so they do not compound with the
first reserved capability: a database error during face recognition must deny quietly
instead of failing the turn; the first protected turn after a server start must not take
8 to 13 s; one definition for each value the code repeats; and two coverage holes
(another person's face against a real role row, and a vacuous test) closed.

**Architecture:** No new subsystem and no change to the identity rule. One `try/except` in
`FusedIdentityResolver` (fail closed), one `warm_up()` per heavy model called from the
existing application `lifespan` (behind the flags that already exist), and three
de-duplications. Everything else is tests and documentation.

**Tech Stack:** Python 3.12, FastAPI `lifespan`, aiosqlite, pytest with
`pytest-asyncio`, `uv` workspace. No new dependency.

**Spec:** [ADR 0016](../../adr/0016-face-and-voice-identity-fusion.md) (Accepted), as
clarified during Plan 0054; the findings themselves are recorded in
[Plan 0054's closure record](../completed/0054-face-default-identity-fusion.md#closure-record).
The plan argues from them; read both.

---

## Source of truth

Authority order, highest first: runtime `AGENTS.md`;
[`implementation-guardrails.md`](../../architecture/implementation-guardrails.md);
accepted ADRs [0004](../../adr/0004-local-first-cognitive-policy.md),
[0009](../../adr/0009-locked-posture-and-scoped-capabilities.md),
[0016](../../adr/0016-face-and-voice-identity-fusion.md);
[`current-state.md`](../../architecture/current-state.md);
[`identity-and-access.md`](../../architecture/identity-and-access.md);
[the roadmap](../../roadmap/cognitive-roadmap.md); then this plan.

Code and tests on `main` outrank any prose here. A contradiction stops the work and is
reported — it is never designed around.

## Required reading (after promotion, in this order)

1. `AGENTS.md` and `.claude/rules/` in full.
2. [`implementation-guardrails.md`](../../architecture/implementation-guardrails.md).
3. [ADR 0016](../../adr/0016-face-and-voice-identity-fusion.md) in full.
4. [Plan 0054](../completed/0054-face-default-identity-fusion.md): *Independent review*,
   *Rulings taken during execution* and *Real-hardware outcomes*.
5. Code, read before writing: `cognition/identity_fusion.py`,
   `cognition/face_authentication.py`, `vision/faces.py`, `voice/speaker_embedding.py`,
   `main.py`, `routers/transcribe.py`, `streaming.py`, `schemas.py`,
   `schemas_streaming.py`; tests `tests/unit/test_identity_fusion.py`,
   `tests/unit/test_app_lifecycle.py`, `tests/integration/test_identity_fusion_turn.py`,
   `tests/integration/test_speaker_evidence_turn.py`.

No item of `project-history/` is required reading.

---

## Re-audit record (2026-09-30, `main` at `e268d1c`)

| # | Finding | Evidence on `main` | Effect |
|---|---|---|---|
| R-1 | A database error while resolving a face is not caught | `FaceRequestResolver._detected_faces` catches only `VisionError`; `_match_when_singular` and `_identify` call `match_face`, `get_active_role`, `has_active_face_consent`, `get_person_label` bare | Task 1 |
| R-2 | The first protected turn loads two models | Hardware, 2026-09-30: 8 to 13 s for the first turn after a restart, 2.4 s afterwards; `vision/faces.py::_get_analyzer` and `voice/speaker_embedding.py::_load_encoder` are lazy | Task 2 |
| R-3 | `identity_source`'s literal is written five times | `schemas.py`, `schemas_streaming.py`, `streaming.py`, `routers/transcribe.py`, `cognition/identity_fusion.py` | Task 3 |
| R-4 | `FusedIdentityResolver.consumed` is unused in production | `_RequestIdentity.consumed` reads `self.pin.consumed` | Task 3 |
| R-5 | `_utc_now` is defined four times | `face_authentication.py`, `identity_fusion.py`, `owner_authentication.py`, `speaker_authentication.py` | Task 3 |
| R-6 | The other-person veto is tested only against doubles | `tests/unit/test_identity_fusion.py` and `test_face_authentication.py` use `AsyncMock` roles; no turn reads `household_role_assignments` | Task 4 |
| R-7 | A Plan 0053 test no longer tests anything | `test_a_backend_failure_does_not_fail_the_turn` posts no frame, so the speaker is never consulted | Task 4 |
| R-8 | A face matched to an entity with no role vetoes (and blocks the PIN) | `evaluate_face_authentication`: any role that is not `OWNER`, `UNKNOWN` included, returns `OTHER_PERSON` | Decision D-3: keep, document (Task 5) |

Nothing in the re-audit contradicts the closed plan or the ADR.

## Decisions taken (2026-09-30, Pipec)

| # | Decision |
|---|---|
| D-1 | A database error while resolving the face degrades to `unknown`: the turn continues as unidentified (generic denial), logs one warning carrying only the exception class, and never raises to the caller |
| D-2 | When `FACE_AUTHENTICATION_ENABLED` or `SPEAKER_AUTHENTICATION_ENABLED` is on, the matching model is loaded at server start, in the existing `lifespan`; a failed warm-up logs a warning and falls back to the lazy load. No new setting |
| D-3 | A matched face whose entity has no household role keeps vetoing (conservative); the operator manual documents it |
| D-4 | Whisper returning its own initial prompt from noise is **not** part of this plan; it gets its own plan |

---

## Global Constraints

Every task's requirements implicitly include this section.

- **API contract:** `POST /transcribe` and `/transcribe/stream` keep every field and value
  they have. **The generated OpenAPI must be byte-identical before and after** (Task 3
  proves it).
- **Audio contract:** WAV, 16 000 Hz, mono, signed int16, documented in every function that
  touches audio.
- **Fail closed:** a store error produces a non-identifying outcome; no path raises to the
  caller; no bare `except`; every `except` names its exceptions.
- **Privacy:** no name, transcript, distance or score reaches a log line; the new warning
  carries the exception class only.
- **Real household data never enters the repository.** Tests use canaries;
  `scripts/check_reserved_terms.py` passes on every commit.
- **Python style:** type hints on every signature, Google docstrings on public APIs,
  `logger` never `print`, `pathlib.Path` never `os.path`, no `Any` without a justification
  comment.
- **Commits:** Conventional Commits, title 72 characters or fewer, one commit per task,
  verified with `git log` after each one.
- **No new dependency, no new environment variable, no new setting.**
- No lint, type, coverage or security configuration is weakened to pass.
- **Nothing outside the file table below is modified.** A file the work turns out to need
  that is not listed stops the work and is reported.

## Review Focus

Failure modes no obvious test exercises, most likely first. Each has its test in the task
that owns the code.

1. **A store error must neither identify nor veto.** It degrades to `unknown` and a valid
   PIN token still works afterwards. *Task 1.*
2. **A failed warm-up must not stop the server or change any flag's meaning.** The model
   then loads lazily exactly as today. *Task 2.*
3. **With both flags off nothing is loaded at startup and `torch` and `insightface` are
   never imported.** *Task 2 (lifespan test) plus the existing subprocess import test.*
4. **The refactors must not change the OpenAPI or the meaning of `authentication_consumed`.**
   *Task 3.*
5. **The veto of another person must hold against a real role row, with and without that
   person's consent, and must not spend a PIN token.** *Task 4.*

---

## Non-goals

- Liveness, anti-replay defence, or any new biometric factor.
- Changing the fusion table, any threshold, or any rule of ADR 0016.
- Whisper's prompt echo on noise (D-4).
- A store-error guard for the PIN resolver: it reads the database only when a token is
  presented, and Plan 0051 reworks that path.
- Merging the three private `_unknown_active_person` helpers.
- The privacy contract of the robot's senses and the onboarding load (Paso 0) — separate
  decisions and plans.

## File structure

**Create**

| File | Single responsibility |
|---|---|
| `server/src/server/cognition/clock.py` | `utc_now()`, the one production clock of the cognition layer |
| `tests/unit/test_cognition_clock.py` | Task 3 |
| `tests/unit/test_identity_source_contract.py` | Task 3 |
| `tests/unit/test_model_warm_up.py` | Task 2 |

**Modify**

| File | Change |
|---|---|
| `server/src/server/cognition/identity_fusion.py` | Store-error guard; import `IdentitySource` and `utc_now` |
| `server/src/server/cognition/face_authentication.py`, `owner_authentication.py`, `speaker_authentication.py` | Use `utc_now` |
| `server/src/server/vision/faces.py`, `server/src/server/voice/speaker_embedding.py` | `warm_up()` |
| `server/src/server/main.py` | Warm-up step in `lifespan` |
| `server/src/server/schemas.py`, `schemas_streaming.py`, `streaming.py`, `routers/transcribe.py` | One `IdentitySource`; `_RequestIdentity.consumed` from the fused resolver |
| `tests/unit/test_identity_fusion.py`, `tests/unit/test_app_lifecycle.py`, `tests/integration/test_identity_fusion_turn.py`, `tests/integration/test_speaker_evidence_turn.py` | As each task states |
| `docs/runbooks/operator-manual.md`, `docs/architecture/current-state.md`, `docs/plans/README.md`, `docs/plans/open/README.md`, `docs/plans/completed/README.md`, this plan | Closure documentation |
| `docs/architecture/diagrams/current-state.{json,html}` | Regenerated with Archify after `current-state.md` changes |

**Never touched:** `cognition/identity.py`, `cognition/authorization.py`, `voice/voiceprints.py`,
`memory/`, `robot/src/`, `scripts/`, `pyproject.toml`, `uv.lock`.

---

## Task 0: Freeze the base and re-verify the re-audit

**Files:** none. No code in this task.

- [ ] **Step 1: Branch from an up-to-date `main`**

```bash
git checkout main && git pull --ff-only
git checkout -b feat/0055-pc4-followups
```

- [ ] **Step 2: Re-verify the load-bearing findings**

```bash
grep -n "def warm_up" server/src/server/vision/faces.py server/src/server/voice/speaker_embedding.py
grep -rn "def _utc_now" server/src | wc -l
grep -n "_STORE_ERRORS" server/src/server/cognition/identity_fusion.py
```

Expected: the first prints nothing, the second prints `4`, the third prints nothing. **Any
mismatch stops the plan and is reported to Pipec — it is not worked around.**

- [ ] **Step 3: Confirm the green baseline**

Run: `just gate`
Expected: PASS. Record the test count; later tasks grow from it.

---

## Task 1: A store error during face recognition degrades to `unknown`

**Files:**
- Modify: `server/src/server/cognition/identity_fusion.py`
- Test: `tests/unit/test_identity_fusion.py`, `tests/integration/test_identity_fusion_turn.py`

**Interfaces:**
- Consumes: `FaceRequestResolver.resolve_actor` (may raise `BrainMemoryError` or
  `aiosqlite.Error`), `OwnerRequestResolver` (unchanged).
- Produces: `FusedIdentityResolver.resolve_actor` never raises those two; on such an error
  it logs `Face identity degraded to unknown: <ExceptionClass>`, leaves `source` as `None`
  and ends with `FusionReason.NO_EVIDENCE` (or `PIN` when a valid token follows).

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_identity_fusion.py` add `import aiosqlite` (third-party block) and
`from server.exceptions import BrainMemoryError`, then give the face helper an optional
error for the role read. Replace the nested `read_role` and the signature of
`_face_resolver`:

```python
def _face_resolver(
    *,
    faces: int = 1,
    role: HouseholdRole = HouseholdRole.OWNER,
    matches: bool = True,
    store_error: Exception | None = None,
) -> FaceRequestResolver:
    """A real FaceRequestResolver over doubles: `faces` detected, a close match or none.

    `store_error`, when given, is raised by the role read — the identity store failing.
    """

    async def detect(_frame: bytes) -> list[DetectedFace]:
        return [
            DetectedFace(embedding=np.zeros(512, dtype=np.float32), score=0.9, width=200.0)
        ] * faces

    async def match(_embedding: np.ndarray) -> FaceMatch | None:
        if not matches:
            return None
        return FaceMatch(entity_id=_OWNER_ID, name="Canary", distance=0.1)

    async def read_role(_person_id: int) -> HouseholdRole:
        if store_error is not None:
            raise store_error
        return role
```

(leave `read_person`, `read_consent` and the `FaceRequestResolver(...)` call as they are).
Append:

```python
@pytest.mark.parametrize("error", [aiosqlite.Error("db down"), BrainMemoryError("db down")])
async def test_a_store_error_in_face_resolution_degrades_to_unknown(
    error: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    """Review Focus 1: the store failing neither identifies nor vetoes, and never raises."""
    factory = _verified()
    fused = _fused(face=_face_resolver(store_error=error), speaker_factory=factory)
    event = _event()

    with caplog.at_level(logging.WARNING):
        actor = await fused.resolve_actor(event)

    assert actor.status is ActivePersonStatus.UNKNOWN
    assert fused.source is None
    assert fused.last_reason is FusionReason.NO_EVIDENCE
    assert factory.owner_ids == []
    assert await fused.resolve_consent(event, actor) is ConsentStatus.NOT_REQUIRED
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any(type(error).__name__ in message for message in warnings)
    assert all("db down" not in message for message in warnings)


async def test_a_store_error_in_the_face_still_lets_a_valid_pin_token_through() -> None:
    """The face says nothing, so the PIN path is still consulted."""
    pin = _pin(with_token=True)
    fused = _fused(face=_face_resolver(store_error=aiosqlite.Error("db down")), pin=pin.resolver)

    actor = await fused.resolve_actor(_event())

    assert actor.status is ActivePersonStatus.IDENTIFIED
    assert fused.last_reason is FusionReason.PIN
    assert fused.source == "local_unlock"
```

In `tests/integration/test_identity_fusion_turn.py` add `import aiosqlite` (third-party
block) and append:

```python
@pytest.mark.integration
async def test_a_store_error_in_face_resolution_denies_instead_of_failing_the_turn(
    fusion_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review Focus 1, end to end: a generic denial, never a 500, and no voice work."""
    _detect(monkeypatch, [_detected(_OWNER_FACE)])
    monkeypatch.setattr(
        face_auth_module, "get_active_role", AsyncMock(side_effect=aiosqlite.Error("db down"))
    )
    embed = _embed(monkeypatch, _MATCHING_VOICE)
    _mock_stt_tts(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe", files=_files())

    body = response.json()
    assert response.status_code == 200
    assert "Joaquín" not in body["llm_response"]
    assert body["identity_source"] is None
    embed.assert_not_awaited()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_identity_fusion.py tests/integration/test_identity_fusion_turn.py -q -n0 -p no:cacheprovider`
Expected: FAIL — the new unit tests raise `aiosqlite.Error` / `BrainMemoryError` out of
`resolve_actor`, and the integration test errors with the unhandled `aiosqlite.Error`.

- [ ] **Step 3: Implement**

In `server/src/server/cognition/identity_fusion.py` add `import aiosqlite` (third-party
block), `from server.exceptions import BrainMemoryError`, and after `logger = ...`:

```python
# The identity store failing is not evidence of anything: the face then says nothing.
_STORE_ERRORS = (BrainMemoryError, aiosqlite.Error)
```

Replace `_resolve` with these two methods (the body of the old face branch moves into
`_resolve_face` unchanged, plus the guard):

```python
async def _resolve(self, event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
    """Run face, then voice, then PIN, stopping at the first identification or veto."""
    face_outcome = await self._resolve_face(event)
    if face_outcome is not None:
        return face_outcome
    pin_context = await self._pin.resolve_actor(event)
    if self._pin.consumed:
        self.last_reason = FusionReason.PIN
        self.source = "local_unlock"
    else:
        self.last_reason = FusionReason.NO_EVIDENCE
    return pin_context


async def _resolve_face(self, event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext | None:
    """Return the face path's final context, or `None` to fall through to the PIN."""
    if self._face is None:
        return None
    try:
        face_context = await self._face.resolve_actor(event)
    except _STORE_ERRORS as exc:
        # Fail closed: neither a veto nor an identification, and nothing personal logged.
        logger.warning("Face identity degraded to unknown: %s", type(exc).__name__)
        return None
    verdict = self._face.last_verdict
    if verdict is FaceAuthenticationVerdict.AMBIGUOUS:
        self.last_reason = FusionReason.VETO_MULTIPLE_FACES
        return face_context
    if verdict is FaceAuthenticationVerdict.OTHER_PERSON:
        self.last_reason = FusionReason.VETO_OTHER_PERSON
        return face_context
    if face_context.status is ActivePersonStatus.IDENTIFIED:
        return await self._with_voice(event, face_context)
    return None
```

Also extend the module docstring's last sentence of the first paragraph with: "A store error
while resolving the face degrades to unknown."

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_identity_fusion.py tests/integration/test_identity_fusion_turn.py -q -n0 -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Run the wider checks**

Run: `uv run ruff check --fix server tests && uv run ruff format server tests && uv run mypy --config-file=pyproject.toml server/src robot/src && uv run pyright && uv run pytest tests/unit tests/integration/test_face_authenticated_turn.py tests/integration/test_identity_fusion_turn.py -q -p no:cacheprovider`
Expected: clean and green.

- [ ] **Step 6: Commit**

```bash
git add server/src/server/cognition/identity_fusion.py tests/unit/test_identity_fusion.py tests/integration/test_identity_fusion_turn.py
git commit -m "fix(cognition): degrade a face store error to unknown"
git log -1 --pretty=%s
```

---

## Task 2: Warm the face and speaker models at startup

**Files:**
- Modify: `server/src/server/vision/faces.py`, `server/src/server/voice/speaker_embedding.py`,
  `server/src/server/main.py`
- Create: `tests/unit/test_model_warm_up.py`
- Test: `tests/unit/test_app_lifecycle.py`

**Interfaces:**
- Produces: `faces.warm_up() -> None` (async; raises `VisionError`),
  `speaker_embedding.warm_up() -> None` (async; raises `SpeakerBackendError`), and a `lifespan`
  that awaits them only when `cfg.face_authentication_enabled` / `cfg.speaker_authentication_enabled`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_model_warm_up.py
"""The two heavy identity models expose a warm-up that loads them off the event loop (Plan 0055)."""

import pytest
from server.vision import faces
from server.voice import speaker_embedding
from server.voice.speaker_embedding import SpeakerBackendError


async def test_face_warm_up_loads_the_analyzer_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(faces, "_get_analyzer", lambda: calls.append(1))

    await faces.warm_up()

    assert calls == [1]


async def test_speaker_warm_up_loads_the_encoder_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(speaker_embedding, "_load_encoder", lambda: calls.append(1))

    await speaker_embedding.warm_up()

    assert calls == [1]


async def test_speaker_warm_up_retypes_any_load_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom() -> None:
        raise RuntimeError("yaml parse error")

    monkeypatch.setattr(speaker_embedding, "_load_encoder", _boom)

    with pytest.raises(SpeakerBackendError):
        await speaker_embedding.warm_up()
```

Append to `tests/unit/test_app_lifecycle.py` (add `import logging` and
`from unittest.mock import AsyncMock` to its imports; `VisionError` from
`server.exceptions`):

```python
def _quiet_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "memory_enabled", False)
    monkeypatch.setattr(main.stt, "preload", lambda: None)
    monkeypatch.setattr(main.tts, "preload", lambda: None)


@pytest.mark.unit
async def test_lifespan_warms_the_models_whose_flags_are_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _quiet_startup(monkeypatch)
    monkeypatch.setattr(settings, "face_authentication_enabled", True)
    monkeypatch.setattr(settings, "speaker_authentication_enabled", True)
    face_warm = AsyncMock()
    speaker_warm = AsyncMock()
    monkeypatch.setattr(main.faces, "warm_up", face_warm)
    monkeypatch.setattr(main.speaker_embedding, "warm_up", speaker_warm)

    async with lifespan(app):
        assert app.state.ready is True

    face_warm.assert_awaited_once()
    speaker_warm.assert_awaited_once()


@pytest.mark.unit
async def test_lifespan_loads_nothing_when_both_flags_are_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review Focus 3: the flag-off server never touches either model."""
    _quiet_startup(monkeypatch)
    monkeypatch.setattr(settings, "face_authentication_enabled", False)
    monkeypatch.setattr(settings, "speaker_authentication_enabled", False)
    face_warm = AsyncMock()
    speaker_warm = AsyncMock()
    monkeypatch.setattr(main.faces, "warm_up", face_warm)
    monkeypatch.setattr(main.speaker_embedding, "warm_up", speaker_warm)

    async with lifespan(app):
        pass

    face_warm.assert_not_awaited()
    speaker_warm.assert_not_awaited()


@pytest.mark.unit
async def test_a_failed_warm_up_does_not_stop_the_server(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Review Focus 2: the model then loads lazily, exactly as it did before."""
    _quiet_startup(monkeypatch)
    monkeypatch.setattr(settings, "face_authentication_enabled", True)
    monkeypatch.setattr(settings, "speaker_authentication_enabled", True)
    monkeypatch.setattr(main.faces, "warm_up", AsyncMock(side_effect=VisionError("model missing")))
    monkeypatch.setattr(
        main.speaker_embedding, "warm_up", AsyncMock(side_effect=SpeakerBackendError("no model"))
    )

    with caplog.at_level(logging.WARNING):
        async with lifespan(app):
            assert app.state.ready is True

    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("Face model warm-up failed" in m for m in messages)
    assert any("Speaker model warm-up failed" in m for m in messages)
```

(`SpeakerBackendError` is imported from `server.voice.speaker_embedding`.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_model_warm_up.py tests/unit/test_app_lifecycle.py -q -n0 -p no:cacheprovider`
Expected: FAIL — `module 'server.vision.faces' has no attribute 'warm_up'`.

- [ ] **Step 3: Implement**

In `vision/faces.py`, after `detect_faces`:

```python
async def warm_up() -> None:
    """Load the face model on the executor thread so the first turn does not pay for it.

    Raises:
        VisionError: If insightface or its models cannot be loaded.
    """
    await run_in_executor_with_context(_executor, _get_analyzer)
```

In `voice/speaker_embedding.py`, after `embed_wav`'s helpers (next to `_run_bounded`):

```python
async def warm_up() -> None:
    """Load the speaker model on the embedding worker so the first turn does not pay for it.

    Raises:
        SpeakerBackendError: If the model cannot be loaded. The load cool-down of
            `_load_encoder` then applies to the first real turn.
    """
    try:
        await run_in_executor_with_context(_executor, _load_encoder)
    except SpeakerBackendError:
        raise
    except Exception as exc:  # noqa: BLE001 -- same deliberate re-typing as `_embed_sync`
        raise SpeakerBackendError("Speaker model warm-up failed") from exc
```

In `main.py`: add `Awaitable, Callable` to the `collections.abc` import, and
`from server.exceptions import VisionError`, `from server.vision import faces`,
`from server.voice import speaker_embedding` to the first-party imports. Add the helper above
`lifespan`:

```python
async def _warm_up(name: str, load: Callable[[], Awaitable[None]]) -> None:
    """Load one optional model at startup; a failure only moves its cost to the first turn."""
    try:
        await load()
    except (VisionError, speaker_embedding.SpeakerBackendError) as exc:
        logger.warning("%s warm-up failed; it will load on first use: %s", name, exc)
```

and in `lifespan`, right after `tts.preload()`:

```python
        if cfg.face_authentication_enabled:
            await _warm_up("Face model", faces.warm_up)
        if cfg.speaker_authentication_enabled:
            await _warm_up("Speaker model", speaker_embedding.warm_up)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_model_warm_up.py tests/unit/test_app_lifecycle.py tests/integration/test_speaker_evidence_turn.py -q -n0 -p no:cacheprovider`
Expected: all pass, including `test_importing_the_app_never_loads_the_speaker_stack`.

- [ ] **Step 5: Run the wider checks**

Run: `uv run ruff check --fix server tests && uv run ruff format server tests && uv run mypy --config-file=pyproject.toml server/src robot/src && uv run pyright && uv run pytest tests/unit tests/integration/test_speaker_evidence_turn.py -q -p no:cacheprovider`
Expected: clean and green.

- [ ] **Step 6: Commit**

```bash
git add server/src/server/vision/faces.py server/src/server/voice/speaker_embedding.py server/src/server/main.py tests/unit/test_model_warm_up.py tests/unit/test_app_lifecycle.py
git commit -m "feat(server): warm the face and speaker models at startup"
git log -1 --pretty=%s
```

---

## Task 3: One definition for the repeated values

**Files:**
- Create: `server/src/server/cognition/clock.py`, `tests/unit/test_cognition_clock.py`,
  `tests/unit/test_identity_source_contract.py`
- Modify: `schemas.py`, `schemas_streaming.py`, `streaming.py`, `routers/transcribe.py`,
  `cognition/identity_fusion.py`, `cognition/face_authentication.py`,
  `cognition/owner_authentication.py`, `cognition/speaker_authentication.py`

**Interfaces:**
- Produces: `server.schemas.IdentitySource = Literal["face", "face_voice", "local_unlock"]`;
  `server.cognition.clock.utc_now() -> datetime`; `_RequestIdentity(resolve_actor,
  resolve_consent, fused)` whose `consumed` is `fused.consumed`.

`IdentitySource` lives in `schemas.py`, not in `cognition`: importing any `server.cognition.*`
module runs the package `__init__`, which imports the memory layer, which imports
`server.schemas` (for `EntityType`) — a cycle. `schemas.py` is the existing leaf for such aliases.

- [ ] **Step 1: Capture the OpenAPI before any change**

```bash
uv run python -c "import json; from server.main import app; open('openapi-before.json','w').write(json.dumps(app.openapi(), sort_keys=True))"
```

Expected: `openapi-before.json` exists in the repository root (it is deleted in Step 6 and never
committed).

- [ ] **Step 2: Write the failing tests**

```python
# tests/unit/test_identity_source_contract.py
"""`identity_source` has exactly one definition, shared by every place that types it (Plan 0055)."""

from typing import get_args, get_type_hints

from server import streaming
from server.schemas import IdentitySource, TranscribeResponse
from server.schemas_streaming import StreamDoneEvent


def test_identity_source_lists_the_three_evidence_sources() -> None:
    assert get_args(IdentitySource) == ("face", "face_voice", "local_unlock")


def test_every_identity_source_annotation_comes_from_that_definition() -> None:
    expected = {*get_args(IdentitySource), type(None)}
    for model in (TranscribeResponse, StreamDoneEvent):
        annotation = model.model_fields["identity_source"].annotation
        assert set(get_args(annotation)) == expected
    hint = get_type_hints(streaming.stream_response_plan)["identity_source"]
    assert set(get_args(hint)) == expected
```

```python
# tests/unit/test_cognition_clock.py
"""The cognition layer has one production clock (Plan 0055)."""

from datetime import UTC

from server.cognition import (
    clock,
    face_authentication,
    identity_fusion,
    owner_authentication,
    speaker_authentication,
)


def test_utc_now_is_aware_and_utc() -> None:
    assert clock.utc_now().utcoffset() == UTC.utcoffset(None)


def test_no_module_keeps_its_own_copy() -> None:
    for module in (
        face_authentication,
        identity_fusion,
        owner_authentication,
        speaker_authentication,
    ):
        assert not hasattr(module, "_utc_now")
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_identity_source_contract.py tests/unit/test_cognition_clock.py -q -n0 -p no:cacheprovider`
Expected: FAIL — `cannot import name 'IdentitySource' from 'server.schemas'` and
`cannot import name 'clock'`.

- [ ] **Step 4: Implement**

1. `schemas.py`, next to `EntityType`:

```python
# Which evidence identified the actor of a turn (Plan 0054, ADR 0016). Defined once and
# shared by the response schemas, the streaming renderer and the fusion resolver.
IdentitySource = Literal["face", "face_voice", "local_unlock"]
```

   and change the field to `identity_source: IdentitySource | None = Field(...)` (keep its
   `default` and `description`).
2. `schemas_streaming.py`: `from server.schemas import IdentitySource`, same field change.
3. `streaming.py`: import `IdentitySource` from `server.schemas`; the parameter becomes
   `identity_source: IdentitySource | None = None`.
4. `routers/transcribe.py`: import `IdentitySource` from `server.schemas` (join the existing
   `from server.schemas import TranscribeResponse, error_responses`); `_RequestIdentity` becomes

```python
@dataclass
class _RequestIdentity:
    """Uniform per-request actor/consent resolver over the fused identity evidence.

    Attributes:
        resolve_actor: The actor resolver to hand to the controller.
        resolve_consent: The matching consent resolver.
        fused: The fusion resolver, the source of `.consumed` and `.identity_source`.
    """

    resolve_actor: ActivePersonResolver
    resolve_consent: ConsentResolver
    fused: FusedIdentityResolver

    @property
    def consumed(self) -> bool:
        """Whether this request consumed a fresh one-use owner PIN unlock grant."""
        return self.fused.consumed

    @property
    def identity_source(self) -> IdentitySource | None:
        """Which evidence identified the actor, or `None` for none."""
        return self.fused.source
```

   and `_build_request_identity` returns `_RequestIdentity(resolve_actor=fused.resolve_actor,
   resolve_consent=fused.resolve_consent, fused=fused)` (the local `pin` stays only to build
   `fused`). Drop the now-unused `Literal` and `OwnerRequestResolver` imports if `ruff` reports them.
5. `cognition/identity_fusion.py`: delete `type IdentitySource = ...` and the `Literal` import;
   `from server.schemas import IdentitySource`.
6. Create the clock:

```python
# server/src/server/cognition/clock.py
"""The one production clock of the cognition layer (Plan 0055)."""

from datetime import UTC, datetime

__all__ = ["utc_now"]


def utc_now() -> datetime:
    """Return the current aware UTC timestamp for production boundaries."""
    return datetime.now(UTC)
```

   In the four modules delete `_utc_now`, import `from server.cognition.clock import utc_now`,
   and replace each `_utc_now` use with `utc_now`; let `ruff check --fix` drop unused `UTC` /
   `datetime` imports.

- [ ] **Step 5: Run the tests and prove nothing observable changed**

```bash
uv run pytest tests/unit/test_identity_source_contract.py tests/unit/test_cognition_clock.py -q -n0 -p no:cacheprovider
uv run python -c "import json; from server.main import app; open('openapi-after.json','w').write(json.dumps(app.openapi(), sort_keys=True))"
python -c "import sys; a=open('openapi-before.json').read(); b=open('openapi-after.json').read(); sys.exit(0 if a==b else 1)"
echo "openapi-identical=$?"
uv run ruff check --fix server tests && uv run ruff format server tests && uv run mypy --config-file=pyproject.toml server/src robot/src && uv run pyright
uv run pytest -n auto -q -p no:cacheprovider
```

Expected: the new tests pass, `openapi-identical=0`, everything clean, and the **whole** suite
passes — `authentication_consumed` keeps its meaning (`test_owner_authenticated_turn.py`,
`test_owner_authenticated_stream.py`, `test_identity_fusion_turn.py`).

- [ ] **Step 6: Commit**

```bash
rm openapi-before.json openapi-after.json
git add server tests
git commit -m "refactor(cognition): define identity source and clock once"
git log -1 --pretty=%s
git status --short
```

Expected: a clean tree (neither JSON file is tracked).

---

## Task 4: Close the two coverage holes

**Files:**
- Test: `tests/integration/test_identity_fusion_turn.py`, `tests/integration/test_speaker_evidence_turn.py`

**Interfaces:** consumes `upsert_entity`, `assign_household_role`, `enroll_face`,
`grant_face_consent`; produces no production change.

- [ ] **Step 1: Write the test that pins the veto against a real role row**

In `tests/integration/test_identity_fusion_turn.py` add to the imports
`from server.cognition.identity import HouseholdRole, PersonRecord` (extend the existing
`identity` import), `from server.memory.declarative import upsert_entity` and
`assign_household_role` to the `household_authorization` import. Append:

```python
@pytest.mark.integration
@pytest.mark.parametrize("other_consents", [True, False])
async def test_another_enrolled_person_vetoes_against_a_real_role_row(
    fusion_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, other_consents: bool
) -> None:
    """Review Focus 5: a real adult's face vetoes, consent or not, and spends no token."""
    other_id = await upsert_entity(name="Canary Adult", type="person")
    await assign_household_role(
        person_entity_id=other_id,
        role=HouseholdRole.ADULT,
        grantor_entity_id=fusion_db.owner_entity_id,
    )
    if other_consents:
        await grant_face_consent(other_id)
    await enroll_face(other_id, _STRANGER_FACE, label="Canary Adult")
    service = _service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    embed = _embed(monkeypatch, _MATCHING_VOICE)
    _mock_stt_tts(monkeypatch)
    headers = {"X-Iroko-Identity-Token": unlock.token}

    _detect(monkeypatch, [_detected(_STRANGER_FACE)])
    async with _client() as client:
        vetoed = await client.post("/transcribe", headers=headers, files=_files())
        alone = await client.post("/transcribe", headers=headers, files=_files(with_frame=False))

    assert "Joaquín" not in vetoed.json()["llm_response"]
    assert vetoed.json()["identity_source"] is None
    assert vetoed.json()["authentication_consumed"] is False
    assert alone.json()["identity_source"] == "local_unlock"
    embed.assert_not_awaited()
```

- [ ] **Step 2: Run it and prove it bites**

Run: `uv run pytest tests/integration/test_identity_fusion_turn.py -q -n0 -p no:cacheprovider -k real_role_row`
Expected: PASS (this characterizes behavior that already exists). Then **mutate**: in
`face_authentication.evaluate_face_authentication` change the non-owner branch to
`return FaceAuthenticationVerdict.UNKNOWN`, rerun, and confirm both parametrized cases FAIL
(the vetoed turn falls through to the PIN and answers). Restore the line and rerun to see PASS.

- [ ] **Step 3: Remove the vacuous test**

In `tests/integration/test_speaker_evidence_turn.py` delete
`test_a_backend_failure_does_not_fail_the_turn` (its turn posts no frame, so the speaker is
never consulted; the real behavior is pinned by
`test_a_dead_speaker_backend_does_not_fail_the_face_turn` in `test_identity_fusion_turn.py`),
then let `ruff check --fix` drop the imports it leaves unused.

- [ ] **Step 4: Run the affected suites**

Run: `uv run ruff check --fix server tests && uv run ruff format server tests && uv run mypy --config-file=pyproject.toml server/src robot/src && uv run pyright && uv run pytest tests/integration/test_identity_fusion_turn.py tests/integration/test_speaker_evidence_turn.py -q -p no:cacheprovider`
Expected: clean and green.

- [ ] **Step 5: Commit**

```bash
git add tests
git commit -m "test(cognition): pin the other-person veto to a real role row"
git log -1 --pretty=%s
```

---

## Task 5: Documentation closure

**Files:** see the Modify table's docs rows. No code.

- [ ] **Step 1:** `operator-manual.md`: in *Tier 4* replace the first-turn-latency sentence with
  the startup warm-up (the two models load when the server starts while their flags are on; a
  failed warm-up falls back to the lazy load); add that a database error while resolving the face
  now denies with `no_evidence` and one warning instead of an error; add (D-3) that a face matched
  to an entity with no household role also vetoes and the PIN cannot bypass it, so such a profile
  is fixed through local administration.
- [ ] **Step 2:** `current-state.md`: extend the *Identity fusion* row with Plan 0055's four
  changes and their measured evidence; remove the first-turn-latency remark from the verification
  bullets if it is now false.
- [ ] **Step 3:** `docs/plans/README.md` (`NOW` empty again, a `CLOSED` row for 0055, a dependency
  row), `docs/plans/open/README.md`, `docs/plans/completed/README.md`; move this plan to
  `completed/` and fix its relative links; record the closure in this plan.
- [ ] **Step 4:** Regenerate the architecture diagram with the Archify skill (`validate` then
  `deliver`, from `.claude/skills/archify`, POSIX paths) because `current-state.md` changed.
- [ ] **Step 5:** `uv run ruff format --check .`, `uv run ruff check .`,
  `uv run python scripts/check_reserved_terms.py`, and a mechanical link/anchor check on the
  touched docs.
- [ ] **Step 6: Commit** — `docs(plan): document the pc-4 follow-ups`.

---

## Task 6: Verification, review and closure

- [ ] **Step 1:** `just gate`. Expected: PASS, test count grown by the new tests, coverage at or
  above the floor. If the `audit` step fails on a newly published advisory of a transitive
  dependency, stop and ask Pipec; do not bump a lock on your own.
- [ ] **Step 2: Optional hardware check (Pipec only).** With both flags on, restart
  `just run-server` and watch the startup log show the face and speaker models loading; then ask
  one protected question. Record only the outcome (first protected turn faster than 8 s, or not).
  An agent never claims it.
- [ ] **Step 3:** Independent whole-branch review with `superpowers:requesting-code-review`;
  resolve findings with `superpowers:receiving-code-review`. Pipec decides whether it is a
  subagent or his own reading.
- [ ] **Step 4:** `superpowers:finishing-a-development-branch`. One PR, squash-merge, branch deleted.

---

## What an agent may never do in this plan

- Record, capture, request, imitate, synthesize, clone or replay a human voice or face, or touch
  the microphone or the webcam.
- Copy a frame, audio, embedding, score or real name into a tracked file, a fixture, a commit
  message or a document. Test data is generated in code.
- Claim the optional hardware check without Pipec having run and reported it.
- Weaken a veto, a threshold, `_RESOLVABLE_SOURCES` semantics or any authorization rule to make a
  test pass, or change a dependency lock without Pipec's say.

---

## Verification commands

```powershell
just gate
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest tests/integration/test_api_contract.py
uv run pytest tests/integration/test_face_authenticated_turn.py   # must pass unedited
uv run python scripts/check_reserved_terms.py
uv lock --check
git diff --check
```

```bash
grep -rn "def _utc_now" server/src
grep -n "Literal\[\"face\", \"face_voice\", \"local_unlock\"\]" -r server/src
```

Expected: the first prints nothing; the second prints exactly one line, in `schemas.py`.

## Completion criteria

1. Every task's RED test was observed failing first (Task 3's refactor and Task 4's coverage test
   use the characterization nets named in their steps), and all gates above are green with no
   configuration weakened.
2. `tests/integration/test_face_authenticated_turn.py` passes unedited.
3. A store error during face recognition yields a generic denial and one warning carrying only
   the exception class; it never raises, never identifies and never vetoes; a valid PIN token
   still works.
4. With the flags on, the models load at startup and a failed warm-up only logs; with the flags
   off nothing is loaded and `torch` / `insightface` are never imported.
5. The generated OpenAPI is byte-identical before and after; `authentication_consumed` and
   `identity_source` keep their meaning.
6. The other-person veto is pinned against a real role row, with and without consent, and spends
   no token; the vacuous Plan 0053 test is gone.
7. `_utc_now` exists nowhere; `IdentitySource` has one definition.
8. Documentation states what changed and what stays open: replay and liveness undefended, no
   reserved capability yet, Whisper's prompt echo in its own plan, PIN scoping in Plan 0051.

## Rollback boundary

There is no flag and no migration. The changes are a `try/except`, two startup loads behind
existing flags, three de-duplications and tests. Rolling back means reverting the PR.

## Risks

| Risk | Why it matters | Mitigation |
|---|---|---|
| Warm-up slows server start by a few seconds | Pipec restarts the server often while developing | It only runs with the identity flags on; the gain is a first protected turn near 2.4 s instead of 8 to 13 s |
| A failed speaker warm-up starts the 60 s load cool-down | The first real turn within a minute of a failed start is refused as `unavailable` | The failure was real (model missing); the turn degrades to `basic` exactly as today |
| `schemas.py` gaining an alias used by the cognition layer | A cognition module importing the API schemas module | `memory/` already imports `EntityType` from it; `schemas.py` stays a leaf |
| Catching store errors could hide a real bug | A broken database would look like "unknown" | One warning per occurrence names the exception class; the error types are the two the repositories raise, not `Exception` |

## Self-review record (2026-09-30)

1. **Spec coverage.** The ADR's fail-closed rule → Task 1; R-2 (hardware evidence) → Task 2;
   R-3 to R-5 → Task 3; R-6, R-7 → Task 4; R-8 and the operator-facing changes → Task 5. Every
   decision D-1 to D-4 has a task or a stated exclusion.
2. **Placeholder scan.** Task 5 lists documentation edits by target and content; every code step
   shows code.
3. **Type consistency.** `IdentitySource` (Task 3) is what `FusedIdentityResolver.source`,
   `_RequestIdentity.identity_source` and `stream_response_plan` use; `warm_up` (Task 2) is what
   `lifespan` awaits; `_STORE_ERRORS` (Task 1) is the only new exception tuple.
4. **Review Focus.** All five entries have an owning task and a named test.

## Execution handoff

Plan written under `docs/plans/open/` — the project's plan location, which overrides the skill's
default path. It is `Draft` until Pipec reads it and promotes it to `NOW`.

**Recommended execution approach: Native** — `superpowers:executing-plans`, one agent in a fresh
Claude Code session, with an independent whole-branch review at the end. There are five small
tasks, only Tasks 1 and 4 share a file, and a shipped mistake is contained: the identity rule does
not change and every behavior added is either a fail-closed guard or a startup convenience.
