# Consented Speaker Runtime Evidence Implementation Plan (PC-3B)

- **Status:** `Draft` — **not executable**. `NOW` is empty; only Pipec promotes
  a plan. This document is the output of the queue-rule 4/6 re-audit of the
  roadmap row *PC-3B — consented speaker runtime evidence*, written on
  2026-09-25 against `main` at `751ce46`.
- **Roadmap row:** [PC-3B](../../roadmap/cognitive-roadmap.md#canonical-pre-electronics-delivery-portfolio),
  step 1 of the [agreed delivery order](../../roadmap/cognitive-roadmap.md#pre-purchase-readiness-gate--plug-it-in-and-it-works)
  (2026-09-25).
- **Spec:** [Plan 0015 — personal companion design](0015-personal-companion-design.md#pc-3--speaker-evidence--pc-3a-closed-pc-3b-unplanned).
- **Evidence it builds on:** [Plan 0047](../completed/0047-speaker-evidence-calibration-study.md#study-result-and-closure-record-2026-09-25)
  (PC-3A, provisional PASS, merged in PR #134 / `de4c6cf`).
- **Blocked on:** the decisions in [Decisions only Pipec can take](#decisions-only-pipec-can-take).
  Nothing in this file authorizes code.

---

## Source of truth

Authority order for this plan, highest first: runtime `AGENTS.md`;
[`implementation-guardrails.md`](../../architecture/implementation-guardrails.md);
accepted ADRs [0004](../../adr/0004-local-first-cognitive-policy.md),
[0006](../../adr/0006-personal-and-family-companion-profiles.md),
[0008](../../adr/0008-progressive-owner-authentication.md),
[0009](../../adr/0009-locked-posture-and-scoped-capabilities.md),
[0015](../../adr/0015-owner-grant-scope-and-speaker-binding.md);
[`current-state.md`](../../architecture/current-state.md);
[`identity-and-access.md`](../../architecture/identity-and-access.md);
[the roadmap](../../roadmap/cognitive-roadmap.md); then this plan.

Code and tests on `main` outrank any prose here. If an implementing agent finds
a contradiction, it stops and reports it instead of redesigning.

## Required reading (after promotion, in this order)

1. `AGENTS.md` and `.claude/rules/` in full.
2. [`docs/architecture/implementation-guardrails.md`](../../architecture/implementation-guardrails.md).
3. [ADR 0008](../../adr/0008-progressive-owner-authentication.md) and
   [ADR 0009](../../adr/0009-locked-posture-and-scoped-capabilities.md) —
   progressive authentication and scoped capabilities.
4. [ADR 0015](../../adr/0015-owner-grant-scope-and-speaker-binding.md) — read
   decision 2 in full: speaker *binding*, the face veto and liveness are PC-4,
   not this plan.
5. [ADR 0006](../../adr/0006-personal-and-family-companion-profiles.md) — face
   and voice are never the sole recovery route.
6. [`docs/architecture/identity-and-access.md`](../../architecture/identity-and-access.md),
   sections *Separate concepts*, *Progressive authentication* and
   *Identity evidence*.
7. [`docs/architecture/current-state.md`](../../architecture/current-state.md),
   rows *Consented local face evidence (Plan 0029 / PC-2)* and
   *Speaker recognition*.
8. [Plan 0047](../completed/0047-speaker-evidence-calibration-study.md) —
   the *Frozen readiness contract*, the *Study result and closure record* and
   the *Task 7 review record*.
9. [Plan 0029](../completed/0029-consented-local-face-evidence.md) — the
   structural template this plan mirrors, task by task.
10. Code, read before writing anything: `server/src/server/cognition/identity.py`,
    `cognition/face_authentication.py`, `routers/auth.py`,
    `routers/transcribe.py`, `memory/biometric_consent.py`,
    `memory/migration_007_biometric_consent.sql`, `vision/faces.py`,
    `settings.py`, `audio_contract.py`, and
    `scripts/speaker_calibration_backend.py`.

No item of `project-history/` is required reading. The 85 MB study model cache
that lives there is an artifact, not a source of truth.

---

## Re-audit record (2026-09-25)

Queue rule 4/6: the row's assumptions were re-checked against merged code, not
memory. The row's **product outcome does not change** — local enrollment,
consent, revocation and verification produce typed `VOICE` evidence; missing,
weak or failed evidence stays `unknown` and grants no capability. What changed
is the cost and the shape of the work.

| # | Finding | Evidence on `main` | Effect on the row |
|---|---|---|---|
| R-1 | PC-3A is **merged**, not pending | `de4c6cf` (PR #134), then `db9b65b` (#135) and `751ce46` (#136); `git branch -a` shows only `main` | Several docs still said "PR pending / unmerged branch"; corrected in the same change that adds this plan |
| R-2 | `VOICE` is not merely untrusted, it is **unresolvable** | `cognition/identity.py:147-154` — `_RESOLVABLE_SOURCES` is `{MANUAL, LOCAL_UNLOCK, FACE, SESSION}`; `tests/unit/test_active_person_identity.py:438` pins that `VOICE` for a verified person resolves to `UNKNOWN` | Good news: PC-3B needs **no change to `resolve_active_person`**. Attaching `VOICE` evidence cannot widen access by construction, and that test must stay green and unedited |
| R-3 | The consent pattern exists but is face-shaped | `migration_007_biometric_consent.sql` (`face_consent_grants`, `CHECK (purpose = 'owner_authentication')`, one active grant per person) and `memory/biometric_consent.py` (grant is idempotent; revoke purges `face_profiles` + `vec_faces` in one transaction) | Mirrorable, not reusable as is: its CHECK and its purge target are face-only. See decision **D-2** |
| R-4 | The biometric-admin endpoint pattern exists | `routers/auth.py` — loopback check, fresh PIN-consumed token, `ENROLL_BIOMETRIC` + `DataSensitivity.BIOMETRIC` through `evaluate_authorization`, audited, always the token's own owner, never a request-supplied subject | Voice enrollment/revocation must mirror it exactly, including the ordering risk in **D-7** |
| R-5 | The runtime does not hold the audio when it builds the identity resolver | `routers/transcribe.py:410-413` (classic) and `:534-537` (streaming): `_build_request_identity(...)` runs **before** `_read_audio_upload(audio)` | A small, real refactor the row did not anticipate: move the composition after the audio read, or hand the resolver a lazy audio provider |
| R-6 | The audio contract already delivers what a verifier needs | `/transcribe` and `/transcribe/stream` already receive WAV 16 kHz mono int16; `audio_contract.validate_wav_contract` exists | **No new multipart field and no response change on the turn endpoints.** Only enrollment needs a new endpoint that accepts WAV |
| R-7 | The frozen backend is a **dev** dependency, not a server one | `pyproject.toml:72-75` — `speechbrain==1.1.1`, `torch`, `torchaudio` live in `[dependency-groups] dev` behind the explicit `pytorch-cpu` index; `server/pyproject.toml` does not list them | Making voice a runtime capability moves hundreds of MB into the server package, and `pip-audit` still cannot audit the local `+cpu` builds (recorded and accepted in Plan 0047, Task 7). See **D-3** |
| R-8 | The model identity is frozen in a **script** constant | `scripts/speaker_calibration_backend.py` documents `_MODEL_SOURCE`/`_MODEL_REVISION` as the one sanctioned exception to the no-hardcoded-model rule, *for the study* | Runtime code may not hardcode a model name (`AGENTS.md` — Never Do). The precedent is `settings.face_model`. See **D-4** |
| R-9 | The cached model lives in gitignored history | `project-history/calibration/speaker/model-cache/`, about 85 MB, kept by `cleanup`'s default | Runtime must not read from `project-history/`. The face precedent downloads into `MODELS_DIR`. See **D-4** |
| R-10 | The threshold is provisional and in-sample | 0.4834; FRR 0/24 is zero **by construction**; one owner, four impostors, no held-out data; separation 0.342; replay 6/8 accepted | A default-off master flag and a "provisional" comment are mandatory, exactly as Plan 0029/0030 did for the face threshold. See **D-5** |
| R-11 | Latency is fine in the frozen protocol, not free in the hot path | p95 231 ms under the frozen protocol; p50 431 / p95 536 ms per real 4–5 s clip on a loaded laptop (informational) | Embed at most once per request, lazily, and never on the public path. See **D-6** |
| R-12 | ADR-0015 keeps binding out of this plan | ADR-0015 decision 2: speaker binding, face veto and liveness are PC-4 | `compose_face_then_pin_resolver`'s precedence is untouched, and `identity_source` keeps its `"face" \| "local_unlock" \| null` shape. See **D-8** |
| R-13 | Found in passing: runbook drift | `docs/runbooks/operator-manual.md` documented `FACE_AUTHENTICATION_MATCH_THRESHOLD` as `0.25`; `settings.py:153` and `.env.example` say `0.5815` since Plan 0030. Plan 0050 Task 12 does not own this line | Corrected in the same change as this plan |
| R-14 | One owner, by design | The face verdict requires `HouseholdRole.OWNER`; `face_consent_grants` allows one active grant per person; the calibration measured one owner | PC-3B stays single-owner. Multi-member voice is PC-6 |

Nothing in the re-audit contradicts the row or the ADRs. The row stays
`Required`; it is now `Draft` instead of `Unplanned`.

---

## Goal

Let the owner enrol their voice locally and consentedly, so that a protected
turn can produce **typed, untrusted `VOICE` identity evidence** with an
explicit verdict, and so that revocation really deletes the voiceprint.

Non-goal in one sentence: this plan does not make a voice authorize anything.

## What this plan does not do (non-goals)

- It does not make `VOICE` trusted, resolvable or capable of identifying the
  actor. `_RESOLVABLE_SOURCES` is not edited.
- It does not fuse voice with face or PIN, and does not change
  `compose_face_then_pin_resolver`'s precedence — PC-4 owns fusion.
- It does not bind a grant to the speaker, veto the PIN fallback, or add
  liveness/anti-replay defence — ADR-0015 decision 2 and PC-4 own those.
- It does not implement the ADR-0015 `OwnerUnlockScope` — Plan 0051 owns it.
- It does not change the audio contract, the `/transcribe` request or response
  shape, or any existing status code.
- It does not add diarization, wake word, multi-speaker segmentation, or any
  second speaker.
- It does not enrol anybody except the token's own owner, and it does not add
  a family/multi-member path (PC-6).
- It does not touch `scripts/speaker_calibration*` (the study harness stays a
  study harness) or re-run the calibration.
- It does not add a cloud provider anywhere (ADR-0004).

## Global constraints

- **Audio contract, never deviated:** WAV, 16 000 Hz, mono, signed int16.
  Documented in every function that touches audio.
- **Privacy:** a stored voiceprint is a vector, never audio. No WAV is
  persisted by the server, ever — not for enrolment, not for debugging.
  `IdentityEvidence.reference` carries a safe static label, never a name, a
  transcript or a score.
- **Real household data never enters the repository.** Tests use synthetic,
  deterministically generated audio and invented canaries;
  `scripts/check_reserved_terms.py` must pass on every commit.
- **Fail closed:** every failure mode (no enrolment, revoked consent, silent or
  too-short audio, a model that will not load, an unreadable WAV, a distance
  above threshold) produces `unknown`, never an exception that reaches the
  caller and never a partially-trusted state.
- **Off by default:** the master flag defaults to `false`, and with it off the
  server must not import the backend, load the model, or read the audio a
  second time.
- **Loopback only** for enrolment and revocation, with a fresh PIN-consumed
  token, exactly like the face endpoints.
- `just gate` is the gate. No lint, type, coverage or security configuration is
  weakened to pass.

---

## Decisions only Pipec can take

The plan is not promotable until these are answered. Each has a recommendation;
none is taken by an agent.

**D-1 — Proceed at all?** The calibration is provisional: one owner, four
impostors, no held-out data, FRR zero by construction, and 6 of 8 replay probes
accepted. Options: (a) build PC-3B now; (b) re-run a wider PC-3A round with
held-out data first; (c) drop voice evidence and go straight to PC-4 with face
and PIN only. *Recommended: (a).* PC-3B produces evidence that grants nothing,
so the provisional threshold cannot cause a disclosure on its own; the risk
lands in PC-4, which is where replay and liveness are decided anyway.

**D-2 — Where the voiceprint and its consent live.** Options: (a) new
`migration_008_voice_consent.sql` with `voice_consent_grants`, `voice_profiles`
and a `vec_voiceprints` virtual table (192-d), mirroring migration 003 + 007
one for one; (b) generalise `face_consent_grants` into a
`biometric_consent_grants` table with a modality column, migrating existing
rows. *Recommended: (a).* It mirrors a pattern that already works, needs no
data migration, and keeps revocation's purge target unambiguous. The DRY cost
is one duplicated 90-line repository; revisit only if a third modality appears.

**D-3 — Accept `torch` + `speechbrain` as server runtime dependencies?**
Options: (a) move `speechbrain==1.1.1`, `torch`, `torchaudio` into
`server/pyproject.toml` behind the existing `pytorch-cpu` index, keeping the
import lazy so a server with the flag off never loads them (the
`vision/faces.py` `_get_analyzer` pattern); (b) keep them out of the server and
run the embedder as a separate local process behind a small typed adapter;
(c) do not proceed (see D-1). *Recommended: (a).* It is the smallest honest
change, it matches how `insightface` already lives in the server, and (b) adds
a process boundary with no security benefit. The cost is explicit: package
size on the homelab, and `pip-audit` still cannot audit the local `+cpu`
builds.

**D-4 — Model identity and cache location.** Options: (a) `SPEAKER_MODEL`,
`SPEAKER_MODEL_REVISION` and a cache under `MODELS_DIR/speechbrain` in
`Settings`, with offline mode on by default and a one-time warm-up command;
(b) hardcode the frozen pair in the runtime module as the study does.
*Recommended: (a)* — (b) is forbidden for runtime code by `AGENTS.md`. Related
question for Pipec: copy the existing 85 MB study cache into `MODELS_DIR`, or
warm up from the network once? *Recommended: copy it* — it is the exact frozen
revision, already on disk, and copying keeps first boot offline.

**D-5 — Threshold and reference-set policy.** Options: (a) adopt 0.4834 as the
default value of `SPEAKER_AUTHENTICATION_MATCH_THRESHOLD`, flag off, comment
marked provisional and in-sample, exactly as Plan 0030's face threshold is
recorded; (b) refuse to ship a default and require a held-out re-measure first.
*Recommended: (a) plus a small held-out check during acceptance*: a handful of
fresh genuine samples that were never part of the calibration. How many
reference samples an enrolment needs before verification is attempted is the
same decision — the study used six references and a centroid; *recommended
minimum: three*, refusing to verify below it.

**D-6 — When the embedding is computed.** Options: (a) only when the flag is
on, the turn reaches a protected branch, and no face or PIN evidence already
identified the actor; (b) on every protected turn, so PC-4 later has both
signals available for conflict detection. *Recommended: (a)* for PC-3B — it is
the cheapest, and PC-4 is free to widen it when fusion actually needs a
conflict signal. Whichever is chosen, the embedding is computed at most once
per request and never on the public path.

**D-7 — Ordering against Plan 0051 (ADR-0015 scope).** The agreed order puts
PC-3B before Plan 0051, so the voice endpoints would be born against today's
unscoped token and Plan 0051 would then have to add them to `biometric_admin`.
Options: (a) keep the agreed order and require this plan to leave an explicit
`ADR-0015` marker on both new routes; (b) move Plan 0051 ahead of PC-3B so
voice enrolment is scoped from birth. *Recommended: (a)* — Plan 0051 already
rewrites enrol/revoke scoping, two more routes is a marginal cost, and
reordering the agreed queue is a bigger change than the problem.

**D-8 — Observability of the verdict.** Options: (a) log-only: a privacy-safe
verdict label in the turn log and the authorization audit, no wire change;
(b) an additive response field / NDJSON event exposing the speaker verdict.
*Recommended: (a)* — (b) implies to a client that voice authenticated the turn,
which is exactly what must not be implied before PC-4.

---

## Permitted file scope

Nothing outside this list may be created or modified. Any file the
implementation turns out to need and that is not listed stops the work and is
reported.

**New**

| File | Purpose |
|---|---|
| `server/src/server/memory/migration_008_voice_consent.sql` | `voice_consent_grants`, `voice_profiles`, `vec_voiceprints` (subject to D-2) |
| `server/src/server/memory/voice_consent.py` | Grant / revoke-and-purge / read, mirroring `biometric_consent.py` |
| `server/src/server/voice/__init__.py`, `voice/speaker_embedding.py` | Lazy, settings-driven, offline ECAPA adapter — the only place the runtime loads the model |
| `server/src/server/voice/voiceprints.py` | Enrol a reference vector, read the centroid, match with cosine distance (`vec_voiceprints`) |
| `server/src/server/cognition/speaker_authentication.py` | Pure verdict table + request-scoped `SpeakerRequestResolver` producing `VOICE` evidence |
| `scripts/speaker_auth_demo.py` | Local enrol/revoke/verify helper, mirroring `scripts/face_auth_demo.py` |
| `tests/unit/test_speaker_authentication.py`, `tests/unit/test_speaker_embedding.py`, `tests/integration/test_voice_consent_schema.py`, `tests/integration/test_owner_voice_enrollment.py` | The RED tests of each task |

**Modified**

| File | Change |
|---|---|
| `server/src/server/db.py` | Register migration 008 in `_MIGRATIONS` (`db.py:29-34`), the way 007 is registered |
| `server/src/server/settings.py` | `speaker_authentication_enabled` (default `false`), model id, model revision, match threshold, min reference count, min/max enrolment seconds |
| `server/src/server/schemas_auth.py` | `VoiceEnrollResponse` |
| `server/src/server/routers/auth.py` | `POST /auth/owner/voice/enroll`, `POST /auth/owner/voice/revoke` |
| `server/src/server/routers/transcribe.py` | Move the identity composition after the audio read; wire the speaker resolver behind the flag |
| `server/pyproject.toml`, `pyproject.toml`, `uv.lock` | Dependency move (D-3), mypy override for `speechbrain.*` if needed |
| `.env.example` | The new variables, with the provisional threshold documented |
| `justfile` | `speaker-auth-demo` recipe |
| `docs/architecture/current-state.md`, `docs/architecture/identity-and-access.md`, `docs/runbooks/operator-manual.md` (Tier 3), `docs/roadmap/cognitive-roadmap.md`, `docs/roadmap/personal-companion-delivery-map.md`, `docs/plans/README.md`, `docs/plans/open/README.md`, this plan | Closure documentation |
| `docs/architecture/diagrams/current-state.{json,html}` | Regenerated with the Archify skill after `current-state.md` changes |

**Never touched:** `scripts/speaker_calibration*.py`, `cognition/identity.py`,
`tests/unit/test_active_person_identity.py`, `vision/`, `robot/src/`,
`cognition/authorization.py`, `cognition/owner_authentication.py`.

---

## Interface contract (sketch, to be RED-tested before it is written)

```python
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

    Pure decision table, no I/O. `VERIFIED` never means authorized: the
    caller may only attach untrusted `VOICE` evidence, which
    `resolve_active_person` does not resolve (PC-4 owns fusion).
    """
```

Rows of the table, each its own test: backend unavailable -> `UNAVAILABLE`;
fewer references than the configured minimum -> `UNKNOWN`; no distance (audio
too short, silent, or unreadable) -> `UNKNOWN`; distance above threshold ->
`UNKNOWN`; consent inactive -> `UNKNOWN`; role not owner -> `UNKNOWN`;
everything satisfied -> `VERIFIED`.

The resolver returns an `ActivePersonContext` whose `status` is `UNKNOWN` and
whose `evidence` tuple carries one `IdentityEvidence(source=VOICE, ...)` with a
calibrated confidence, `observed_at`, an `expires_at` bounded by the turn, and
`reference="in-turn-speaker-evidence"`. It grants nothing, by construction
(R-2).

---

## Tasks

Every task is RED first: write the failing test, watch it fail for the right
reason, then implement. One commit per task, Conventional Commits, title 72
characters or fewer.

### Task 0 — Freeze the base and re-verify the re-audit

Re-run the checks in the [re-audit record](#re-audit-record-2026-09-25) against
the then-current `main` (the fourteen findings, by file and line). Any finding
that no longer holds stops the plan and is reported, not worked around. No code
in this task.

### Task 1 — Voice consent and voiceprint storage

**RED:** grant is idempotent for an already-consenting person; revoke sets
`revoked_at`, deletes every `voice_profiles` row and every matching
`vec_voiceprints` row in one transaction, and is idempotent when there is
nothing to revoke; `has_active_voice_consent` is false after revocation; a
second active grant for the same person is impossible (unique partial index).

**GREEN:** migration 008 plus `memory/voice_consent.py` and
`voice/voiceprints.py`, mirroring `biometric_consent.py` and `vision/faces.py`.

### Task 2 — The pure verdict table

**RED:** one test per row of `evaluate_speaker_verification`, including the
degraded rows. No database, no model, no audio.

**GREEN:** the pure function, in `cognition/speaker_authentication.py`.

### Task 3 — The frozen runtime backend adapter

**RED, with a typed fake encoder:** a valid WAV yields exactly 192 finite
floats; a non-conforming WAV (wrong rate, stereo, not int16) raises the typed
error and never reaches the model; a model that will not load degrades to
`UNAVAILABLE` and logs a warning without a traceback; the int16 to float
preprocessing matches Plan 0047's frozen contract exactly; the module is not
imported at all when the flag is off.

**GREEN:** `voice/speaker_embedding.py` — lazy import, settings-driven model id
and revision (D-4), offline by default, one embedding per call. One
`@pytest.mark.slow` test exercises the real cached model, as Plan 0047 did.

### Task 4 — The request-scoped speaker resolver

**RED:** with the flag on and an enrolled, consenting owner, a matching WAV
produces a context whose `status` is `UNKNOWN` and whose evidence tuple holds
exactly one `VOICE` item; with no enrolment, revoked consent, a non-matching
WAV or a dead backend, the evidence tuple is empty and the verdict is logged;
the embedding is computed at most once per request even when the resolver is
consulted twice; the existing
`test_resolver_returns_unknown_for_voice_evidence` still passes unedited.

**GREEN:** `SpeakerRequestResolver`, mirroring `FaceRequestResolver`'s lazy
single-inference shape.

### Task 5 — Enrolment and revocation endpoints

**RED:** loopback only (403 otherwise); absent, expired, consumed or malformed
token -> 401 with no disclosure; a WAV that violates the audio contract -> 422;
audio shorter than the configured minimum speech -> 422 with a stable reason;
oversized upload -> 413; the enrolled subject is always the token's own owner,
and a body field naming anybody else is ignored or rejected; a successful
enrolment writes exactly one `voice_profiles` row plus its vector and one
active consent grant; revocation returns 204 and purges; every attempt is
audited through `evaluate_authorization` and `record_authorization_decision`
with `ENROLL_BIOMETRIC` and `DataSensitivity.BIOMETRIC`; no route logs a name,
a transcript or a distance.

**GREEN:** `POST /auth/owner/voice/enroll` and `POST /auth/owner/voice/revoke`
in `routers/auth.py`, plus `VoiceEnrollResponse`. Both carry an explicit
ADR-0015 marker for Plan 0051 (D-7).

### Task 6 — Wire it into the turn, behind the flag

**RED:** with `SPEAKER_AUTHENTICATION_ENABLED=false` (the default) the
behaviour of `/transcribe` and `/transcribe/stream` is byte-identical, the
backend is never imported and the audio is read exactly once — pinned by the
existing OpenAPI contract test; with the flag on, a protected turn attaches
`VOICE` evidence and still denies without a PIN or face; the identity
composition now happens after the audio read (R-5) and the Plan 0026/0027/0029
paths are unchanged; a backend failure degrades the turn to the existing
behaviour instead of failing it.

**GREEN:** the minimal edit in `routers/transcribe.py`.

### Task 7 — Operator tooling and configuration

`.env.example`, `settings.py` comments marking the threshold provisional and
in-sample, `scripts/speaker_auth_demo.py`, a `just speaker-auth-demo` recipe,
the voice phase in `just onboard` if D-5's reference minimum makes a guided
capture worthwhile, and the operator manual's *Tier 3* section rewritten from
"not started" to what actually exists, gaps included.

### Task 8 — Real acceptance, privacy cleanup and documentation closure

Automated gates, then the real-hardware run of the next section, then the
documentation closure (current state, identity and access, roadmap row, both
delivery maps, both plan indexes, the Archify diagram), then the move to
`completed/`. The plan is closed by Pipec's evidence, not by an agent's
assertion.

---

## What needs Pipec's real hardware

An agent cannot produce any of this. These steps run locally, on Pipec's own
microphone and database, and record **outcomes only** — never audio, never a
name, never a per-sample score.

1. **Enrolment.** Speak the configured minimum number of reference samples
   through the real microphone into `POST /auth/owner/voice/enroll`, at normal
   distance, in a quiet room.
2. **Genuine acceptance.** A handful of fresh protected turns, in at least two
   acoustic conditions, confirming the verdict is `verified` and that the turn
   still requires a PIN or a face to disclose anything.
3. **Held-out check (D-5).** The genuine samples of step 2 must not be
   calibration samples. Record how many were accepted.
4. **Negative cases.** No enrolment at all; consent revoked; silence; a very
   short utterance; the model files removed. Each must produce `unknown` and a
   working turn.
5. **Revocation.** Revoke, then confirm directly in SQLite that no
   `voice_profiles` or `vec_voiceprints` row survives for that person.
6. **Optional, Pipec's call:** a consenting adult repeats step 2 as an
   impostor. Consent is asked for explicitly and the audio is deleted
   immediately after the verdict is recorded.
7. **Delete every captured WAV** and confirm nothing remains outside the
   database.

## What an agent may never do in this plan

- Record, capture, request, imitate, synthesize, clone or replay a human voice,
  in any task, for any reason, including "just to test it".
- Touch the microphone, or run any command that would.
- Copy a private sample, an embedding, a manifest, a hash or a transcript into
  a tracked file, a test fixture, a commit message or a document.
- Write a real household name, date or pet anywhere.
- Claim an acceptance step that Pipec did not run and report.
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
uv run python scripts/check_reserved_terms.py
uv lock --check
git diff --check
```

Scoped, because `just gate` does not see `scripts/`:

```powershell
uv run ruff check scripts/speaker_auth_demo.py
uv run mypy scripts/speaker_auth_demo.py
```

## Completion criteria

1. Every task's RED test was observed failing first, and all gates above are
   green with no configuration weakened.
2. `cognition/identity.py` and `tests/unit/test_active_person_identity.py` are
   unchanged; `VOICE` still resolves to `UNKNOWN`.
3. With the flag off, `/transcribe` and `/transcribe/stream` are unchanged and
   the backend is never imported; the OpenAPI contract test proves it.
4. Enrolment and revocation are loopback-only, PIN-gated, owner-only and
   audited; revocation purges the vectors, proven in SQLite.
5. Every failure mode produces `unknown`; no path raises to the caller.
6. No audio is persisted by the server, and no raw biometric value appears in
   any log, audit row or response.
7. Pipec's real-hardware run recorded outcomes for every case in
   [the acceptance list](#what-needs-pipecs-real-hardware), including the
   held-out genuine check and the revocation purge.
8. Documentation closure is complete and states plainly what is still open:
   `VOICE` is untrusted, replay is not defended, and PC-4 owns fusion.
9. The threshold's provenance and its provisional, in-sample nature are
   recorded next to the setting itself.

## Rollback boundary

Everything is additive and behind `SPEAKER_AUTHENTICATION_ENABLED=false`.
Rolling back means turning the flag off; the migration is additive and its
tables are unused when the flag is off. Revocation is the user-facing undo and
must work even with the flag off.

## Risks

| Risk | Why it matters | Mitigation in this plan |
|---|---|---|
| Replay accepted 6 of 8 in the study | A recording of the owner scores like the owner | `VOICE` grants nothing here; replay and liveness are PC-4's explicit gate. The plan states this in code comments, docs and the operator manual |
| One owner, four impostors, no held-out data | The measured FAR of 0 has a 95 % rule-of-three bound of about 12.5 %, and the FRR is zero by construction | Flag off by default; provisional threshold documented at the setting; a held-out genuine check during acceptance (D-5) |
| `torch` in the server | Package size, slower cold start, an unauditable local `+cpu` build | Lazy import, flag off by default, cost stated explicitly in D-3 |
| Latency on the hot path | p95 536 ms per real clip on a loaded laptop | Embed at most once per request, only on a protected branch, never on the public path (D-6) |
| Ordering against Plan 0051 | Two new routes born against an unscoped token | Explicit ADR-0015 markers on both routes so Plan 0051 picks them up (D-7) |
| Duplicated consent repository | Two near-identical modules (face, voice) | Accepted deliberately (D-2); a shared abstraction is justified only by a third modality |
| Quiet scope creep into fusion | The tempting next step is to merge voice into the face/PIN context | Non-goals, permitted file scope, and a completion criterion that `identity.py` is unchanged |

---

*Draft. It authorizes nothing until Pipec answers D-1 to D-8 and promotes it to
`NOW`.*
