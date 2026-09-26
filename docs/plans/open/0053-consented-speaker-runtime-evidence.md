# Consented Speaker Runtime Evidence Implementation Plan (PC-3B)

> **For agentic workers:** REQUIRED SUB-SKILL — use
> `superpowers:executing-plans` and implement this plan task by task in one
> session. `superpowers:subagent-driven-development` is **not** the default
> here: Pipec's standing rule is no subagents unless he asks for them. Steps
> use checkbox (`- [ ]`) syntax for tracking. Work on **one simple branch from
> `main`** — never a git worktree, even if a skill suggests one — and open one
> PR at the end. Also required: `superpowers:test-driven-development` for every
> task, and `superpowers:verification-before-completion` before any claim that
> a task or the plan is done.

- **Status:** `Ready` — **promoted to `NOW` by Pipec on 2026-09-25**, after he
  answered every decision below. It is the single executable plan; no other
  plan under `open/` may be started while this one is open.
- **Roadmap row:** [PC-3B](../../roadmap/cognitive-roadmap.md#canonical-pre-electronics-delivery-portfolio),
  step 1 of the [agreed delivery order](../../roadmap/cognitive-roadmap.md#pre-purchase-readiness-gate--plug-it-in-and-it-works).
- **Evidence it builds on:** [Plan 0047](../completed/0047-speaker-evidence-calibration-study.md#study-result-and-closure-record-2026-09-25)
  (PC-3A, provisional PASS, merged as PR #134 / `de4c6cf`).

**Goal:** Let the owner enrol their voice locally and consentedly so a
protected turn produces typed, untrusted `VOICE` identity evidence with an
explicit verdict, and so revocation really deletes the voiceprint.

**Architecture:** A request-scoped speaker resolver mirrors the Plan 0029 face
resolver: a pure verdict table decides from pre-computed inputs, a lazy adapter
runs at most one CPU embedding per request, and the result is attached as
`IdentityEvidence(source=VOICE)`. `VOICE` is absent from `_RESOLVABLE_SOURCES`,
so the evidence cannot identify anybody or widen access — fusion is PC-4.
Enrolment and revocation are loopback-only endpoints behind a fresh
PIN-consumed grant, exactly like `/auth/owner/face/*`. Everything sits behind
`SPEAKER_AUTHENTICATION_ENABLED`, default `false`.

**Tech Stack:** Python 3.12, FastAPI with `Annotated` style, Pydantic v2,
aiosqlite, NumPy, SpeechBrain `1.1.1` `EncoderClassifier` (ECAPA, revision
`0f99f2d0…`, Apache-2.0) on CPU torch, `uv` workspace, pytest with
`pytest-asyncio`.

**Spec:** [Plan 0015 — personal companion design, PC-3](0015-personal-companion-design.md#pc-3--speaker-evidence--pc-3a-closed-pc-3b-unplanned),
with the roadmap row as its one-line contract and
[ADR 0015](../../adr/0015-owner-grant-scope-and-speaker-binding.md) decision 2
bounding it.

---

## Source of truth

Authority order, highest first: runtime `AGENTS.md`;
[`implementation-guardrails.md`](../../architecture/implementation-guardrails.md);
accepted ADRs [0004](../../adr/0004-local-first-cognitive-policy.md),
[0006](../../adr/0006-personal-and-family-companion-profiles.md),
[0008](../../adr/0008-progressive-owner-authentication.md),
[0009](../../adr/0009-locked-posture-and-scoped-capabilities.md),
[0015](../../adr/0015-owner-grant-scope-and-speaker-binding.md);
[`current-state.md`](../../architecture/current-state.md);
[`identity-and-access.md`](../../architecture/identity-and-access.md);
[the roadmap](../../roadmap/cognitive-roadmap.md); then this plan.

Code and tests on `main` outrank any prose here. A contradiction stops the work
and is reported — it is never designed around.

## Required reading (after promotion, in this order)

1. `AGENTS.md` and `.claude/rules/` in full.
2. [`implementation-guardrails.md`](../../architecture/implementation-guardrails.md).
3. [ADR 0008](../../adr/0008-progressive-owner-authentication.md) and
   [ADR 0009](../../adr/0009-locked-posture-and-scoped-capabilities.md).
4. [ADR 0015](../../adr/0015-owner-grant-scope-and-speaker-binding.md),
   decision 2 in full — speaker *binding*, the face veto and liveness are PC-4.
5. [ADR 0006](../../adr/0006-personal-and-family-companion-profiles.md) — face
   and voice are never the sole recovery route.
6. [`identity-and-access.md`](../../architecture/identity-and-access.md):
   *Separate concepts*, *Progressive authentication*, *Identity evidence*.
7. [`current-state.md`](../../architecture/current-state.md): the rows
   *Consented local face evidence (Plan 0029 / PC-2)* and *Speaker recognition*.
8. [Plan 0047](../completed/0047-speaker-evidence-calibration-study.md): the
   *Frozen readiness contract*, the *Study result and closure record*, the
   *Task 7 review record*.
9. [Plan 0029](../completed/0029-consented-local-face-evidence.md) — the
   structural template this plan mirrors.
10. Code, read before writing: `cognition/identity.py`,
    `cognition/face_authentication.py`, `routers/auth.py`,
    `routers/transcribe.py`, `memory/biometric_consent.py`,
    `memory/migration_007_biometric_consent.sql`, `db.py`, `vision/faces.py`,
    `settings.py`, `audio_contract.py`, `scripts/speaker_calibration_backend.py`.

No item of `project-history/` is required reading. The 85 MB study model cache
that lives there is an artifact, not a source of truth.

---

## Re-audit record (2026-09-25)

Queue rule 4/6: the row's assumptions were re-checked against merged code, not
memory. The row's **product outcome does not change** — local enrolment,
consent, revocation and verification produce typed `VOICE` evidence; missing,
weak or failed evidence stays `unknown` and grants no capability. What changed
is the cost and the shape of the work.

| # | Finding | Evidence on `main` | Effect on the row |
|---|---|---|---|
| R-1 | PC-3A is **merged**, not pending | `de4c6cf` (PR #134), then `db9b65b` (#135) and `751ce46` (#136) | Five documents said "PR pending / unmerged branch"; corrected when this plan landed |
| R-2 | `VOICE` is not merely untrusted, it is **unresolvable** | `cognition/identity.py:147-154` — `_RESOLVABLE_SOURCES` is `{MANUAL, LOCAL_UNLOCK, FACE, SESSION}`; `tests/unit/test_active_person_identity.py:438` pins that `VOICE` for a verified person resolves to `UNKNOWN` | **No change to `resolve_active_person`.** Attaching `VOICE` evidence cannot widen access by construction, and that test stays green and unedited |
| R-3 | The consent pattern exists but is face-shaped | `migration_007_biometric_consent.sql` and `memory/biometric_consent.py` (idempotent grant; revoke purges `face_profiles` + `vec_faces` in one transaction) | Mirrorable, not reusable: its `CHECK` and its purge target are face-only (D-2) |
| R-4 | The biometric-admin endpoint pattern exists | `routers/auth.py` — loopback check, fresh PIN-consumed token, `ENROLL_BIOMETRIC` + `DataSensitivity.BIOMETRIC` through `evaluate_authorization`, audited, always the token's own owner | Mirror it exactly, including the ordering risk in D-7 |
| R-5 | The runtime does not hold the audio when it builds the identity resolver | `routers/transcribe.py:410-413` (classic) and `:534-537` (streaming): `_build_request_identity(...)` runs **before** `_read_audio_upload(audio)` | A small, real refactor the row did not anticipate (Task 6) |
| R-6 | The audio contract already delivers what a verifier needs | Both turn endpoints receive WAV 16 kHz mono int16; `audio_contract.validate_wav_contract` exists | **No new multipart field and no response change on the turn endpoints.** Only enrolment needs a new endpoint |
| R-7 | The frozen backend is a **dev** dependency | `pyproject.toml:72-75` — `speechbrain`, `torch`, `torchaudio` in `[dependency-groups] dev`; `server/pyproject.toml` does not list them | Hundreds of MB move into the server package, and `pip-audit` still cannot audit the local `+cpu` builds (D-3) |
| R-8 | The model identity is frozen in a **script** constant | `scripts/speaker_calibration_backend.py` calls it the one sanctioned exception, *for the study* | Runtime may not hardcode a model name (`AGENTS.md`). Precedent: `settings.face_model` (D-4) |
| R-9 | The cached model lives in gitignored history | `project-history/calibration/speaker/model-cache/`, about 85 MB | Runtime must not read from `project-history/`; the face precedent uses `MODELS_DIR` (D-4) |
| R-10 | The threshold is provisional and in-sample | 0.4834; FRR 0/24 is zero **by construction**; one owner, four impostors, no held-out data; separation 0.342; replay 6/8 accepted | Default-off flag and a "provisional" comment are mandatory (D-5) |
| R-11 | Latency is fine in the frozen protocol, not free in the hot path | p95 231 ms frozen protocol; p50 431 / p95 536 ms per real 4–5 s clip on a loaded laptop | At most one embedding per request, never on the public path (D-6) |
| R-12 | ADR-0015 keeps binding out of this plan | ADR-0015 decision 2 | `compose_face_then_pin_resolver`'s precedence is untouched; `identity_source` keeps its shape (D-8) |
| R-13 | Found in passing: runbook drift | The operator manual documented `FACE_AUTHENTICATION_MATCH_THRESHOLD` as `0.25`; `settings.py:153` and `.env.example` say `0.5815` since Plan 0030 | Corrected when this plan landed |
| R-14 | One owner, by design | The face verdict requires `HouseholdRole.OWNER`; one active grant per person; the calibration measured one owner | PC-3B stays single-owner; multi-member voice is PC-6 |

Nothing in the re-audit contradicts the row or the ADRs.

## Decisions taken (2026-09-25, Pipec)

Pipec accepted every recommendation of the re-audit. These are now constraints,
not options.

| # | Decision | Taken |
|---|---|---|
| D-1 | Proceed with PC-3B despite the provisional, in-sample calibration | **Yes.** PC-3B grants nothing, so the provisional threshold cannot cause a disclosure on its own; replay and liveness stay PC-4's gate |
| D-2 | Where the voiceprint and its consent live | **New tables in migration 008**, mirroring 003 + 007, no data migration. Refined while writing the tasks and **confirmed by Pipec on 2026-09-25**: no `vec0` virtual table — see [Why no vec0 table](#why-no-vec0-table) |
| D-3 | `torch` + `speechbrain` as server runtime dependencies | **Yes**, behind the existing `pytorch-cpu` index, with a lazy import so a server with the flag off never loads them |
| D-4 | Model identity and cache location | **`Settings`**, never a runtime constant; cache under `MODELS_DIR/speechbrain`; **copy** the existing 85 MB study cache instead of re-downloading, so first boot is offline |
| D-5 | Threshold and reference-set policy | **0.4834 as a default-off provisional value**, marked in-sample at the setting itself; **minimum 3 references** before verification is attempted; a held-out genuine check during acceptance |
| D-6 | When the embedding is computed | **Only** when the flag is on, the turn reaches a protected branch, and no face or PIN evidence already identified the actor; at most once per request; never on the public path |
| D-7 | Ordering against Plan 0051 (ADR-0015 scope) | **Keep the agreed order.** Both new routes carry an explicit ADR-0015 marker so Plan 0051 picks them up |
| D-8 | Observability of the verdict | **Log and audit only.** No wire change: a client must not be told that voice authenticated a turn before PC-4 exists |

### Why no vec0 table

The measured threshold 0.4834 is a cosine distance **to the centroid of the
L2-normalized references**, not to the nearest single reference. A `vec0` KNN
returns the nearest neighbour, which is a different quantity and would silently
break the threshold's provenance. With one enrolled person and a handful of
references, the centroid is computed in NumPy from vectors stored as a `BLOB`
column, which reproduces the study's arithmetic exactly. `sqlite-vec` stays the
baseline for face recognition and semantic memory, where nearest-neighbour
search over many rows is the actual need. Pipec confirmed this on 2026-09-25; a `vec0` table
would change Task 1 and nothing else, and is not what we are building.

---

## Global Constraints

Every task's requirements implicitly include this section.

- **Audio contract, never deviated:** WAV, 16 000 Hz, mono, signed int16.
  Documented in the docstring of every function that touches audio.
- **API contract:** `POST /transcribe` keeps
  `{ text_heard, llm_response, audio_base64, duration_ms, emotion }` plus the
  fields already added by Plans 0026–0029. Adding a field is allowed; this plan
  adds none to existing routes.
- **Frozen backend (Plan 0047, block 1):** `speechbrain==1.1.1`
  `EncoderClassifier`, source `speechbrain/spkrec-ecapa-voxceleb`, revision
  `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`, device CPU, 192-d embeddings,
  preprocessing `samples.astype(np.float32) / 32768.0`, offline after cache.
- **Threshold:** `0.4834` cosine distance to the reference centroid, provisional
  and in-sample. A sample matches when `distance <= threshold`.
- **Minimum references:** 3. **Minimum enrolment audio:** 2.0 s.
  **Maximum:** `settings.max_audio_duration_s` (30.0 s today).
- **Flag:** `SPEAKER_AUTHENTICATION_ENABLED`, default `false`. With it off, the
  backend module is never imported and no behaviour changes.
- **Privacy:** no audio is ever persisted by the server. A stored voiceprint is
  a vector. No name, transcript, distance or score reaches a log line, an audit
  row or a response body.
- **Real household data never enters the repository.** Tests use synthetic,
  deterministically generated audio and invented canaries.
  `scripts/check_reserved_terms.py` passes on every commit.
- **Fail closed:** every failure produces `unknown`; no path raises to the
  caller; no bare `except`; every `except` names its exception and preserves
  the cause.
- **Python style:** type hints on every signature, Google docstrings on public
  APIs, `logger` never `print`, `pathlib.Path` never `os.path`, `Annotated`
  FastAPI style, no `Any` without a justification comment.
- **Commits:** Conventional Commits, title 72 characters or fewer, one commit
  per task, verified with `git log` after each one.
- No dependency or environment variable beyond the ones this plan names.
- No lint, type, coverage or security configuration is weakened to pass.

## Review Focus

Five failure modes the spec implies that no obvious task test would exercise,
most likely to bite first. Each one's test is assigned to the task that owns
the code, and appears there in that task's own step style.

1. **A format-perfect but nearly silent WAV.** Silence embeds to a vector like
   any other, and nothing in the audio contract rejects it. A near-silent turn
   must never verify. *Test owned by Task 3 (energy gate) and Task 5
   (enrolment rejects it with 422).*
2. **Verification against a voiceprint produced by a different model.** If the
   configured model or revision changes, every stored vector becomes
   meaningless but still numerically comparable. *Test owned by Task 1
   (`model_id` stored) and Task 4 (a foreign `model_id` yields `UNKNOWN`).*
3. **Revocation racing a turn in flight.** A turn can read references, then the
   owner revokes before the comparison completes. The turn must resolve
   `unknown`, not verify against purged data. *Test owned by Task 4.*
4. **Model files present but corrupt or half-downloaded.** The loader raises
   something the adapter did not anticipate, and a 500 escapes to the caller
   instead of a degraded turn. *Test owned by Task 3.*
5. **The enrolled person stops being the owner.** A role change after enrolment
   must take effect on the next turn, so the role is re-read every turn and
   never cached across requests. *Test owned by Task 4.*

---

## Non-goals

- Making `VOICE` trusted, resolvable, or capable of identifying the actor.
  `_RESOLVABLE_SOURCES` is not edited.
- Fusing voice with face or PIN, or changing
  `compose_face_then_pin_resolver`'s precedence — PC-4 owns fusion.
- Binding a grant to the speaker, vetoing the PIN fallback, or adding
  liveness/anti-replay defence — ADR-0015 decision 2 and PC-4.
- Implementing the ADR-0015 `OwnerUnlockScope` — Plan 0051.
- Changing the audio contract, the `/transcribe` request or response shape, or
  any existing status code.
- Diarization, wake word, multi-speaker segmentation, or any second speaker.
- Enrolling anybody except the token's own owner; any family/multi-member path
  (PC-6).
- Touching `scripts/speaker_calibration*` or re-running the calibration.
- Any cloud provider anywhere (ADR-0004).

## File structure

Nothing outside this list may be created or modified. A file the
implementation turns out to need that is not listed stops the work and is
reported.

**Create**

| File | Single responsibility |
|---|---|
| `server/src/server/memory/migration_008_voice_consent.sql` | `voice_consent_grants` and `voice_profiles` |
| `server/src/server/memory/voice_consent.py` | Grant, revoke-and-purge, read consent |
| `server/src/server/voice/__init__.py` | Package marker, no logic |
| `server/src/server/voice/voiceprints.py` | Store references, count them, compute the centroid distance |
| `server/src/server/voice/speaker_embedding.py` | The only place the runtime loads the model |
| `server/src/server/cognition/speaker_authentication.py` | Pure verdict table plus the request-scoped resolver |
| `scripts/speaker_auth_demo.py` | Local enrol/revoke helper over loopback HTTP |
| `tests/integration/test_voice_consent_schema.py` | Task 1 |
| `tests/unit/test_speaker_authentication.py` | Tasks 2 and 4 |
| `tests/unit/test_speaker_embedding.py` | Task 3 |
| `tests/slow/test_speaker_embedding_real_model.py` | Task 3, `slow` marker |
| `tests/integration/test_owner_voice_enrollment.py` | Task 5 |
| `tests/integration/test_speaker_evidence_turn.py` | Task 6 |

**Modify**

| File | Change |
|---|---|
| `server/src/server/db.py` | One `_MIGRATIONS` entry |
| `server/src/server/settings.py` | Six settings, added by the task that needs each |
| `server/src/server/schemas_auth.py` | `VoiceEnrollResponse` |
| `server/src/server/routers/auth.py` | Two routes |
| `server/src/server/routers/transcribe.py` | Composition order plus the flagged resolver |
| `server/pyproject.toml`, `pyproject.toml`, `uv.lock` | Dependency move (D-3) |
| `.env.example`, `justfile` | Configuration and one recipe |
| `docs/architecture/current-state.md`, `docs/architecture/identity-and-access.md`, `docs/runbooks/operator-manual.md`, `docs/roadmap/cognitive-roadmap.md`, `docs/roadmap/personal-companion-delivery-map.md`, `docs/plans/README.md`, `docs/plans/open/README.md`, this plan | Closure documentation |
| `docs/architecture/diagrams/current-state.{json,html}` | Regenerated with the Archify skill after `current-state.md` changes |

**Never touched:** `scripts/speaker_calibration*.py`,
`cognition/identity.py`, `tests/unit/test_active_person_identity.py`,
`vision/`, `robot/src/`, `cognition/authorization.py`,
`cognition/owner_authentication.py`.

---

## Task 0: Freeze the base and re-verify the re-audit

**Files:** none. No code in this task.

- [ ] **Step 1: Branch from an up-to-date `main`**

```bash
git checkout main && git pull --ff-only
git checkout -b feat/0053-speaker-runtime-evidence
```

- [ ] **Step 2: Re-verify the four load-bearing findings**

```bash
grep -n "_RESOLVABLE_SOURCES = " server/src/server/cognition/identity.py
grep -n "speechbrain==1.1.1" server/pyproject.toml pyproject.toml
grep -n "request_identity = _build_request_identity\|audio_bytes = await _read_audio_upload" server/src/server/routers/transcribe.py
grep -n "_MODEL_REVISION" scripts/speaker_calibration_backend.py
```

Expected: `VOICE` absent from `_RESOLVABLE_SOURCES`; `speechbrain` only in the
root `pyproject.toml`; `_build_request_identity` before `_read_audio_upload` in
both routes; the model revision still a script constant. **Any mismatch stops
the plan and is reported to Pipec — it is not worked around.**

- [ ] **Step 3: Confirm the green baseline before changing anything**

Run: `just gate`
Expected: PASS. Record the test count; it is the number later tasks grow from.

---

## Task 1: Migration 008, consent and voiceprint storage

**Files:**
- Create: `server/src/server/memory/migration_008_voice_consent.sql`
- Create: `server/src/server/memory/voice_consent.py`
- Create: `server/src/server/voice/__init__.py`, `server/src/server/voice/voiceprints.py`
- Modify: `server/src/server/db.py` (`_MIGRATIONS`)
- Modify: `server/src/server/settings.py` (`speaker_model`, `speaker_model_revision`)
- Test: `tests/integration/test_voice_consent_schema.py`

**Interfaces:**
- Consumes: `server.db.transaction`, `server.db.get_conn`,
  `server.memory.declarative.upsert_entity` (tests only).
- Produces:
  - `grant_voice_consent(person_entity_id: int) -> int`
  - `revoke_voice_consent(person_entity_id: int) -> None`
  - `has_active_voice_consent(person_entity_id: int) -> bool`
  - `enroll_voiceprint(entity_id: int, embedding: np.ndarray, label: str, model_id: str) -> int`
  - `count_voiceprints(entity_id: int, model_id: str) -> int`
  - `centroid_distance(entity_id: int, embedding: np.ndarray, model_id: str) -> float | None`
  - `VOICEPRINT_DIM: Final = 192`

- [ ] **Step 1: Write the failing schema and repository tests**

```python
# tests/integration/test_voice_consent_schema.py
"""Integration tests for voice consent and voiceprint storage (Plan 0053,
Task 1) — real temp DB, synthetic vectors, no speaker model involved."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import numpy as np
import pytest
from server.memory.declarative import upsert_entity
from server.memory.voice_consent import (
    grant_voice_consent,
    has_active_voice_consent,
    revoke_voice_consent,
)
from server.settings import settings
from server.voice.voiceprints import (
    VOICEPRINT_DIM,
    centroid_distance,
    count_voiceprints,
    enroll_voiceprint,
)

from server import db

MODEL_ID = "test-model@rev1"


@pytest.fixture
async def memory_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[misc]
    """Provide a clean temporary DB (runs all migrations) for each test."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "test.db")
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield
    await db.close_db()
    db._conn = None


def _unit_vector(axis: int) -> np.ndarray:
    """Return a 192-d L2-normalized vector along *axis* — a synthetic voice."""
    vector = np.zeros(VOICEPRINT_DIM, dtype=np.float32)
    vector[axis] = 1.0
    return vector


async def test_grant_is_idempotent(memory_db: None) -> None:
    person = await upsert_entity(name="canary-owner", entity_type="person")
    first = await grant_voice_consent(person)
    second = await grant_voice_consent(person)
    assert first == second
    assert await has_active_voice_consent(person) is True


async def test_revoke_purges_every_voiceprint(memory_db: None) -> None:
    person = await upsert_entity(name="canary-owner", entity_type="person")
    await grant_voice_consent(person)
    await enroll_voiceprint(person, _unit_vector(0), "canary-owner", MODEL_ID)
    await enroll_voiceprint(person, _unit_vector(1), "canary-owner", MODEL_ID)

    await revoke_voice_consent(person)

    assert await has_active_voice_consent(person) is False
    assert await count_voiceprints(person, MODEL_ID) == 0


async def test_revoke_is_idempotent_without_a_grant(memory_db: None) -> None:
    person = await upsert_entity(name="canary-owner", entity_type="person")
    await revoke_voice_consent(person)  # must not raise
    assert await has_active_voice_consent(person) is False


async def test_vectors_from_another_model_are_not_counted(memory_db: None) -> None:
    """Review Focus 2: a model change must invalidate stored references."""
    person = await upsert_entity(name="canary-owner", entity_type="person")
    await enroll_voiceprint(person, _unit_vector(0), "canary-owner", MODEL_ID)
    assert await count_voiceprints(person, "other-model@rev2") == 0
    assert await centroid_distance(person, _unit_vector(0), "other-model@rev2") is None


async def test_centroid_distance_matches_the_study_arithmetic(memory_db: None) -> None:
    person = await upsert_entity(name="canary-owner", entity_type="person")
    await enroll_voiceprint(person, _unit_vector(0), "canary-owner", MODEL_ID)
    await enroll_voiceprint(person, _unit_vector(1), "canary-owner", MODEL_ID)

    # Centroid of two orthogonal unit vectors, L2-normalized, is 45 degrees
    # from each: cosine similarity sqrt(0.5), so distance 1 - sqrt(0.5).
    distance = await centroid_distance(person, _unit_vector(0), MODEL_ID)
    assert distance == pytest.approx(1.0 - 0.5**0.5, abs=1e-6)


async def test_centroid_distance_is_none_without_references(memory_db: None) -> None:
    person = await upsert_entity(name="canary-owner", entity_type="person")
    assert await centroid_distance(person, _unit_vector(0), MODEL_ID) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/integration/test_voice_consent_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.memory.voice_consent'`.

- [ ] **Step 3: Write the migration**

```sql
-- server/src/server/memory/migration_008_voice_consent.sql
-- Migration 8 — consented speaker evidence (Plan 0053, PC-3B).
-- Mirrors migration 003 (face profiles) and 007 (face consent).
-- voice_consent_grants records an explicit, revocable consent to use a
-- person's voice as identity evidence. Only ONE active (unrevoked) grant may
-- exist per person, and revoking it must purge every voice_profiles row for
-- that person — see server/src/server/memory/voice_consent.py.
-- A voiceprint is a 192-d float32 ECAPA embedding, L2-normalized, stored as a
-- BLOB: verification compares against the CENTROID of the references, which is
-- what Plan 0047 measured, not a nearest-neighbour search. No audio is ever
-- stored. model_id pins the frozen model@revision that produced the vector;
-- vectors from any other model are ignored, never silently compared.

CREATE TABLE IF NOT EXISTS voice_consent_grants (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    person_entity_id    INTEGER NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
    purpose             TEXT NOT NULL CHECK (purpose = 'speaker_evidence'),
    granted_at          TEXT NOT NULL DEFAULT (datetime('now')),
    revoked_at          TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS voice_consent_grants_active_idx
ON voice_consent_grants (person_entity_id)
WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS voice_profiles (
    id          INTEGER PRIMARY KEY,
    entity_id   INTEGER NOT NULL REFERENCES entities(id),
    label       TEXT NOT NULL,
    embedding   BLOB NOT NULL,
    model_id    TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_voice_profiles_entity ON voice_profiles(entity_id);
```

- [ ] **Step 4: Register the migration**

In `server/src/server/db.py`, append one line to `_MIGRATIONS`:

```text
    (7, "migration_007_biometric_consent.sql"),
    (8, "migration_008_voice_consent.sql"),          <- new line
```

- [ ] **Step 5: Write the consent repository**

`server/src/server/memory/voice_consent.py` is `memory/biometric_consent.py`
with three differences: the table is `voice_consent_grants`, `_PURPOSE` is
`"speaker_evidence"`, and the purge deletes `voice_profiles` rows (there is no
`vec_` table to clean). Keep the module docstring, the Google docstrings, the
`db.transaction()` usage and the `logger.info` lines in the same shape — the
face module is the reference implementation, and a reviewer will diff them.

```python
_PURPOSE = "speaker_evidence"


async def revoke_voice_consent(person_entity_id: int) -> None:
    """Revoke consent and purge every stored voiceprint for this person.

    Sets ``revoked_at`` on the active grant AND deletes every
    ``voice_profiles`` row for *person_entity_id*, inside one transaction.
    Idempotent — no active grant and no rows is not an error.

    Args:
        person_entity_id: Person whose consent and voiceprints are purged.

    Raises:
        BrainMemoryError: If the DB is unavailable.
    """
    async with db.transaction() as conn:
        await conn.execute("DELETE FROM voice_profiles WHERE entity_id = ?", (person_entity_id,))
        await conn.execute(
            "UPDATE voice_consent_grants SET revoked_at = datetime('now') "
            "WHERE person_entity_id = ? AND revoked_at IS NULL",
            (person_entity_id,),
        )
    logger.info("Voice consent revoked and voiceprints purged: person=%s", person_entity_id)
```

- [ ] **Step 6: Write the voiceprint store**

```python
# server/src/server/voice/voiceprints.py
"""Local voiceprint storage and centroid comparison (Plan 0053, PC-3B).

A voiceprint is a 192-d float32 ECAPA embedding, L2-normalized, stored as a
BLOB in ``voice_profiles``. Verification compares a fresh embedding with the
CENTROID of that person's references, because that is the quantity Plan 0047
calibrated (threshold 0.4834). No audio is ever stored, and no vector produced
by a different model is ever compared.
"""

from typing import Final

import numpy as np

from server import db
from server.db import get_conn
from server.exceptions import BrainMemoryError

VOICEPRINT_DIM: Final = 192

__all__ = ["VOICEPRINT_DIM", "centroid_distance", "count_voiceprints", "enroll_voiceprint"]


def _pack(embedding: np.ndarray) -> bytes:
    """Serialize a voiceprint as float32 little-endian, like ``vision.faces``."""
    return embedding.astype(np.float32).tobytes()


def _unpack(blob: bytes) -> np.ndarray:
    """Read one stored voiceprint back into a 1-D float32 array."""
    return np.frombuffer(blob, dtype=np.float32)


def _l2_normalized(vector: np.ndarray) -> np.ndarray:
    """Return *vector* scaled to unit length, exactly as the study did."""
    norm = float(np.linalg.norm(vector))
    if norm == 0.0:
        raise BrainMemoryError("Refusing to store or compare an all-zero voiceprint")
    return (vector / norm).astype(np.float32)


async def enroll_voiceprint(
    entity_id: int, embedding: np.ndarray, label: str, model_id: str
) -> int:
    """Store one reference voiceprint for *entity_id*.

    Several references per person are expected: the study used six, captured
    in one quiet session, and the runtime compares against their centroid.

    Args:
        entity_id: Target entity in ``entities``.
        embedding: 192-d embedding; stored L2-normalized.
        label: Human label, normally the entity name.
        model_id: Frozen ``model@revision`` that produced *embedding*.

    Returns:
        The new ``voice_profiles`` row id.

    Raises:
        BrainMemoryError: If the DB is unavailable, the dimension is wrong, or
            the embedding is all zeros.
    """
    if embedding.shape != (VOICEPRINT_DIM,):
        raise BrainMemoryError(f"Expected {VOICEPRINT_DIM}-d voiceprint, got {embedding.shape}")
    normalized = _l2_normalized(embedding)
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "INSERT INTO voice_profiles (entity_id, label, embedding, model_id) "
            "VALUES (?, ?, ?, ?)",
            (entity_id, label, _pack(normalized), model_id),
        )
        profile_id = cursor.lastrowid
        await cursor.close()
    return int(profile_id) if profile_id is not None else 0


async def _references(entity_id: int, model_id: str) -> list[np.ndarray]:
    """Read every stored reference for this person and this exact model."""
    cursor = await get_conn().execute(
        "SELECT embedding FROM voice_profiles WHERE entity_id = ? AND model_id = ?",
        (entity_id, model_id),
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return [_unpack(bytes(row[0])) for row in rows]


async def count_voiceprints(entity_id: int, model_id: str) -> int:
    """Return how many usable references this person has for *model_id*."""
    return len(await _references(entity_id, model_id))


async def centroid_distance(entity_id: int, embedding: np.ndarray, model_id: str) -> float | None:
    """Return the cosine distance from *embedding* to this person's centroid.

    Args:
        entity_id: Person whose references are compared.
        embedding: Fresh 192-d embedding of the current utterance.
        model_id: Frozen ``model@revision`` currently configured. References
            produced by any other model are ignored.

    Returns:
        The cosine distance in ``[0, 2]`` — lower is closer — or ``None`` when
        this person has no reference for *model_id*.

    Raises:
        BrainMemoryError: If the DB is unavailable or a vector is all zeros.
    """
    references = await _references(entity_id, model_id)
    if not references:
        return None
    centroid = _l2_normalized(np.mean(np.stack(references), axis=0))
    return float(1.0 - np.dot(centroid, _l2_normalized(embedding)))
```

- [ ] **Step 7: Add the two model settings**

In `server/src/server/settings.py`, after the face block:

```python
    # ---------------- Speaker evidence (Plan 0053, PC-3B) ----------------
    # Frozen by Plan 0047's readiness contract and calibrated against this
    # exact revision. Changing either value invalidates every stored
    # voiceprint: vectors record the model that produced them and are never
    # compared across models.
    speaker_model: str = "speechbrain/spkrec-ecapa-voxceleb"
    speaker_model_revision: str = "0f99f2d0ebe89ac095bcc5903c4dd8f72b367286"
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `uv run pytest tests/integration/test_voice_consent_schema.py -v`
Expected: 6 passed.

- [ ] **Step 9: Commit**

```bash
git add server/src/server/memory/migration_008_voice_consent.sql server/src/server/memory/voice_consent.py server/src/server/voice/__init__.py server/src/server/voice/voiceprints.py server/src/server/db.py server/src/server/settings.py tests/integration/test_voice_consent_schema.py
git commit -m "feat(memory): consented voiceprint storage and revocation"
git log -1 --pretty=%s
```

---

## Task 2: The pure verdict table

**Files:**
- Create: `server/src/server/cognition/speaker_authentication.py`
- Modify: `server/src/server/settings.py` (threshold, minimum references)
- Test: `tests/unit/test_speaker_authentication.py`

**Interfaces:**
- Consumes: `server.cognition.identity.HouseholdRole`.
- Produces: `SpeakerVerdict` (`VERIFIED`, `UNKNOWN`, `UNAVAILABLE`) and
  `evaluate_speaker_verification(*, reference_count, distance, consent_active,
  role, backend_available) -> SpeakerVerdict`.

- [ ] **Step 1: Write the failing decision-table tests**

```python
# tests/unit/test_speaker_authentication.py
"""Unit tests for the pure speaker verdict table (Plan 0053, Task 2)."""

import pytest
from server.cognition.identity import HouseholdRole
from server.cognition.speaker_authentication import SpeakerVerdict, evaluate_speaker_verification
from server.settings import settings


def _evaluate(**overrides: object) -> SpeakerVerdict:
    """Evaluate the table from the all-satisfied case with named overrides."""
    kwargs: dict[str, object] = {
        "reference_count": settings.speaker_min_reference_count,
        "distance": settings.speaker_authentication_match_threshold - 0.01,
        "consent_active": True,
        "role": HouseholdRole.OWNER,
        "backend_available": True,
    }
    kwargs.update(overrides)
    return evaluate_speaker_verification(**kwargs)  # type: ignore[arg-type]


def test_all_conditions_satisfied_verifies() -> None:
    assert _evaluate() is SpeakerVerdict.VERIFIED


def test_distance_exactly_at_the_threshold_verifies() -> None:
    """The study's rule is `distance <= threshold`, not `<`."""
    assert _evaluate(distance=settings.speaker_authentication_match_threshold) is (
        SpeakerVerdict.VERIFIED
    )


def test_backend_unavailable_is_unavailable_not_unknown() -> None:
    assert _evaluate(backend_available=False) is SpeakerVerdict.UNAVAILABLE


@pytest.mark.parametrize(
    "override",
    [
        {"reference_count": 0},
        {"reference_count": 2},
        {"distance": None},
        {"distance": 0.9},
        {"consent_active": False},
        {"role": HouseholdRole.ADULT},
        {"role": HouseholdRole.UNKNOWN},
    ],
)
def test_every_other_failure_is_unknown(override: dict[str, object]) -> None:
    assert _evaluate(**override) is SpeakerVerdict.UNKNOWN


def test_unavailable_wins_over_a_matching_distance() -> None:
    """A dead backend is never reported as a match, whatever else is true."""
    assert _evaluate(backend_available=False, distance=0.0) is SpeakerVerdict.UNAVAILABLE
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_speaker_authentication.py -v`
Expected: FAIL — `No module named 'server.cognition.speaker_authentication'`.

- [ ] **Step 3: Add the two settings**

```python
    # Cosine-DISTANCE upper bound for a speaker match against the reference
    # centroid (0 = identical voice). Measured by Plan 0047's calibration
    # study: 0/24 live-impostor false accepts and 0/24 genuine false rejects
    # at 0.4834 — but IN-SAMPLE (the FRR is zero by construction), on one
    # owner and four impostors, with no held-out data, and 6 of 8 replay
    # probes were ACCEPTED. Provisional: voice is never standalone
    # high-assurance evidence, and this value grants nothing by itself.
    speaker_authentication_match_threshold: float = 0.4834
    # Fewer references than this and verification is not attempted at all —
    # a centroid of one or two samples is not what the study measured.
    speaker_min_reference_count: int = 3
```

- [ ] **Step 4: Write the pure table**

```python
# server/src/server/cognition/speaker_authentication.py (first half)
"""Pure speaker verdict and request-scoped speaker evidence (Plan 0053, PC-3B).

`VERIFIED` never means authorized. The resolver below attaches untrusted
`IdentityEvidenceSource.VOICE` evidence, which `resolve_active_person` does not
resolve — fusing voice with face or PIN is PC-4, not this module.

Audio contract for every WAV this module touches: WAV, 16 000 Hz, mono, signed
int16.
"""

from enum import StrEnum

from server.cognition.identity import HouseholdRole
from server.settings import settings


class SpeakerVerdict(StrEnum):
    """Closed outcome of one speaker verification attempt."""

    VERIFIED = "verified"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"


def evaluate_speaker_verification(
    *,
    reference_count: int,
    distance: float | None,
    consent_active: bool,
    role: HouseholdRole,
    backend_available: bool,
) -> SpeakerVerdict:
    """Decide the speaker verdict from pre-computed evidence.

    Pure decision table — no I/O. The caller must already have applied the
    frozen preprocessing and compared against the reference centroid.

    Args:
        reference_count: Stored references for the configured model.
        distance: Cosine distance to the centroid, or `None` when no
            comparison was possible (no reference, unusable audio).
        consent_active: Whether the person has an active voice consent grant.
        role: The person's current household role, re-read this turn.
        backend_available: Whether the embedding backend produced a vector.

    Returns:
        `UNAVAILABLE` when the backend could not run — a degraded sense, not a
        judgement about the speaker. `VERIFIED` only with enough references, a
        distance within `settings.speaker_authentication_match_threshold`,
        active consent and the owner role. `UNKNOWN` for every other case.
    """
    if not backend_available:
        return SpeakerVerdict.UNAVAILABLE
    if reference_count < settings.speaker_min_reference_count:
        return SpeakerVerdict.UNKNOWN
    if distance is None or distance > settings.speaker_authentication_match_threshold:
        return SpeakerVerdict.UNKNOWN
    if not consent_active:
        return SpeakerVerdict.UNKNOWN
    if role is not HouseholdRole.OWNER:
        return SpeakerVerdict.UNKNOWN
    return SpeakerVerdict.VERIFIED
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_speaker_authentication.py -v`
Expected: 11 passed.

- [ ] **Step 6: Commit**

```bash
git add server/src/server/cognition/speaker_authentication.py server/src/server/settings.py tests/unit/test_speaker_authentication.py
git commit -m "feat(cognition): pure speaker verification verdict table"
git log -1 --pretty=%s
```

---

## Task 3: The frozen runtime embedding adapter

**Files:**
- Create: `server/src/server/voice/speaker_embedding.py`
- Modify: `server/pyproject.toml`, `pyproject.toml`, `uv.lock` (D-3)
- Modify: `server/src/server/settings.py` (`speaker_model_cache_dir`, `speaker_min_enrollment_s`)
- Test: `tests/unit/test_speaker_embedding.py`,
  `tests/slow/test_speaker_embedding_real_model.py`

**Interfaces:**
- Consumes: `server.audio_contract.validate_wav_contract`, `settings`.
- Produces:
  - `SpeakerBackendError(ServerError)`
  - `embed_wav(wav_bytes: bytes) -> np.ndarray` — 192 finite floats
  - `has_voiced_energy(wav_bytes: bytes) -> bool`
  - `model_id() -> str` — `f"{settings.speaker_model}@{settings.speaker_model_revision}"`

- [ ] **Step 1: Move the dependencies**

```bash
uv add --package server "speechbrain==1.1.1" "torch>=2.14.0,<3.0.0" "torchaudio>=2.11.0,<3.0.0"
uv lock --check
```

Keep the root `[dependency-groups] dev` entries: the study harness under
`scripts/` still needs them and `just gate` runs from the root. Confirm the
`pytorch-cpu` index still applies (`[tool.uv.sources]` in the root
`pyproject.toml` is workspace-wide).

- [ ] **Step 2: Write the failing adapter tests with a typed fake encoder**

```python
# tests/unit/test_speaker_embedding.py
"""Unit tests for the frozen runtime speaker-embedding adapter (Plan 0053,
Task 3). No real model: a typed fake encoder stands in, so CI never downloads
or loads torch weights."""

import io
import wave

import numpy as np
import pytest
from server.exceptions import AudioContractError
from server.voice import speaker_embedding
from server.voice.speaker_embedding import SpeakerBackendError


def _wav(samples: np.ndarray, *, rate: int = 16_000, channels: int = 1) -> bytes:
    """Build a WAV container around *samples* (int16)."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(samples.astype(np.int16).tobytes())
    return buffer.getvalue()


def _tone(seconds: float = 3.0, amplitude: int = 8_000) -> bytes:
    """Build a deterministic synthetic 'utterance' — never a human recording."""
    t = np.linspace(0.0, seconds, int(16_000 * seconds), endpoint=False)
    return _wav((amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.int16))


class _FakeEncoder:
    """Stands in for speechbrain's EncoderClassifier."""

    def __init__(self, vector: np.ndarray | None = None) -> None:
        self.calls = 0
        self._vector = np.ones(192, dtype=np.float32) if vector is None else vector

    def encode_batch(self, wavs: object, wav_lens: object, normalize: bool) -> object:
        self.calls += 1
        return _FakeOutput(self._vector)


def test_embed_returns_192_finite_floats(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(speaker_embedding, "_load_encoder", lambda: _FakeEncoder())
    vector = speaker_embedding.embed_wav(_tone())
    assert vector.shape == (192,)
    assert np.isfinite(vector).all()


def test_non_contract_wav_never_reaches_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    encoder = _FakeEncoder()
    monkeypatch.setattr(speaker_embedding, "_load_encoder", lambda: encoder)
    with pytest.raises(AudioContractError):
        speaker_embedding.embed_wav(_wav(np.zeros(16_000), rate=44_100))
    assert encoder.calls == 0


def test_a_broken_loader_raises_the_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review Focus 4: corrupt or half-downloaded model files must degrade."""

    def _explode() -> object:
        raise RuntimeError("PytorchStreamReader failed reading zip archive")

    monkeypatch.setattr(speaker_embedding, "_load_encoder", _explode)
    with pytest.raises(SpeakerBackendError):
        speaker_embedding.embed_wav(_tone())


def test_near_silence_has_no_voiced_energy() -> None:
    """Review Focus 1: a format-perfect silent WAV must never verify."""
    assert speaker_embedding.has_voiced_energy(_wav(np.zeros(48_000))) is False
    assert speaker_embedding.has_voiced_energy(_tone()) is True


def test_model_id_comes_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(speaker_embedding.settings, "speaker_model", "m")
    monkeypatch.setattr(speaker_embedding.settings, "speaker_model_revision", "r")
    assert speaker_embedding.model_id() == "m@r"
```

`_FakeOutput` mirrors the tensor shape the real encoder returns
(`(1, 1, 192)` with `.squeeze().detach().cpu().numpy()`); write it in the same
file as a small class with those four methods returning `self` and finally the
vector.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_speaker_embedding.py -v`
Expected: FAIL — `No module named 'server.voice.speaker_embedding'`.

- [ ] **Step 4: Write the adapter**

```python
# server/src/server/voice/speaker_embedding.py
"""Frozen CPU speaker-embedding adapter (Plan 0053, PC-3B).

The only place the runtime loads a speaker model. Reproduces Plan 0047's frozen
contract exactly — SpeechBrain 1.1.1 EncoderClassifier, the pinned revision,
CPU, `samples / 32768.0` preprocessing, 192-d output — but reads the model
identity from `settings` instead of hardcoding it, because runtime code may not
hardcode a model name. Every heavy import is deferred, so a server with
`SPEAKER_AUTHENTICATION_ENABLED=false` never imports torch.

Audio contract: WAV, 16 000 Hz, mono, signed int16. No cloud inference
(ADR-0004). A returned vector is untrusted identity evidence, never
authorization.
"""

import io
import logging
from typing import Any, Final
import wave

import numpy as np

from server.audio_contract import validate_wav_contract
from server.exceptions import ServerError
from server.settings import settings

logger = logging.getLogger(__name__)

_INT16_FULL_SCALE: Final = 32768.0
_EMBEDDING_DIM: Final = 192
# Mean absolute sample value below which the clip is treated as silence. A
# contract-perfect silent WAV embeds like any other and would otherwise be
# compared against the centroid (Review Focus 1).
_MIN_MEAN_ABS_AMPLITUDE: Final = 200.0

_encoder: Any | None = None  # noqa: ANN401 -- speechbrain ships no type stubs


class SpeakerBackendError(ServerError):
    """The speaker backend could not produce an embedding."""


def model_id() -> str:
    """Return the configured frozen ``model@revision`` identifier."""
    return f"{settings.speaker_model}@{settings.speaker_model_revision}"


def has_voiced_energy(wav_bytes: bytes) -> bool:
    """Return whether the clip carries more than background-level energy.

    Args:
        wav_bytes: Raw WAV bytes — 16 000 Hz, mono, signed int16.

    Returns:
        `False` for a clip whose mean absolute amplitude is at or below the
        silence floor, which must never be verified against a voiceprint.
    """
    samples = _decode(wav_bytes)
    return bool(np.mean(np.abs(samples)) > _MIN_MEAN_ABS_AMPLITUDE / _INT16_FULL_SCALE)


def embed_wav(wav_bytes: bytes) -> np.ndarray:
    """Embed one contract WAV into a 192-d speaker vector on CPU.

    Args:
        wav_bytes: Raw WAV bytes — 16 000 Hz, mono, signed int16.

    Returns:
        A 1-D `np.ndarray` of exactly 192 finite floats.

    Raises:
        AudioContractError: If the bytes break the audio contract.
        SpeakerBackendError: If the model cannot be loaded or returns a
            non-finite, wrong-length or all-zero vector.
    """
    validate_wav_contract(wav_bytes, max_duration_s=settings.max_audio_duration_s)
    wave_f32 = _decode(wav_bytes)
    try:
        encoder = _load_encoder()
        import torch  # noqa: PLC0415 -- deferred so the flag-off path never imports torch

        tensor = torch.from_numpy(wave_f32).unsqueeze(0)
        output = encoder.encode_batch(wavs=tensor, wav_lens=None, normalize=False)
        vector = np.asarray(output.squeeze().detach().cpu().numpy(), dtype=np.float32)
    except (OSError, RuntimeError, ValueError, ImportError) as exc:
        raise SpeakerBackendError("Speaker backend unavailable") from exc
    if vector.shape != (_EMBEDDING_DIM,) or not np.isfinite(vector).all() or not vector.any():
        raise SpeakerBackendError(f"Speaker backend returned an unusable vector {vector.shape}")
    return vector


def _decode(wav_bytes: bytes) -> np.ndarray:
    """Decode a contract WAV to float32 in [-1.0, 1.0), as Plan 0047 froze it."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / _INT16_FULL_SCALE


def _load_encoder() -> Any:  # noqa: ANN401 -- speechbrain ships no type stubs
    """Construct the frozen encoder once per process, offline, on CPU."""
    global _encoder  # noqa: PLW0603 -- one process-wide model, like vision.faces
    if _encoder is not None:
        return _encoder
    from speechbrain.inference.speaker import EncoderClassifier  # noqa: PLC0415 -- deferred
    from speechbrain.utils.fetching import FetchConfig, LocalStrategy  # noqa: PLC0415 -- deferred

    cache_dir = settings.speaker_model_cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Loading speaker model %s (CPU, offline)", model_id())
    _encoder = EncoderClassifier.from_hparams(
        source=settings.speaker_model,
        savedir=str(cache_dir),
        run_opts={"device": "cpu"},
        local_strategy=LocalStrategy.COPY,  # SYMLINK breaks on Windows without Dev Mode
        fetch_config=FetchConfig(revision=settings.speaker_model_revision, allow_network=False),
    )
    return _encoder
```

Add the settings this task needs:

```python
    # Frozen model cache. Copied once from the Plan 0047 study cache; never
    # read from project-history/, which is gitignored local history.
    speaker_model_cache_dir: Path = Path("models") / "speechbrain"
    # Shortest utterance accepted for ENROLMENT. Verification uses whatever the
    # turn already carried; enrolment refuses a reference this short.
    speaker_min_enrollment_s: float = 2.0
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_speaker_embedding.py -v`
Expected: 5 passed.

- [ ] **Step 6: Add the one slow test against the real cached model**

```python
# tests/slow/test_speaker_embedding_real_model.py
"""One real-model check (Plan 0053, Task 3) — skipped when the frozen model is
not cached on this machine. Synthetic audio only; never a human recording."""

import pytest
from server.settings import settings
from server.voice.speaker_embedding import embed_wav, model_id

pytestmark = pytest.mark.slow


def test_the_real_encoder_returns_the_frozen_shape() -> None:
    if not (settings.speaker_model_cache_dir / "hyperparams.yaml").is_file():
        pytest.skip("frozen speaker model not cached on this machine")
    vector = embed_wav(_tone())  # same helper as the unit test, copied locally
    assert vector.shape == (192,)
    assert "@" in model_id()
```

- [ ] **Step 7: Warm the cache from the study's copy (once, locally)**

```powershell
New-Item -ItemType Directory -Force models/speechbrain
Copy-Item project-history/calibration/speaker/model-cache/* models/speechbrain/
uv run pytest tests/slow/test_speaker_embedding_real_model.py -v
```

Expected: PASS, with no network access. If the cache is absent the test skips —
that is the CI behaviour and it is correct.

- [ ] **Step 8: Commit**

```bash
git add server/src/server/voice/speaker_embedding.py server/src/server/settings.py server/pyproject.toml pyproject.toml uv.lock tests/unit/test_speaker_embedding.py tests/slow/test_speaker_embedding_real_model.py
git commit -m "feat(voice): frozen CPU speaker embedding adapter"
git log -1 --pretty=%s
```

---

## Task 4: The request-scoped speaker resolver

**Files:**
- Modify: `server/src/server/cognition/speaker_authentication.py` (second half)
- Test: `tests/unit/test_speaker_authentication.py` (append)

**Interfaces:**
- Consumes: Task 1's `count_voiceprints` / `centroid_distance` /
  `has_active_voice_consent`, Task 2's verdict table, Task 3's `embed_wav` /
  `has_voiced_energy` / `model_id`, `memory.household_authorization.get_active_role`,
  `memory.entity_labels.get_person_label`.
- Produces:
  - `SpeakerRequestResolver(*, wav_bytes, owner_person_id, clock, read_role, read_consent, count_references, distance_to_centroid, embed, model_id)`
  - `await resolver.resolve_actor(event) -> ActivePersonContext`
  - `resolver.last_verdict: SpeakerVerdict | None`
  - `build_default_speaker_resolver(wav_bytes: bytes, owner_person_id: int) -> SpeakerRequestResolver`

- [ ] **Step 1: Write the failing resolver tests**

```python
# appended to tests/unit/test_speaker_authentication.py
"""Resolver behaviour (Plan 0053, Task 4)."""

from datetime import UTC, datetime
from uuid import uuid4

from server.cognition.identity import ActivePersonStatus, IdentityEvidenceSource
from server.cognition.models import CognitiveEvent
from server.cognition.response_plan import TextTurnPayload
from server.cognition.speaker_authentication import SpeakerRequestResolver
from server.voice.speaker_embedding import SpeakerBackendError

_OWNER_ID = 42


def _event() -> CognitiveEvent[TextTurnPayload]:
    now = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    return CognitiveEvent(
        event_id=uuid4(),
        schema_version=1,
        event_type="text.turn",
        occurred_at=now,
        recorded_at=now,
        source="audio.transcribe",
        correlation_id=uuid4(),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message="canary", conversation_id="canary-scope"),
    )


def _resolver(**overrides: object) -> SpeakerRequestResolver:
    """Build a resolver whose every boundary is a controllable double."""
    ...  # fill each seam from the Interfaces block; defaults verify


async def test_a_verified_speaker_produces_untrusted_voice_evidence() -> None:
    resolver = _resolver()
    context = await resolver.resolve_actor(_event())
    assert context.status is ActivePersonStatus.UNKNOWN  # VOICE never identifies
    assert context.person_id is None
    assert [item.source for item in context.evidence] == [IdentityEvidenceSource.VOICE]
    assert context.evidence[0].candidate_person_id == _OWNER_ID


async def test_a_failed_verdict_produces_no_evidence_at_all() -> None:
    resolver = _resolver(read_consent=_false)
    context = await resolver.resolve_actor(_event())
    assert context.evidence == ()


async def test_the_embedding_runs_at_most_once_per_request() -> None:
    counter = _CountingEmbed()
    resolver = _resolver(embed=counter)
    await resolver.resolve_actor(_event())
    await resolver.resolve_actor(_event())
    assert counter.calls == 1


async def test_a_dead_backend_degrades_instead_of_raising() -> None:
    resolver = _resolver(embed=_raise(SpeakerBackendError("down")))
    context = await resolver.resolve_actor(_event())
    assert context.evidence == ()
    assert resolver.last_verdict is SpeakerVerdict.UNAVAILABLE


async def test_silence_is_never_verified() -> None:
    """Review Focus 1."""
    resolver = _resolver(has_energy=_false_sync)
    assert (await resolver.resolve_actor(_event())).evidence == ()


async def test_a_reference_from_another_model_is_ignored() -> None:
    """Review Focus 2 — `count_references` is asked for the CONFIGURED model."""
    resolver = _resolver(count_references=_zero)
    assert (await resolver.resolve_actor(_event())).evidence == ()


async def test_revocation_mid_turn_loses_the_references() -> None:
    """Review Focus 3 — the purge empties the centroid before comparison."""
    resolver = _resolver(distance_to_centroid=_none)
    assert (await resolver.resolve_actor(_event())).evidence == ()


async def test_the_role_is_read_on_every_request() -> None:
    """Review Focus 5 — a role change takes effect on the next turn."""
    role_reader = _CountingRole()
    await _resolver(read_role=role_reader).resolve_actor(_event())
    await _resolver(read_role=role_reader).resolve_actor(_event())
    assert role_reader.calls == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_speaker_authentication.py -v`
Expected: FAIL — `cannot import name 'SpeakerRequestResolver'`.

- [ ] **Step 3: Write the resolver**

Mirror `FaceRequestResolver`: one cached `_resolve` per request, every boundary
injected, `VisionError`-equivalent (`SpeakerBackendError`) caught and degraded
to `UNAVAILABLE`, and the evidence built only on `VERIFIED`:

```python
class SpeakerRequestResolver:
    """Request-scoped speaker resolver bound to one turn's audio (excerpt)."""

    async def _resolve(self, event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        """Run the one-shot energy -> embed -> compare -> decide pipeline."""
        distance: float | None = None
        backend_available = True
        reference_count = await self._count_references(self._owner_person_id, self._model_id)
        enough = reference_count >= settings.speaker_min_reference_count
        if enough and self._has_energy(self._wav):
            try:
                embedding = self._embed(self._wav)
            except (SpeakerBackendError, AudioContractError) as exc:
                logger.warning("Speaker backend degraded to unavailable: %s", exc)
                backend_available = False
            else:
                distance = await self._distance(self._owner_person_id, embedding, self._model_id)

        verdict = evaluate_speaker_verification(
            reference_count=reference_count,
            distance=distance,
            consent_active=await self._read_consent(self._owner_person_id),
            role=await self._read_role(self._owner_person_id),
            backend_available=backend_available,
        )
        self.last_verdict = verdict
        logger.info(
            "Speaker verdict: %s",
            verdict.value,
            extra={"event": "speaker.verdict", "verdict": verdict.value},
        )
        if verdict is not SpeakerVerdict.VERIFIED:
            return _unknown_active_person(event, "No speaker evidence")
        evidence = IdentityEvidence(
            evidence_id=uuid4(),
            source=IdentityEvidenceSource.VOICE,
            candidate_person_id=self._owner_person_id,
            confidence=Confidence(
                score=1.0,
                basis=ConfidenceBasis.MEASURED,
                calibrated=True,
                reason="Speaker match within the provisional authentication threshold",
            ),
            observed_at=self._clock(),
            reference="in-turn-speaker-evidence",
            expires_at=None,
        )
        return _unknown_active_person(event, "Speaker evidence is untrusted", evidence=(evidence,))
```

The log line carries the verdict only — never a name, a distance or a
transcript (D-8). `_unknown_active_person` builds the same safe
`ActivePersonContext` shape `face_authentication.py` uses, with
`status=UNKNOWN`, `role=HouseholdRole.UNKNOWN` and the supplied evidence tuple.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_speaker_authentication.py -v`
Expected: 19 passed.

- [ ] **Step 5: Prove the identity core is untouched**

Run: `uv run pytest tests/unit/test_active_person_identity.py -v && git diff --stat server/src/server/cognition/identity.py`
Expected: all pass, and an empty diff for `identity.py`.

- [ ] **Step 6: Commit**

```bash
git add server/src/server/cognition/speaker_authentication.py tests/unit/test_speaker_authentication.py
git commit -m "feat(cognition): request-scoped untrusted speaker evidence"
git log -1 --pretty=%s
```

---

## Task 5: Enrolment and revocation endpoints

**Files:**
- Modify: `server/src/server/routers/auth.py`
- Modify: `server/src/server/schemas_auth.py`
- Test: `tests/integration/test_owner_voice_enrollment.py`

**Interfaces:**
- Consumes: `_is_loopback`, `_authorize_face_action` (renamed
  `_authorize_biometric_action`, same behaviour, both callers updated),
  `read_limited_upload`, Task 1's repository, Task 3's adapter.
- Produces: `POST /auth/owner/voice/enroll` returning
  `VoiceEnrollResponse{profile_id: int, enrolled_at: datetime, reference_count: int}`;
  `POST /auth/owner/voice/revoke` returning 204.

- [ ] **Step 1: Write the failing endpoint tests**

Mirror `tests/integration/test_owner_face_enrollment.py` case for case:
non-loopback -> 403; no token -> 401; expired or already-consumed token -> 401;
oversized upload -> 413; empty body -> 422; a 44.1 kHz or stereo WAV -> 422; a
1-second clip -> 422 (`speaker_min_enrollment_s`); a near-silent 3-second clip
-> 422; a valid clip -> 200 with `reference_count == 1`, one `voice_profiles`
row and one active grant; a second valid clip -> `reference_count == 2` and
still one grant; revoke -> 204, zero rows, no active grant; every attempt
writes one `authorization_audit_events` row; no response body or log line
contains the owner's name.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/integration/test_owner_voice_enrollment.py -v`
Expected: FAIL — 404 on both routes.

- [ ] **Step 3: Add the response schema**

```python
class VoiceEnrollResponse(BaseModel):
    """Result of a successful authenticated owner voiceprint enrollment."""

    model_config = ConfigDict(extra="forbid")

    profile_id: int
    enrolled_at: datetime
    reference_count: int
```

Add it to `__all__`.

- [ ] **Step 4: Write the routes**

```python
@router.post(
    "/voice/enroll",
    responses=error_responses(
        (401, "Absent, expired, consumed, or otherwise unauthorized token"),
        (403, "Caller is not on loopback"),
        (413, "Audio exceeds the upload size limit"),
        (503, "Speaker model unavailable"),
    ),
)
async def enroll_owner_voice(
    http_request: Request,
    owner_unlock_service: OwnerUnlockServiceDep,
    audio: Annotated[UploadFile, File(description="WAV 16kHz mono int16 · one utterance")],
    x_iroko_identity_token: IdentityTokenDep = None,
) -> VoiceEnrollResponse:
    """Enroll one reference voiceprint for the token's own owner.

    Audio contract: WAV, 16 000 Hz, mono, signed int16. The audio is embedded
    and discarded — never stored, never logged, never transcribed. Several
    calls build the reference set the runtime compares a centroid against;
    `settings.speaker_min_reference_count` references are required before any
    verification is attempted.

    ADR-0015 decision 1: this is `biometric_admin`, not
    `personal_protected_read`. Plan 0051 binds the grant's scope; until then
    it consumes the same unscoped one-use token the face routes consume.
    ...
    """
```

The body is the face route's body with three substitutions: `_read_face_image`
becomes a `_read_enrollment_audio` helper that calls `read_limited_upload(...,
limit=settings.max_audio_upload_bytes)`, then `validate_wav_contract(...,
max_duration_s=settings.max_audio_duration_s)`, then rejects a clip shorter
than `settings.speaker_min_enrollment_s` or without `has_voiced_energy`;
`vision.enroll_person` becomes `embed_wav` plus `enroll_voiceprint`; and
`grant_face_consent` becomes `grant_voice_consent`. A `SpeakerBackendError`
becomes a 503, exactly as `VisionError` does for faces.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/integration/test_owner_voice_enrollment.py -v`
Expected: all pass.

- [ ] **Step 6: Confirm the OpenAPI surface grew by exactly two routes**

Run: `uv run pytest tests/integration/test_api_contract.py -v`
Expected: PASS. If a route-count assertion fails, update it deliberately in the
same commit — never by loosening the assertion.

- [ ] **Step 7: Commit**

```bash
git add server/src/server/routers/auth.py server/src/server/schemas_auth.py tests/integration/test_owner_voice_enrollment.py
git commit -m "feat(auth): loopback voice enrollment and revocation"
git log -1 --pretty=%s
```

---

## Task 6: Wire the resolver into the turn, behind the flag

**Files:**
- Modify: `server/src/server/routers/transcribe.py`
- Modify: `server/src/server/settings.py` (`speaker_authentication_enabled`)
- Test: `tests/integration/test_speaker_evidence_turn.py`

**Interfaces:**
- Consumes: Task 4's `build_default_speaker_resolver`.
- Produces: no new public interface. `_build_request_identity` gains a
  `wav_bytes: bytes | None` parameter and is called **after**
  `_read_audio_upload`.

- [ ] **Step 1: Write the failing wiring tests**

```python
# tests/integration/test_speaker_evidence_turn.py
"""The speaker resolver is inert with the flag off and produces untrusted
evidence with it on (Plan 0053, Task 6)."""


def test_flag_off_never_imports_the_backend(monkeypatch, client, silence_wav_bytes) -> None:
    """With the default settings, torch must not be imported by a turn."""
    monkeypatch.setattr(settings, "speaker_authentication_enabled", False)
    monkeypatch.delitem(sys.modules, "torch", raising=False)
    client.post("/transcribe", files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")})
    assert "torch" not in sys.modules


def test_flag_off_leaves_the_response_shape_unchanged(...) -> None: ...
def test_flag_on_still_denies_a_protected_question_without_pin_or_face(...) -> None: ...
def test_flag_on_reads_the_audio_exactly_once(...) -> None: ...
def test_a_backend_failure_does_not_fail_the_turn(...) -> None: ...
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/integration/test_speaker_evidence_turn.py -v`
Expected: FAIL — the flag does not exist yet.

- [ ] **Step 3: Add the master flag**

```python
    # Master on/off for in-request speaker evidence (Plan 0053). Off by
    # default: with it off no speaker model is loaded, torch is never
    # imported, and the turn behaves exactly as it does today. Voice evidence
    # grants nothing even when on — fusion is PC-4.
    speaker_authentication_enabled: bool = False
```

- [ ] **Step 4: Move the composition after the audio read**

In both `transcribe` and `transcribe_stream`, swap the two statements so
`audio_bytes = await _read_audio_upload(audio)` runs first, then
`request_identity = _build_request_identity(owner_unlock_service, token,
frame_bytes, audio_bytes)`. Nothing else moves: STT still runs on the same
bytes, and the 413/422 behaviour of `_read_audio_upload` is unchanged because
it did not depend on the resolver.

- [ ] **Step 5: Attach the resolver without touching face precedence**

`_build_request_identity` keeps returning the existing PIN-only or
face-then-PIN pair. When the flag is on and the owner is known, it additionally
builds the speaker resolver and consults it **only** when the composed actor
came back unidentified (D-6), attaching its evidence to the returned context.
`compose_face_then_pin_resolver` itself is not edited.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/integration/test_speaker_evidence_turn.py tests/integration/test_owner_authenticated_turn.py tests/integration/test_owner_authenticated_stream.py tests/integration/test_face_authenticated_turn.py -v`
Expected: all pass, with the pre-existing files unedited.

- [ ] **Step 7: Commit**

```bash
git add server/src/server/routers/transcribe.py server/src/server/settings.py tests/integration/test_speaker_evidence_turn.py
git commit -m "feat(transcribe): attach untrusted speaker evidence behind a flag"
git log -1 --pretty=%s
```

---

## Task 7: Configuration and operator tooling

**Files:**
- Modify: `.env.example`, `justfile`
- Create: `scripts/speaker_auth_demo.py`

- [ ] **Step 1: Document every new variable in `.env.example`**

One block after the face block, stating the threshold's provenance, that it is
provisional and in-sample, that replay was accepted 6 of 8, and that the flag
is off by default.

- [ ] **Step 2: Write the demo script**

`scripts/speaker_auth_demo.py` mirrors `scripts/face_auth_demo.py`:
`--enroll` (records nothing by itself — it takes a WAV path or uses the
existing `mic_test` capture helper the operator already runs), `--revoke`,
`--status`. It unlocks over loopback with the PIN, then calls the two new
routes. It never writes audio to the repository.

- [ ] **Step 3: Add the recipe**

```just
speaker-auth-demo *ARGS:
    uv run --env-file .env python scripts/speaker_auth_demo.py {{ARGS}}
```

- [ ] **Step 4: Verify the scoped checks the root gate does not see**

Run: `uv run ruff check scripts/speaker_auth_demo.py && uv run ruff format --check scripts/speaker_auth_demo.py && uv run mypy scripts/speaker_auth_demo.py`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add .env.example justfile scripts/speaker_auth_demo.py
git commit -m "chore(voice): operator tooling for speaker enrollment"
git log -1 --pretty=%s
```

---

## Task 8: Acceptance, privacy cleanup and documentation closure

- [ ] **Step 1: Run the full gate**

Run: `just gate`
Expected: PASS, with the test count grown by the new tests and coverage at or
above the configured floor.

- [ ] **Step 2: Hand the acceptance list to Pipec and wait**

Do not proceed until he reports outcomes for every case in
[What needs Pipec's real hardware](#what-needs-pipecs-real-hardware). An agent
never claims any of them.

- [ ] **Step 3: Confirm no audio survived**

Run a search for `.wav` files outside `tests/fixtures/` and the models
directory, and confirm the tracked diff contains no sample, hash, manifest or
transcript.

- [ ] **Step 4: Update the canonical documents**

`current-state.md` (Speaker recognition row rewritten from measured evidence),
`identity-and-access.md` (the PC-3B paragraph), the operator manual's *Tier 3*,
the roadmap row, both delivery maps, both plan indexes, and this plan's own
closure record — each stating plainly that `VOICE` stays untrusted, that replay
is not defended, and that PC-4 owns fusion.

- [ ] **Step 5: Regenerate the architecture diagram**

Per the standing rule, after editing `current-state.md` regenerate
`docs/architecture/diagrams/current-state.{json,html}` with the Archify skill
(`validate` then `deliver`).

- [ ] **Step 6: Obtain an independent review and resolve every finding**

Use `superpowers:requesting-code-review` for a whole-branch review, and
`superpowers:receiving-code-review` when the findings come back. Pipec decides
whether that review is a subagent or his own reading — an agent does not spawn
one on its own initiative.

- [ ] **Step 7: Finish the branch**

Use `superpowers:finishing-a-development-branch`. One PR, squash-merge, branch
deleted. Move this plan to `completed/` only with the measured evidence and
Pipec's acceptance recorded in it.

---

## What needs Pipec's real hardware

An agent can produce none of this. These steps run locally, on Pipec's own
microphone and database, and record **outcomes only** — never audio, never a
name, never a per-sample score.

1. **Enrolment.** At least three reference utterances through the real
   microphone at normal distance in a quiet room.
2. **Genuine acceptance.** A handful of fresh protected turns in at least two
   acoustic conditions: the verdict is `verified` and the turn still requires a
   PIN or a face to disclose anything.
3. **Held-out check (D-5).** None of step 2's utterances may be a calibration
   sample. Record how many were accepted.
4. **Negative cases.** No enrolment; consent revoked; silence; a very short
   utterance; the model files removed. Each produces `unknown` and a working
   turn.
5. **Revocation.** Revoke, then confirm directly in SQLite that no
   `voice_profiles` row survives for that person.
6. **Optional, Pipec's call.** A consenting adult repeats step 2 as an
   impostor. Consent is asked explicitly and the audio is deleted immediately
   after the verdict is recorded.
7. **Delete every captured WAV** and confirm nothing remains outside the
   database.

## What an agent may never do in this plan

- Record, capture, request, imitate, synthesize, clone or replay a human voice,
  in any task, for any reason, including "just to test it".
- Touch the microphone, or run any command that would.
- Copy a private sample, an embedding, a manifest, a hash or a transcript into
  a tracked file, a test fixture, a commit message or a document.
- Write a real household name, date or pet anywhere.
- Claim an acceptance step Pipec did not run and report.
- Weaken `_RESOLVABLE_SOURCES`, the face precedence, or any authorization rule
  to make a test pass.

Test audio is generated in code — deterministic synthetic waveforms — and the
model is exercised through a typed fake except in the one slow test against the
real cached model.

---

## Verification commands

```powershell
just gate                         # lint + typecheck + test + audit
uv run ruff format --check .      # CI also formats python blocks inside .md
uv run ruff check .
uv run pytest tests/integration/test_api_contract.py
uv run pytest tests/unit/test_active_person_identity.py
uv run python scripts/check_reserved_terms.py
uv lock --check
git diff --check
```

Scoped, because `just gate` does not see `scripts/`:

```powershell
uv run ruff check scripts/speaker_auth_demo.py
uv run ruff format --check scripts/speaker_auth_demo.py
uv run mypy scripts/speaker_auth_demo.py
```

## Completion criteria

1. Every task's RED test was observed failing first, and all gates above are
   green with no configuration weakened.
2. `cognition/identity.py` and `tests/unit/test_active_person_identity.py` are
   unchanged; `VOICE` still resolves to `UNKNOWN`.
3. With the flag off, both turn endpoints are unchanged and `torch` is never
   imported; the contract test and the import test prove it.
4. Enrolment and revocation are loopback-only, PIN-gated, owner-only and
   audited; revocation purges the vectors, proven in SQLite.
5. Every failure mode produces `unknown`; no path raises to the caller.
6. No audio is persisted, and no name, transcript, distance or score appears in
   any log, audit row or response body.
7. Pipec's real-hardware run recorded outcomes for every acceptance case,
   including the held-out genuine check and the revocation purge.
8. Documentation closure is complete and states plainly what stays open:
   `VOICE` untrusted, replay undefended, fusion owned by PC-4.
9. The threshold's provenance and its provisional, in-sample nature are
   recorded next to the setting itself.
10. Both new routes carry an ADR-0015 marker for Plan 0051.

## Rollback boundary

Everything is additive and behind `SPEAKER_AUTHENTICATION_ENABLED=false`.
Rolling back means turning the flag off; migration 008 is additive and its
tables are unused when the flag is off. Revocation is the user-facing undo and
works with the flag off.

## Risks

| Risk | Why it matters | Mitigation |
|---|---|---|
| Replay accepted 6 of 8 in the study | A recording of the owner scores like the owner | `VOICE` grants nothing here; replay and liveness are PC-4's explicit gate, stated in code, docs and the runbook |
| One owner, four impostors, no held-out data | The measured FAR of 0 has a 95 % rule-of-three bound near 12.5 %, and the FRR is zero by construction | Flag off by default; provenance at the setting; held-out genuine check at acceptance |
| `torch` in the server | Package size, slower cold start, an unauditable local `+cpu` build | Lazy import, flag off by default, cost accepted explicitly in D-3 |
| Latency on the hot path | p95 536 ms per real clip on a loaded laptop | One embedding per request, protected branch only, never the public path |
| Ordering against Plan 0051 | Two routes born against an unscoped token | ADR-0015 markers on both routes |
| Duplicated consent repository | Two near-identical modules | Accepted deliberately (D-2); a shared abstraction needs a third modality |
| Quiet scope creep into fusion | The tempting next step is merging voice into the face/PIN context | Non-goals, file scope, and completion criterion 2 |

## Self-review record (2026-09-25)

Run against the spec with fresh eyes, per `superpowers:writing-plans`.

1. **Spec coverage.** The roadmap row's four nouns map to tasks: enrolment
   (Task 5), consent (Task 1), revocation (Tasks 1 and 5), verification
   producing typed `VOICE` evidence (Tasks 2–4, wired in Task 6). "Missing,
   weak or failed evidence remains `unknown`" is Task 2's table plus Task 4's
   degradation tests. Plan 0015's "no household member's real voice may enter
   the repository" is the privacy constraint and Task 8 Step 3. No requirement
   is left without a task.
2. **Placeholder scan.** Tasks 5, 6 and 7 describe their code by exact
   substitution against a named existing implementation rather than repeating
   it in full; every signature they produce is written out in the Interfaces
   block, and every test case is enumerated. Task 4 Step 1's `_resolver`
   helper is deliberately left as a seam list because its doubles are named
   one by one in the Interfaces block. These are the weakest points of the
   plan; an implementer who cannot resolve one stops and asks rather than
   guessing.
3. **Type consistency.** `model_id` is a `str` everywhere and is produced by
   `speaker_embedding.model_id()`; `centroid_distance` returns `float | None`
   and feeds `evaluate_speaker_verification(distance=...)` unchanged;
   `count_voiceprints` feeds `reference_count`; `SpeakerVerdict` is the only
   verdict type. `VOICEPRINT_DIM` (192) and the adapter's `_EMBEDDING_DIM`
   (192) are two constants for one number, deliberately: one is a storage
   contract, the other a model contract, and Task 1's test pins that they
   agree.
4. **Review Focus.** All five entries have an owning task and a named test.

## Execution handoff

Plan complete. It lives under `docs/plans/open/` — the project's plan location,
which overrides the skill's default path — and Pipec promoted it to `NOW` in
[`docs/plans/README.md`](../README.md#operational-board) on 2026-09-25, so it is
executable.

**Recommended execution approach: Native** — `superpowers:executing-plans`, one
agent implementing every task in a fresh Claude Code session, with an
independent whole-branch review at the end. The tasks share interfaces closely
(Tasks 2–4 build one module between them), there are only eight of them, and
Pipec's standing rule is no subagents unless he asks. A shipped mistake here is
contained by the default-off flag, so the cheaper approach is the right one.

*Promoted 2026-09-25. Execute it in a fresh Claude Code session, one simple
branch from `main`, one PR at the end.*
