# Face-Default Identity Fusion Implementation Plan (PC-4)

> **For agentic workers:** REQUIRED SUB-SKILL — use
> `superpowers:executing-plans` and implement this plan task by task in one
> session. `superpowers:subagent-driven-development` is **not** the default here:
> Pipec's standing rule is no subagents unless he asks. Steps use checkbox
> (`- [ ]`) syntax for tracking. Work on **one simple branch from `main`** —
> never a git worktree, even if a skill suggests one — and open one PR at the
> end. Also required: `superpowers:test-driven-development` for every task, and
> `superpowers:verification-before-completion` before any claim that a task or
> the plan is done.

- **Status:** `Ready` — written 2026-09-30 after the PC-4 brainstorm with Pipec;
  read and promoted to `NOW` by Pipec on 2026-09-30
  ([`docs/plans/README.md`](../README.md#operational-board)).
- **Roadmap row:** [PC-4](../../roadmap/cognitive-roadmap.md#canonical-pre-electronics-delivery-portfolio),
  step 2 of the [agreed delivery order](../../roadmap/cognitive-roadmap.md#pre-purchase-readiness-gate--plug-it-in-and-it-works).
- **Evidence it builds on:** [Plan 0053](../completed/0053-consented-speaker-runtime-evidence.md)
  (PC-3B, merged as PRs #144–#147) and
  [Plan 0030](../completed/0030-real-camera-face-acceptance.md).

**Goal:** Identify the owner by face by default, raise the assurance to `strong`
when the voice agrees, and require `strong` for reserved data — so a stranger never
receives private data, without a PIN in the daily path.

**Architecture:** One deterministic rule lives in `resolve_active_person` (face and
voice are *corroborating* sources; the result carries an `IdentityAssurance`). A
request-scoped `FusedIdentityResolver` composes face → voice → optional PIN and
replaces `compose_face_then_pin_resolver` and the `transcribe.py` speaker wrapper.
`evaluate_authorization` denies a request whose sensitivity includes a
high-assurance category unless the actor's assurance is `strong`.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI with `Annotated` style, aiosqlite,
pytest with `pytest-asyncio`, `uv` workspace. No new dependency.

**Spec:** [ADR 0016 — Identify the owner by face; require more assurance for
reserved data](../../adr/0016-face-and-voice-identity-fusion.md) (Accepted
2026-09-30), refining [ADR 0015](../../adr/0015-owner-grant-scope-and-speaker-binding.md)
decision 2. The plan argues from the ADR; read both.

---

## Source of truth

Authority order, highest first: runtime `AGENTS.md`;
[`implementation-guardrails.md`](../../architecture/implementation-guardrails.md);
accepted ADRs [0004](../../adr/0004-local-first-cognitive-policy.md),
[0006](../../adr/0006-personal-and-family-companion-profiles.md),
[0008](../../adr/0008-progressive-owner-authentication.md),
[0009](../../adr/0009-locked-posture-and-scoped-capabilities.md),
[0015](../../adr/0015-owner-grant-scope-and-speaker-binding.md),
[0016](../../adr/0016-face-and-voice-identity-fusion.md);
[`current-state.md`](../../architecture/current-state.md);
[`identity-and-access.md`](../../architecture/identity-and-access.md);
[the roadmap](../../roadmap/cognitive-roadmap.md); then this plan.

Code and tests on `main` outrank any prose here. A contradiction stops the work and
is reported — it is never designed around.

## Required reading (after promotion, in this order)

1. `AGENTS.md` and `.claude/rules/` in full.
2. [`implementation-guardrails.md`](../../architecture/implementation-guardrails.md).
3. [ADR 0016](../../adr/0016-face-and-voice-identity-fusion.md) in full, then ADR 0015
   decision 2, ADR 0006 and ADR 0008.
4. [`identity-and-access.md`](../../architecture/identity-and-access.md): *Identity
   evidence*, *Active person context*, *Initial fusion rules*.
5. [`current-state.md`](../../architecture/current-state.md): the rows *Consented local
   face evidence (Plan 0029 / PC-2)* and *Speaker recognition (Plan 0053 / PC-3B)*.
6. [Plan 0053](../completed/0053-consented-speaker-runtime-evidence.md), *Closure
   record* — what voice does today and what was not measured.
7. Code, read before writing: `cognition/identity.py`, `cognition/authorization.py`,
   `cognition/face_authentication.py`, `cognition/speaker_authentication.py`,
   `cognition/owner_authentication.py`, `routers/transcribe.py`, `schemas.py`,
   `schemas_streaming.py`; tests `tests/unit/test_active_person_identity.py`,
   `tests/unit/test_face_authentication.py`, `tests/unit/test_household_authorization_policy.py`,
   `tests/unit/test_speaker_actor_wrapper.py`, `tests/integration/test_face_authenticated_turn.py`,
   `tests/integration/test_speaker_evidence_turn.py`.

No item of `project-history/` is required reading.

---

## Re-audit record (2026-09-30)

Queue rule 4/6: the row's assumptions were re-checked against merged code (`main` at
`aeb3e32`), not memory. The row's **product outcome does not change**; what changed is
the shape of the work.

| # | Finding | Evidence on `main` | Effect |
|---|---|---|---|
| R-1 | A face alone already identifies at the only authorization gate | `identity.py` `_TRUSTED_IDENTIFIED_SOURCES` contains `FACE`; `authorization.py` `_is_resolved_actor` requires `IDENTIFIED` | The default stays; what is new is an **assurance level** on top |
| R-2 | `VOICE` is unresolvable | `_RESOLVABLE_SOURCES = {MANUAL, LOCAL_UNLOCK, FACE, SESSION}`; `test_resolver_returns_unknown_for_voice_evidence` pins it | Plan 0053's invariant is deliberately relaxed here: `VOICE` becomes *corroborating*, never sufficient |
| R-3 | Composition is a precedence chain in two places | `face_authentication.compose_face_then_pin_resolver`; `transcribe._speaker_augmented_actor_resolver` | Both are replaced by one resolver |
| R-4 | The Plan 0053 wrapper reads the owner id from the DB on protected turns | `transcribe.py`: `get_active_owner_pin_credential()` | Unneeded: the id comes from the identified face |
| R-5 | The policy has a closed sensitivity vocabulary and one live protected capability | `DataSensitivity`; only the child read exists; no `SECURITY` data | The high-assurance rule is proven with a synthetic request |
| R-6 | The speaker verdict has no "not the owner" outcome | `SpeakerVerdict` = `verified`, `unknown`, `unavailable` | No voice veto is introduced |
| R-7 | The face verdict cannot tell "another enrolled person" from "unknown" | `evaluate_face_authentication` returns `UNKNOWN` for a non-owner role | New `OTHER_PERSON` verdict feeds the veto |
| R-8 | `identity_source` is `Literal["face", "local_unlock"]` in two schemas; the robot does not read it | `schemas.py`, `schemas_streaming.py`; `grep -r identity_source robot/` is empty | Adding `"face_voice"` is additive |
| R-9 | Plan 0050 (draft) and the future Plan 0051 also edit `transcribe.py` | Both drafts | The agreed order runs them after PC-4; re-audit them when promoted |

Nothing in the re-audit contradicts the row or the ADRs.

## Decisions taken (2026-09-30, Pipec)

Recorded in ADR 0016; restated as constraints.

| # | Decision |
|---|---|
| D-1 | The owner's face alone identifies, with assurance `basic` (default path, unchanged from today) |
| D-2 | Face + verified voice of the same person → assurance `strong`; an optional PIN token is also `strong` |
| D-3 | `HIGH_ASSURANCE_CATEGORIES = {SECURITY}` requires `strong`; all else (incl. `CHILD_DATA`) needs `basic`. No reserved capability exists yet, so a synthetic request proves the rule |
| D-4 | Veto only on positive evidence of another person (another enrolled face, or two or more faces), even with a PIN token, and without consuming it |
| D-5 | The PIN is optional and administrative (enrolment and revocation over loopback); it is not promoted in the daily path |
| D-6 | Recovery when biometrics fail is local administration on the server host; no spoken recovery step |
| D-7 | The denial text never changes; the reason goes only to the log as a closed enum |
| D-8 | Replay/liveness is measured and recorded as residual risk, not defended |
| D-9 | `identity_source` gains `"face_voice"` |
| D-10 | `insufficient_assurance` (ADR 0016 §8) is not a fusion reason: it is the `policy_id` `p0.5.assurance-required` of the authorization audit row. The fusion enum has the other seven |

---

## Global Constraints

Every task's requirements implicitly include this section.

- **API contract:** `POST /transcribe` keeps
  `{ text_heard, llm_response, audio_base64, duration_ms, emotion }` plus the fields
  added by Plans 0026–0029. The only wire change is one additive `identity_source`
  value, `"face_voice"`, in `TranscribeResponse` and the streaming `done` event.
- **Audio contract:** WAV, 16 000 Hz, mono, signed int16, documented in every function
  that touches audio.
- **Fail closed:** every failure produces a non-identifying outcome; no path raises to
  the caller; no bare `except`; every `except` names its exception and preserves the
  cause.
- **Privacy:** no name, transcript, distance or score reaches a log line, an audit row
  or a response body; the log carries the closed reason enum only.
- **Real household data never enters the repository.** Tests use synthetic embeddings,
  generated audio and invented canaries. `scripts/check_reserved_terms.py` passes on
  every commit.
- **Python style:** type hints on every signature, Google docstrings on public APIs,
  `logger` never `print`, `pathlib.Path` never `os.path`, `Annotated` FastAPI style,
  no `Any` without a justification comment.
- **Commits:** Conventional Commits, title 72 characters or fewer, one commit per task,
  verified with `git log` after each one.
- **No new dependency, no new environment variable.**
- No lint, type, coverage or security configuration is weakened to pass.
- `resolve_active_person` stays the single place that turns evidence into a status.

## Review Focus

Failure modes the ADR implies that no obvious task test would exercise, most likely
first. Each has its test in the task that owns the code.

1. **Voice evidence for a person other than the face's.** It must not upgrade or
   identify anyone. *Task 1 (rule, `test_face_and_voice_of_different_people_are_ambiguous`)
   and Task 4 (resolver ignores a foreign candidate).*
2. **A veto must not burn the PIN token.** Two faces with a valid token deny, and the
   same token still works alone afterwards. *Task 4 (unit) and Task 5 (integration).*
3. **A dead or unverified voice while the face matched must still answer at `basic`,**
   never raise and never fail the turn. *Task 4 and Task 5.*
4. **A reserved request answered at `basic` is denied with `p0.5.assurance-required`,**
   while `CHILD_DATA` at `basic` (and at no assurance) is still allowed. *Task 2.*
5. **Public turns and turns with no owner face never load the face or voice stack.**
   *Task 5 (embed not awaited without a face) plus the existing subprocess import test.*

---

## Non-goals

- Liveness, anti-replay defence, or a spoken challenge (D-8).
- A "voice rejected" verdict, or any voice veto (ADR 0016 §4).
- Removing or scoping the PIN, and binding grants to operations — Plan 0051.
- Multi-member households, a second enrolled person, diarization — PC-6.
- The seed load of the household (Paso 0) and any onboarding change.
- Recalibrating any threshold, or touching `scripts/speaker_calibration*`.
- Any cloud provider anywhere (ADR-0004).

## File structure

Nothing outside this list may be created or modified. A file the implementation turns
out to need that is not listed stops the work and is reported.

**Create**

| File | Single responsibility |
|---|---|
| `server/src/server/cognition/identity_fusion.py` | `FusedIdentityResolver`, `FusionReason`, `build_fused_identity_resolver` |
| `tests/unit/test_identity_fusion.py` | Task 4 |
| `tests/integration/test_identity_fusion_turn.py` | Task 5 |

**Modify**

| File | Change |
|---|---|
| `server/src/server/cognition/identity.py` | `IdentityAssurance`, `ActivePersonContext.assurance`, the corroboration rule |
| `server/src/server/cognition/authorization.py` | `HIGH_ASSURANCE_CATEGORIES` and the `p0.5.assurance-required` denial |
| `server/src/server/cognition/face_authentication.py` | `OTHER_PERSON` verdict; delete `compose_face_then_pin_resolver` |
| `server/src/server/routers/transcribe.py` | Use the fused resolver; delete the Plan 0053 wrapper; `identity_source` |
| `server/src/server/schemas.py`, `server/src/server/schemas_streaming.py`, `server/src/server/streaming.py` | `identity_source` gains `"face_voice"` (`streaming.py` was missing from the original list; Pipec authorized it during execution) |
| `tests/unit/test_active_person_identity.py`, `tests/unit/test_household_authorization_policy.py`, `tests/unit/test_face_authentication.py`, `tests/integration/test_speaker_evidence_turn.py` | As each task states |
| `docs/architecture/current-state.md`, `docs/architecture/identity-and-access.md`, `docs/runbooks/operator-manual.md`, `docs/roadmap/cognitive-roadmap.md`, `docs/roadmap/personal-companion-delivery-map.md`, `docs/plans/README.md`, `docs/plans/open/README.md`, `docs/adr/0015-owner-grant-scope-and-speaker-binding.md`, this plan | Closure documentation |
| `docs/architecture/diagrams/current-state.{json,html}` | Regenerated with the Archify skill after `current-state.md` changes |

**Delete:** `tests/unit/test_speaker_actor_wrapper.py` (its wrapper is replaced; the
behaviors it pinned move to Task 4).

**Never touched:** `cognition/speaker_authentication.py`, `voice/`, `memory/`,
`scripts/speaker_calibration*.py`, `robot/src/`, `cognition/owner_authentication.py`.

---

## Task 0: Freeze the base and re-verify the re-audit

**Files:** none. No code in this task.

- [ ] **Step 1: Branch from an up-to-date `main`**

```bash
git checkout main && git pull --ff-only
git checkout -b feat/0054-identity-fusion
```

- [ ] **Step 2: Re-verify the load-bearing findings**

```bash
grep -n "_TRUSTED_IDENTIFIED_SOURCES = \|_RESOLVABLE_SOURCES = " server/src/server/cognition/identity.py
grep -n "def compose_face_then_pin_resolver" server/src/server/cognition/face_authentication.py
grep -n "def _speaker_augmented_actor_resolver\|identity_source" server/src/server/routers/transcribe.py
grep -rn "identity_source" robot/src | head -1
```

Expected: `FACE` inside `_TRUSTED_IDENTIFIED_SOURCES` and `VOICE` absent from
`_RESOLVABLE_SOURCES`; both composers present; `robot/src` prints nothing. **Any
mismatch stops the plan and is reported to Pipec — it is not worked around.**

- [ ] **Step 3: Confirm the green baseline**

Run: `just gate`
Expected: PASS. Record the test count; later tasks grow from it.

---

## Task 1: The corroboration rule and the assurance level

**Files:**
- Modify: `server/src/server/cognition/identity.py`
- Test: `tests/unit/test_active_person_identity.py`

**Interfaces:**
- Produces: `IdentityAssurance` (`NONE`, `BASIC`, `STRONG`, a `str` enum in the module's
  existing `_Enum` style); `ActivePersonContext.assurance: IdentityAssurance = NONE`;
  `resolve_active_person` sets it as ADR 0016 §2 tables.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_active_person_identity.py` add `IdentityAssurance` to the import
block, **delete** `test_resolver_returns_unknown_for_voice_evidence` (Plan 0053's pin,
deliberately relaxed here), and append:

```python
def _source_evidence(
    source: IdentityEvidenceSource,
    person_id: int = 42,
    *,
    expires_at: datetime | None = None,
) -> IdentityEvidence:
    """Build evidence of one source for one person, observed just before resolution."""
    return IdentityEvidence(
        evidence_id=uuid4(),
        source=source,
        candidate_person_id=person_id,
        confidence=_confidence(),
        observed_at=_RESOLVED_AT - timedelta(minutes=1),
        expires_at=expires_at,
        reference=f"{source.value}-match",
    )


_FACE = IdentityEvidenceSource.FACE
_VOICE = IdentityEvidenceSource.VOICE
_PIN = IdentityEvidenceSource.LOCAL_UNLOCK
_MANUAL = IdentityEvidenceSource.MANUAL
_SESSION = IdentityEvidenceSource.SESSION
_CONTEXT = IdentityEvidenceSource.CONTEXT


@pytest.mark.parametrize(
    ("sources", "status", "assurance"),
    [
        ((_FACE,), ActivePersonStatus.IDENTIFIED, IdentityAssurance.BASIC),
        ((_FACE, _VOICE), ActivePersonStatus.IDENTIFIED, IdentityAssurance.STRONG),
        ((_VOICE,), ActivePersonStatus.PROBABLE, IdentityAssurance.NONE),
        ((_PIN,), ActivePersonStatus.IDENTIFIED, IdentityAssurance.STRONG),
        ((_PIN, _FACE), ActivePersonStatus.IDENTIFIED, IdentityAssurance.STRONG),
        ((_PIN, _VOICE), ActivePersonStatus.IDENTIFIED, IdentityAssurance.STRONG),
        ((_PIN, _FACE, _VOICE), ActivePersonStatus.IDENTIFIED, IdentityAssurance.STRONG),
        ((_MANUAL,), ActivePersonStatus.IDENTIFIED, IdentityAssurance.BASIC),
        ((_SESSION,), ActivePersonStatus.PROBABLE, IdentityAssurance.NONE),
        ((_SESSION, _VOICE), ActivePersonStatus.PROBABLE, IdentityAssurance.NONE),
        ((_CONTEXT,), ActivePersonStatus.UNKNOWN, IdentityAssurance.NONE),
    ],
)
def test_the_fusion_table_for_one_person(
    sources: tuple[IdentityEvidenceSource, ...],
    status: ActivePersonStatus,
    assurance: IdentityAssurance,
) -> None:
    """ADR 0016 §2 as data: every combination of sources for one verified person."""
    context = _resolve(tuple(_source_evidence(source) for source in sources), {42: _person(42)})

    assert context.status is status
    assert context.assurance is assurance
    if status is ActivePersonStatus.UNKNOWN:
        assert context.person_id is None


def test_face_and_voice_of_different_people_are_ambiguous() -> None:
    """Review Focus 1: corroboration needs the SAME person; conflict is never resolved."""
    context = _resolve(
        (_source_evidence(_FACE, 42), _source_evidence(_VOICE, 7)),
        {42: _person(42), 7: _person(7)},
    )

    assert context.status is ActivePersonStatus.AMBIGUOUS
    assert context.person_id is None
    assert context.assurance is IdentityAssurance.NONE


def test_expired_voice_evidence_leaves_the_face_at_basic() -> None:
    """Review Focus 3: a stale voice degrades to the default path, it does not deny."""
    expired = _source_evidence(_VOICE, expires_at=_RESOLVED_AT - timedelta(seconds=1))

    context = _resolve((_source_evidence(_FACE), expired), {42: _person(42)})

    assert context.status is ActivePersonStatus.IDENTIFIED
    assert context.assurance is IdentityAssurance.BASIC


def test_a_context_defaults_to_no_assurance() -> None:
    """Default construction never claims assurance."""
    context = _resolve((), {})

    assert context.status is ActivePersonStatus.UNKNOWN
    assert context.assurance is IdentityAssurance.NONE
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_active_person_identity.py -v`
Expected: FAIL — `cannot import name 'IdentityAssurance'`.

- [ ] **Step 3: Implement the rule**

In `server/src/server/cognition/identity.py`:

1. Add `"IdentityAssurance"` to `__all__` (alphabetical).
2. After `ActivePersonStatus`, add:

```python
class IdentityAssurance(str, _Enum):  # noqa: UP042
    """How strongly the evidence of one turn establishes the actor (ADR 0016).

    `BASIC` is the owner's face alone (or a manual selection); `STRONG` is face and
    voice of the same person agreeing, or an owner unlock grant. Reserved data
    categories require `STRONG`. `NONE` is carried by every non-identified result.
    """

    NONE = "none"
    BASIC = "basic"
    STRONG = "strong"
```

3. Add the field to `ActivePersonContext` (after `resolved_at`):

```python
    assurance: IdentityAssurance = IdentityAssurance.NONE
```

4. Replace `_RESOLVABLE_SOURCES`:

```python
_TRUSTED_IDENTIFIED_SOURCES = frozenset(
    {
        IdentityEvidenceSource.MANUAL,
        IdentityEvidenceSource.LOCAL_UNLOCK,
        IdentityEvidenceSource.FACE,
    }
)
# VOICE is resolvable but never trusted on its own: it corroborates a face (ADR 0016).
_RESOLVABLE_SOURCES = _TRUSTED_IDENTIFIED_SOURCES | {
    IdentityEvidenceSource.SESSION,
    IdentityEvidenceSource.VOICE,
}


def _assurance_for(sources: frozenset[IdentityEvidenceSource]) -> IdentityAssurance:
    """Return the assurance that a set of agreeing sources establishes (ADR 0016 §2)."""
    if IdentityEvidenceSource.LOCAL_UNLOCK in sources:
        return IdentityAssurance.STRONG
    if IdentityEvidenceSource.FACE in sources and IdentityEvidenceSource.VOICE in sources:
        return IdentityAssurance.STRONG
    if sources & _TRUSTED_IDENTIFIED_SOURCES:
        return IdentityAssurance.BASIC
    return IdentityAssurance.NONE
```

5. In `resolve_active_person`'s single-person branch, compute `sources` and pass the
   assurance only when identified. Replace the `return ActivePersonContext(...)` of
   that branch with:

```python
        sources = frozenset(item.source for item, _ in candidates)
        return ActivePersonContext(
            person_id=selected_person.person_id,
            display_name=selected_person.display_name,
            status=status,
            confidence=selected_evidence.confidence,
            role=lookup_role(selected_person.person_id),
            evidence=evidence,
            resolved_at=resolved_at,
            assurance=(
                _assurance_for(sources)
                if status is ActivePersonStatus.IDENTIFIED
                else IdentityAssurance.NONE
            ),
        )
```

Update the module docstring line of `resolve_active_person` ("manual or session
evidence") to say it fuses manual, session, local-unlock, face and voice evidence.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_active_person_identity.py -v`
Expected: all pass. If `test_active_person_context_is_immutable_utc_and_json_round_trips`
asserts an exact key set, add `"assurance": "none"` to it — nothing else.

- [ ] **Step 5: Commit**

```bash
git add server/src/server/cognition/identity.py tests/unit/test_active_person_identity.py
git commit -m "feat(cognition): fuse face and voice into an assurance level"
git log -1 --pretty=%s
```

---

## Task 2: Reserved categories require `strong`

**Files:**
- Modify: `server/src/server/cognition/authorization.py`
- Test: `tests/unit/test_household_authorization_policy.py`

**Interfaces:**
- Consumes: Task 1's `IdentityAssurance`.
- Produces: `HIGH_ASSURANCE_CATEGORIES: frozenset[DataSensitivity]` = `{SECURITY}`;
  the denial `policy_id="p0.5.assurance-required"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_household_authorization_policy.py` (add
`IdentityAssurance` to the `identity` import):

```python
def _strong(actor: ActivePersonContext) -> ActivePersonContext:
    return actor.model_copy(update={"assurance": IdentityAssurance.STRONG})


def _basic(actor: ActivePersonContext) -> ActivePersonContext:
    return actor.model_copy(update={"assurance": IdentityAssurance.BASIC})


def _reserved_read(actor: ActivePersonContext) -> AuthorizationRequest:
    return _request(
        actor,
        action=AuthorizationAction.READ_HOUSEHOLD_DATA,
        visibility=frozenset({DataVisibility.PERSONAL}),
        sensitivity=frozenset({DataSensitivity.SECURITY}),
        consent=ConsentStatus.GRANTED,
        target_person_id=7,
    )


def test_reserved_data_is_denied_at_basic_assurance() -> None:
    """Review Focus 4: a face alone must not open account numbers or passwords."""
    decision = evaluate_authorization(_reserved_read(_basic(_actor(role=HouseholdRole.OWNER))))

    assert decision.decision is AuthorizationStatus.DENIED
    assert decision.policy_id == "p0.5.assurance-required"


def test_reserved_data_is_denied_without_any_assurance() -> None:
    decision = evaluate_authorization(_reserved_read(_actor(role=HouseholdRole.OWNER)))

    assert decision.decision is AuthorizationStatus.DENIED
    assert decision.policy_id == "p0.5.assurance-required"


def test_reserved_data_is_allowed_at_strong_assurance() -> None:
    decision = evaluate_authorization(_reserved_read(_strong(_actor(role=HouseholdRole.OWNER))))

    assert decision.decision is AuthorizationStatus.ALLOWED
    assert decision.policy_id == "p0.5.owner-sensitive-consent"


@pytest.mark.parametrize("assurance", [IdentityAssurance.NONE, IdentityAssurance.BASIC])
def test_child_data_does_not_need_strong_assurance(assurance: IdentityAssurance) -> None:
    """The live protected capability keeps working on the default face path."""
    actor = _actor(role=HouseholdRole.OWNER).model_copy(update={"assurance": assurance})

    decision = evaluate_authorization(
        _request(
            actor,
            action=AuthorizationAction.READ_HOUSEHOLD_DATA,
            visibility=frozenset({DataVisibility.PERSONAL}),
            sensitivity=frozenset({DataSensitivity.CHILD_DATA}),
            consent=ConsentStatus.GRANTED,
            target_person_id=7,
        )
    )

    assert decision.decision is AuthorizationStatus.ALLOWED
    assert decision.policy_id == "p0.5.owner-sensitive-consent"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_household_authorization_policy.py -v`
Expected: FAIL — the `SECURITY` cases are allowed today (`policy_id` mismatch).

- [ ] **Step 3: Implement**

In `server/src/server/cognition/authorization.py`, import `IdentityAssurance` from
`server.cognition.identity`, then after `_SENSITIVE_CATEGORIES` add:

```python
# Categories whose reads need face-and-voice agreement or an owner unlock (ADR 0016
# §3). Only SECURITY today; others join when a capability declares them.
HIGH_ASSURANCE_CATEGORIES = frozenset({DataSensitivity.SECURITY})


def _lacks_required_assurance(request: AuthorizationRequest) -> bool:
    """Return whether a reserved request is made with less than `strong` assurance."""
    return (
        bool(request.sensitivity & HIGH_ASSURANCE_CATEGORIES)
        and request.actor.assurance is not IdentityAssurance.STRONG
    )
```

and in `evaluate_authorization`, between the `_is_resolved_actor` check and
`return _evaluate_resolved_request(request)`:

```python
    if _lacks_required_assurance(request):
        return _decision(
            request,
            AuthorizationStatus.DENIED,
            "p0.5.assurance-required",
            "Reserved data needs face and voice agreement or an owner unlock.",
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_household_authorization_policy.py tests/unit/test_active_person_identity.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add server/src/server/cognition/authorization.py tests/unit/test_household_authorization_policy.py
git commit -m "feat(cognition): require strong assurance for reserved data"
git log -1 --pretty=%s
```

---

## Task 3: The `OTHER_PERSON` face verdict

**Files:**
- Modify: `server/src/server/cognition/face_authentication.py`
- Test: `tests/unit/test_face_authentication.py`

**Interfaces:**
- Produces: `FaceAuthenticationVerdict.OTHER_PERSON = "other_person"`; a strict match
  whose role is not `OWNER` returns it (before the consent check); the resolver answers
  it with the ambiguous actor. `compose_face_then_pin_resolver` is **not** removed yet
  (Task 4 replaces its callers, then deletes it).

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_face_authentication.py` **replace**
`test_one_face_match_consent_but_non_owner_role_is_unknown` and
`test_match_within_threshold_consent_but_non_owner_role_resolves_unknown` with:

```python
@pytest.mark.unit
@pytest.mark.parametrize("consent_active", [True, False])
def test_one_face_match_of_a_non_owner_is_positive_evidence_of_another_person(
    consent_active: bool,
) -> None:
    """ADR 0016 §4: a match with someone who is not the owner vetoes, consent or not."""
    verdict = evaluate_face_authentication(
        detected_face_count=1,
        match=_match(0.1),
        consent_active=consent_active,
        role=HouseholdRole.ADULT,
    )
    assert verdict is FaceAuthenticationVerdict.OTHER_PERSON


@pytest.mark.unit
async def test_match_within_threshold_of_a_non_owner_resolves_ambiguous() -> None:
    """A close match with another enrolled person denies and never identifies."""

    async def detect_one(_frame: bytes) -> list[DetectedFace]:
        return [_face(1)]

    async def match_close(_embedding: np.ndarray) -> FaceMatch | None:
        return _match(0.1)

    async def role_adult(_person_id: int) -> HouseholdRole:
        return HouseholdRole.ADULT

    resolver = _resolver(
        frame=_FRAME, detect_faces=detect_one, match_face=match_close, read_role=role_adult
    )

    actor = await resolver.resolve_actor(_event())

    assert actor.status is ActivePersonStatus.AMBIGUOUS
    assert actor.person_id is None
    assert resolver.last_verdict is FaceAuthenticationVerdict.OTHER_PERSON
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_face_authentication.py -v`
Expected: FAIL — `OTHER_PERSON` does not exist.

- [ ] **Step 3: Implement**

In `face_authentication.py`:

1. Add the enum member (after `AMBIGUOUS`): `OTHER_PERSON = "other_person"`.
2. In `evaluate_face_authentication`, replace the tail (after the `match is None`
   check) and update the docstring `Returns`:

```python
    if match is None:
        return FaceAuthenticationVerdict.UNKNOWN
    if role is not HouseholdRole.OWNER:
        # Positive evidence of another enrolled person: a veto, consent or not.
        return FaceAuthenticationVerdict.OTHER_PERSON
    if not consent_active:
        return FaceAuthenticationVerdict.UNKNOWN
    return FaceAuthenticationVerdict.IDENTIFIED
```

3. Give `_ambiguous_active_person` a reason argument:

```python
def _ambiguous_active_person(
    event: CognitiveEvent[TextTurnPayload], reason: str = "Multiple faces detected in frame"
) -> ActivePersonContext:
```
   and use `reason=reason` in its `Confidence`.
4. In `FaceRequestResolver._resolve`, after the `AMBIGUOUS` branch add:

```python
        if verdict is FaceAuthenticationVerdict.OTHER_PERSON:
            return _ambiguous_active_person(event, "Face matches another enrolled person")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_face_authentication.py -v`
Expected: all pass (the composition tests still pass; Task 4 moves them).

- [ ] **Step 5: Commit**

```bash
git add server/src/server/cognition/face_authentication.py tests/unit/test_face_authentication.py
git commit -m "feat(cognition): report a face that matches another enrolled person"
git log -1 --pretty=%s
```

---

## Task 4: The fused resolver

**Files:**
- Create: `server/src/server/cognition/identity_fusion.py`
- Create: `tests/unit/test_identity_fusion.py`

**Interfaces:**
- Consumes: `FaceRequestResolver.resolve_actor`, `.last_verdict`, `.resolve_consent`
  (Task 3); `SpeakerRequestResolver.resolve_actor`, `.last_verdict` (unchanged, Plan 0053);
  `OwnerRequestResolver.resolve_actor`, `.resolve_consent`, `.consumed`;
  `resolve_active_person` and `IdentityAssurance` (Task 1).
- Produces:
  - `FusionReason` (`PIN`, `FACE_AND_VOICE`, `FACE_ONLY`, `VETO_OTHER_PERSON`,
    `VETO_MULTIPLE_FACES`, `BACKEND_UNAVAILABLE`, `NO_EVIDENCE`), a `StrEnum`.
  - `FusedIdentityResolver(*, pin, face, speaker_factory, clock)` with
    `async resolve_actor(event) -> ActivePersonContext`,
    `async resolve_consent(event, actor) -> ConsentStatus`, `consumed: bool` (property,
    the PIN grant), `source: Literal["face", "face_voice", "local_unlock"] | None`,
    `last_reason: FusionReason | None`.
  - `build_fused_identity_resolver(pin, *, frame, wav_bytes) -> FusedIdentityResolver`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_identity_fusion.py
"""Unit tests for the request-scoped fusion of face, voice and optional PIN (Plan 0054)."""

from datetime import UTC, datetime, timedelta
import logging
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import numpy as np
import pytest
from server.cognition.authorization import ConsentStatus
from server.cognition.face_authentication import FaceRequestResolver
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityAssurance,
    IdentityEvidence,
    IdentityEvidenceSource,
    PersonRecord,
)
from server.cognition.identity_fusion import FusedIdentityResolver, FusionReason
from server.cognition.identity_sessions import IdentitySessionRegistry
from server.cognition.models import CognitiveEvent, Confidence, ConfidenceBasis
from server.cognition.owner_authentication import OwnerRequestResolver
from server.cognition.response_plan import TextTurnPayload
from server.cognition.speaker_authentication import SpeakerVerdict
from server.vision.faces import DetectedFace, FaceMatch

_NOW = datetime(2026, 9, 30, 10, 0, tzinfo=UTC)
_OWNER_ID = 7
_OWNER = PersonRecord(person_id=_OWNER_ID, display_name="Canary", entity_type="person")
_FRAME = b"fake-jpeg-bytes"


def _event() -> CognitiveEvent[TextTurnPayload]:
    return CognitiveEvent(
        event_id=UUID("33333333-3333-3333-3333-333333333333"),
        schema_version=1,
        event_type="text.turn",
        occurred_at=_NOW,
        recorded_at=_NOW,
        source="audio.transcribe",
        correlation_id=UUID("44444444-4444-4444-4444-444444444444"),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message="canary", conversation_id="canary-scope"),
    )


def _face_resolver(
    *, faces: int = 1, role: HouseholdRole = HouseholdRole.OWNER
) -> FaceRequestResolver:
    """A real FaceRequestResolver over doubles: `faces` detected, a close match."""

    async def detect(_frame: bytes) -> list[DetectedFace]:
        return [
            DetectedFace(embedding=np.zeros(512, dtype=np.float32), score=0.9, width=200.0)
        ] * faces

    async def match(_embedding: np.ndarray) -> FaceMatch | None:
        return FaceMatch(entity_id=_OWNER_ID, name="Canary", distance=0.1)

    async def read_role(_person_id: int) -> HouseholdRole:
        return role

    async def read_person(person_id: int) -> PersonRecord | None:
        return _OWNER if person_id == _OWNER_ID else None

    async def read_consent(_person_id: int) -> bool:
        return True

    return FaceRequestResolver(
        frame=_FRAME,
        clock=lambda: _NOW,
        read_role=AsyncMock(side_effect=read_role),
        read_person=AsyncMock(side_effect=read_person),
        detect_faces=AsyncMock(side_effect=detect),
        match_face=AsyncMock(side_effect=match),
        read_consent=AsyncMock(side_effect=read_consent),
    )


def _unmatched_face_resolver() -> FaceRequestResolver:
    resolver = _face_resolver()
    resolver._match_face = AsyncMock(return_value=None)  # type: ignore[method-assign]
    return resolver


def _voice_evidence(person_id: int = _OWNER_ID, *, expired: bool = False) -> IdentityEvidence:
    return IdentityEvidence(
        evidence_id=uuid4(),
        source=IdentityEvidenceSource.VOICE,
        candidate_person_id=person_id,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
        observed_at=_NOW - timedelta(minutes=2),
        expires_at=_NOW - timedelta(minutes=1) if expired else None,
        reference="in-turn-speaker-evidence",
    )


class _FakeSpeaker:
    """Stands in for SpeakerRequestResolver: a verdict plus the evidence it attached."""

    def __init__(self, verdict: SpeakerVerdict, evidence: tuple[IdentityEvidence, ...]) -> None:
        self.last_verdict = verdict
        self.calls = 0
        self._evidence = evidence

    async def resolve_actor(self, _event: object) -> ActivePersonContext:
        self.calls += 1
        return ActivePersonContext(
            person_id=None,
            display_name=None,
            status=ActivePersonStatus.UNKNOWN,
            confidence=Confidence(
                score=0.0, basis=ConfidenceBasis.NOT_APPLICABLE, calibrated=False
            ),
            role=HouseholdRole.UNKNOWN,
            evidence=self._evidence,
            resolved_at=_NOW,
        )


class _SpeakerFactory:
    """Records how often the speaker resolver is built and for whom."""

    def __init__(self, speaker: _FakeSpeaker) -> None:
        self.speaker = speaker
        self.owner_ids: list[int] = []

    def __call__(self, owner_person_id: int) -> _FakeSpeaker:
        self.owner_ids.append(owner_person_id)
        return self.speaker


def _verified() -> _SpeakerFactory:
    return _SpeakerFactory(_FakeSpeaker(SpeakerVerdict.VERIFIED, (_voice_evidence(),)))


def _pin(*, with_token: bool = False) -> tuple[OwnerRequestResolver, IdentitySessionRegistry]:
    registry = IdentitySessionRegistry(
        lookup_person=lambda _pid: None, clock=lambda: _NOW, ttl=timedelta(seconds=60)
    )
    token = (
        registry.issue_for_person(_OWNER, source=IdentityEvidenceSource.LOCAL_UNLOCK)
        if with_token
        else None
    )
    resolver = OwnerRequestResolver(
        token=token,
        registry=registry,
        read_role=AsyncMock(return_value=HouseholdRole.OWNER),
        read_person=AsyncMock(return_value=_OWNER),
        clock=lambda: _NOW,
    )
    return resolver, registry


def _fused(*, face, speaker_factory=None, pin=None) -> FusedIdentityResolver:  # noqa: ANN001, ANN202
    return FusedIdentityResolver(
        pin=pin or _pin()[0], face=face, speaker_factory=speaker_factory, clock=lambda: _NOW
    )


async def test_face_and_verified_voice_identify_with_strong_assurance() -> None:
    factory = _verified()
    fused = _fused(face=_face_resolver(), speaker_factory=factory)
    event = _event()

    actor = await fused.resolve_actor(event)

    assert actor.status is ActivePersonStatus.IDENTIFIED
    assert actor.assurance is IdentityAssurance.STRONG
    assert fused.last_reason is FusionReason.FACE_AND_VOICE
    assert fused.source == "face_voice"
    assert factory.owner_ids == [_OWNER_ID]
    assert await fused.resolve_consent(event, actor) is ConsentStatus.GRANTED


async def test_face_without_a_verified_voice_stays_at_basic() -> None:
    """Review Focus 3: an unverified voice degrades to the default path."""
    factory = _SpeakerFactory(_FakeSpeaker(SpeakerVerdict.UNKNOWN, ()))
    fused = _fused(face=_face_resolver(), speaker_factory=factory)

    actor = await fused.resolve_actor(_event())

    assert actor.status is ActivePersonStatus.IDENTIFIED
    assert actor.assurance is IdentityAssurance.BASIC
    assert fused.last_reason is FusionReason.FACE_ONLY
    assert fused.source == "face"


async def test_an_unavailable_voice_backend_still_answers_at_basic() -> None:
    factory = _SpeakerFactory(_FakeSpeaker(SpeakerVerdict.UNAVAILABLE, ()))
    fused = _fused(face=_face_resolver(), speaker_factory=factory)

    actor = await fused.resolve_actor(_event())

    assert actor.assurance is IdentityAssurance.BASIC
    assert fused.last_reason is FusionReason.BACKEND_UNAVAILABLE


async def test_without_a_speaker_factory_the_face_is_basic_and_nothing_is_built() -> None:
    fused = _fused(face=_face_resolver(), speaker_factory=None)

    actor = await fused.resolve_actor(_event())

    assert actor.assurance is IdentityAssurance.BASIC
    assert fused.last_reason is FusionReason.FACE_ONLY


async def test_voice_evidence_for_another_person_is_ignored() -> None:
    """Review Focus 1: a foreign candidate can neither upgrade nor identify."""
    factory = _SpeakerFactory(
        _FakeSpeaker(SpeakerVerdict.VERIFIED, (_voice_evidence(person_id=99),))
    )
    fused = _fused(face=_face_resolver(), speaker_factory=factory)

    actor = await fused.resolve_actor(_event())

    assert actor.person_id == _OWNER_ID
    assert actor.assurance is IdentityAssurance.BASIC
    assert fused.last_reason is FusionReason.FACE_ONLY


async def test_expired_voice_evidence_leaves_the_face_at_basic() -> None:
    factory = _SpeakerFactory(
        _FakeSpeaker(SpeakerVerdict.VERIFIED, (_voice_evidence(expired=True),))
    )
    fused = _fused(face=_face_resolver(), speaker_factory=factory)

    actor = await fused.resolve_actor(_event())

    assert actor.assurance is IdentityAssurance.BASIC


async def test_the_speaker_is_built_and_consulted_once_per_request() -> None:
    factory = _verified()
    fused = _fused(face=_face_resolver(), speaker_factory=factory)

    for _ in range(3):
        await fused.resolve_actor(_event())

    assert factory.owner_ids == [_OWNER_ID]
    assert factory.speaker.calls == 1


async def test_a_face_that_is_not_the_owner_never_consults_voice_or_pin() -> None:
    """Face unknown: voice is not consulted (nothing to corroborate)."""
    factory = _verified()
    fused = _fused(face=_unmatched_face_resolver(), speaker_factory=factory)

    actor = await fused.resolve_actor(_event())

    assert actor.status is ActivePersonStatus.UNKNOWN
    assert factory.owner_ids == []
    assert fused.last_reason is FusionReason.NO_EVIDENCE


async def test_another_enrolled_person_vetoes_even_with_a_valid_token() -> None:
    """Review Focus 2: the veto does not consume the PIN token."""
    pin, _registry = _pin(with_token=True)
    factory = _verified()
    fused = _fused(face=_face_resolver(role=HouseholdRole.ADULT), speaker_factory=factory, pin=pin)

    actor = await fused.resolve_actor(_event())

    assert actor.status is ActivePersonStatus.AMBIGUOUS
    assert fused.last_reason is FusionReason.VETO_OTHER_PERSON
    assert pin.consumed is False
    assert factory.owner_ids == []


async def test_two_faces_veto_even_with_a_valid_token_and_keep_the_token() -> None:
    pin, registry = _pin(with_token=True)
    fused = _fused(face=_face_resolver(faces=2), speaker_factory=_verified(), pin=pin)

    actor = await fused.resolve_actor(_event())

    assert actor.status is ActivePersonStatus.AMBIGUOUS
    assert fused.last_reason is FusionReason.VETO_MULTIPLE_FACES
    assert pin.consumed is False
    assert registry.evidence_for(pin._token) is not None  # type: ignore[arg-type]  # still valid


async def test_an_unknown_face_falls_through_to_a_valid_pin_token() -> None:
    pin, _registry = _pin(with_token=True)
    fused = _fused(face=_unmatched_face_resolver(), speaker_factory=None, pin=pin)
    event = _event()

    actor = await fused.resolve_actor(event)

    assert actor.status is ActivePersonStatus.IDENTIFIED
    assert actor.assurance is IdentityAssurance.STRONG
    assert fused.last_reason is FusionReason.PIN
    assert fused.source == "local_unlock"
    assert fused.consumed is True
    assert await fused.resolve_consent(event, actor) is ConsentStatus.GRANTED


async def test_a_face_identified_owner_never_consumes_the_pin_token() -> None:
    pin, _registry = _pin(with_token=True)
    fused = _fused(face=_face_resolver(), speaker_factory=None, pin=pin)

    await fused.resolve_actor(_event())

    assert pin.consumed is False


async def test_no_face_and_no_token_is_unknown_with_no_evidence() -> None:
    fused = _fused(face=None, speaker_factory=_verified())
    event = _event()

    actor = await fused.resolve_actor(event)

    assert actor.status is ActivePersonStatus.UNKNOWN
    assert fused.last_reason is FusionReason.NO_EVIDENCE
    assert fused.source is None
    assert await fused.resolve_consent(event, actor) is ConsentStatus.NOT_REQUIRED


async def test_the_log_carries_the_reason_and_no_personal_data(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fused = _fused(face=_face_resolver(), speaker_factory=_verified())

    with caplog.at_level(logging.INFO):
        await fused.resolve_actor(_event())

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "face_and_voice" in joined
    assert "Canary" not in joined
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_identity_fusion.py -v`
Expected: FAIL — `No module named 'server.cognition.identity_fusion'`.

- [ ] **Step 3: Write the resolver**

```python
# server/src/server/cognition/identity_fusion.py
"""Request-scoped fusion of face, voice and optional PIN evidence (Plan 0054, ADR 0016).

One resolver per HTTP request. The order is fixed: face first; voice only when the face
matched the owner (the only case in which it can corroborate); the PIN only when a token
was presented and nothing resolved or vetoed. Positive evidence of another person (another
enrolled face, or two or more faces) vetoes and never consumes the PIN token. The final
status and assurance come from `resolve_active_person`, the single place that fuses
evidence. Voice is a corroborating source: it can raise a face to `strong`, never identify.

Audio contract for every WAV the speaker resolver touches: WAV, 16 000 Hz, mono, signed
int16.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from functools import partial
import logging
from typing import Literal

from server.cognition.authorization import ConsentStatus
from server.cognition.face_authentication import (
    FaceAuthenticationVerdict,
    FaceRequestResolver,
    build_default_face_request_resolver,
)
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    IdentityAssurance,
    PersonRecord,
    resolve_active_person,
)
from server.cognition.models import CognitiveEvent
from server.cognition.owner_authentication import OwnerRequestResolver
from server.cognition.response_plan import TextTurnPayload
from server.cognition.speaker_authentication import (
    SpeakerRequestResolver,
    SpeakerVerdict,
    build_default_speaker_resolver,
)
from server.settings import settings

logger = logging.getLogger(__name__)

__all__ = ["FusedIdentityResolver", "FusionReason", "build_fused_identity_resolver"]

type Clock = Callable[[], datetime]
type SpeakerFactory = Callable[[int], SpeakerRequestResolver]
type IdentitySource = Literal["face", "face_voice", "local_unlock"]


class FusionReason(StrEnum):
    """Closed reason for one turn's identity outcome — the only thing logged (ADR 0016 §8)."""

    PIN = "pin"
    FACE_AND_VOICE = "face_and_voice"
    FACE_ONLY = "face_only"
    VETO_OTHER_PERSON = "veto_other_person"
    VETO_MULTIPLE_FACES = "veto_multiple_faces"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    NO_EVIDENCE = "no_evidence"


class FusedIdentityResolver:
    """Resolve the actor of one request from face, voice and an optional PIN token."""

    def __init__(
        self,
        *,
        pin: OwnerRequestResolver,
        face: FaceRequestResolver | None,
        speaker_factory: SpeakerFactory | None,
        clock: Clock,
    ) -> None:
        """Create a resolver for exactly one HTTP request.

        Args:
            pin: Request-scoped PIN resolver (Plan 0025/0026); consulted last.
            face: Request-scoped face resolver, or `None` when no frame is usable.
            speaker_factory: Builds the speaker resolver for the identified owner's
                id, or `None` when speaker evidence is disabled or there is no audio.
            clock: Source of the resolution timestamp.
        """
        self._pin = pin
        self._face = face
        self._speaker_factory = speaker_factory
        self._clock = clock
        self._cached: ActivePersonContext | None = None
        self.last_reason: FusionReason | None = None
        self.source: IdentitySource | None = None

    @property
    def consumed(self) -> bool:
        """Whether this request consumed a fresh one-use owner PIN grant."""
        return self._pin.consumed

    async def resolve_actor(self, event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        """Resolve the actor once per request; later calls return the cached result.

        Args:
            event: The protected event this resolution is scoped to.

        Returns:
            The identified owner (`basic` from the face, `strong` with a corroborating
            voice or a PIN grant), the ambiguous actor on a veto, or the unknown actor.
        """
        if self._cached is not None:
            return self._cached
        context = await self._resolve(event)
        self._cached = context
        logger.info(
            "Identity fusion: %s",
            self.last_reason.value if self.last_reason else "none",
            extra={"event": "identity.fusion", "reason": self.last_reason},
        )
        return context

    async def resolve_consent(
        self, event: CognitiveEvent[TextTurnPayload], actor: ActivePersonContext
    ) -> ConsentStatus:
        """Grant scoped consent only through the path that identified the owner."""
        if self.source in {"face", "face_voice"} and self._face is not None:
            return await self._face.resolve_consent(event, actor)
        if self._pin.consumed:
            return await self._pin.resolve_consent(event, actor)
        return ConsentStatus.NOT_REQUIRED

    async def _resolve(self, event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        if self._face is not None:
            face_context = await self._face.resolve_actor(event)
            verdict = self._face.last_verdict
            if verdict is FaceAuthenticationVerdict.AMBIGUOUS:
                self.last_reason = FusionReason.VETO_MULTIPLE_FACES
                return face_context
            if verdict is FaceAuthenticationVerdict.OTHER_PERSON:
                self.last_reason = FusionReason.VETO_OTHER_PERSON
                return face_context
            if face_context.status is ActivePersonStatus.IDENTIFIED:
                return await self._with_voice(event, face_context)
        pin_context = await self._pin.resolve_actor(event)
        if self._pin.consumed:
            self.last_reason = FusionReason.PIN
            self.source = "local_unlock"
        else:
            self.last_reason = FusionReason.NO_EVIDENCE
        return pin_context

    async def _with_voice(
        self, event: CognitiveEvent[TextTurnPayload], face_context: ActivePersonContext
    ) -> ActivePersonContext:
        """Raise an identified face to `strong` when the voice of the same person agrees."""
        self.source = "face"
        self.last_reason = FusionReason.FACE_ONLY
        owner_id = face_context.person_id
        if self._speaker_factory is None or owner_id is None:
            return face_context
        speaker = self._speaker_factory(owner_id)
        voice_context = await speaker.resolve_actor(event)
        if speaker.last_verdict is SpeakerVerdict.UNAVAILABLE:
            self.last_reason = FusionReason.BACKEND_UNAVAILABLE
            return face_context
        voice_evidence = tuple(
            item for item in voice_context.evidence if item.candidate_person_id == owner_id
        )
        if speaker.last_verdict is not SpeakerVerdict.VERIFIED or not voice_evidence:
            return face_context
        person = PersonRecord(
            person_id=owner_id, display_name=face_context.display_name or "", entity_type="person"
        )
        fused = resolve_active_person(
            evidence=face_context.evidence + voice_evidence,
            lookup_person=lambda person_id: person if person_id == owner_id else None,
            lookup_role=lambda _person_id: face_context.role,
            clock=self._clock,
        )
        if fused.assurance is not IdentityAssurance.STRONG:
            return face_context
        self.source = "face_voice"
        self.last_reason = FusionReason.FACE_AND_VOICE
        return fused


def _utc_now() -> datetime:
    """Return the current aware UTC timestamp for production boundaries."""
    return datetime.now(UTC)


def build_fused_identity_resolver(
    pin: OwnerRequestResolver, *, frame: bytes | None, wav_bytes: bytes | None
) -> FusedIdentityResolver:
    """Compose the production resolver for one request.

    Args:
        pin: The request's PIN resolver.
        frame: Validated webcam frame bytes, or `None` (no frame, or
            `settings.face_authentication_enabled` is off).
        wav_bytes: The turn's own audio — WAV, 16 000 Hz, mono, int16 — used only
            when `settings.speaker_authentication_enabled` is on.

    Returns:
        A resolver wired to the real face and speaker resolvers.
    """
    face = (
        build_default_face_request_resolver(frame)
        if settings.face_authentication_enabled and frame is not None
        else None
    )
    speaker_factory: SpeakerFactory | None = (
        partial(build_default_speaker_resolver, wav_bytes)
        if settings.speaker_authentication_enabled and wav_bytes is not None
        else None
    )
    return FusedIdentityResolver(
        pin=pin, face=face, speaker_factory=speaker_factory, clock=_utc_now
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_identity_fusion.py -v`
Expected: all pass. If `OwnerRequestResolver._token` or `registry.evidence_for` differ from
what the veto test uses, read `owner_authentication.py` / `identity_sessions.py` and use the
public equivalent (the assertion's intent is "the token is still spendable").

- [ ] **Step 5: Run the wider unit suite**

Run: `uv run ruff check --fix server tests && uv run ruff format server tests && uv run mypy server/src robot/src && uv run pytest tests/unit -q`
Expected: clean and green. The old composers stay until Task 5 rewires `transcribe.py`; nothing is deleted here.

- [ ] **Step 6: Commit**

```bash
git add server/src/server/cognition/identity_fusion.py tests/unit/test_identity_fusion.py
git commit -m "feat(cognition): fuse face, voice and pin in one resolver"
git log -1 --pretty=%s
```

---

## Task 5: Wire the turn, retire the old composers, prove it end to end

**Files:**
- Modify: `server/src/server/routers/transcribe.py`, `server/src/server/schemas.py`,
  `server/src/server/schemas_streaming.py`
- Modify: `server/src/server/cognition/face_authentication.py` (delete `compose_face_then_pin_resolver`, its `__all__` entry and imports left unused)
- Modify: `tests/unit/test_face_authentication.py` (delete the composition section — from the `# compose_face_then_pin_resolver` banner to the end of the file — and the imports it leaves unused)
- Delete: `tests/unit/test_speaker_actor_wrapper.py`
- Modify: `tests/integration/test_speaker_evidence_turn.py`
- Create: `tests/integration/test_identity_fusion_turn.py`

**Interfaces:**
- Consumes: Task 4's `build_fused_identity_resolver`, `FusedIdentityResolver`.
- Produces: `identity_source: Literal["face", "face_voice", "local_unlock"] | None` in both
  schemas.

- [ ] **Step 1: Write the failing integration tests**

```python
# tests/integration/test_identity_fusion_turn.py
"""Face, voice and PIN through the real /transcribe routes (Plan 0054, ADR 0016).

Detection and the speaker embedding are doubles; face matching, the voice centroid and the
database are real. Audio is generated in code — never a human recording.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
import io
import json
from pathlib import Path
from unittest.mock import AsyncMock
import wave

import cv2
from httpx import ASGITransport, AsyncClient
import numpy as np
from pydantic import SecretStr
import pytest
from server.cognition import (
    face_authentication as face_auth_module,
    speaker_authentication as speaker_auth_module,
)
from server.cognition.identity import PersonRecord
from server.cognition.identity_sessions import IdentitySessionRegistry
from server.cognition.owner_authentication import OwnerUnlockService, owner_unlock_service
from server.dependencies import get_owner_unlock_service
from server.main import app
from server.memory.biometric_consent import grant_face_consent
from server.memory.entity_labels import get_person_label
from server.memory.household_authorization import get_active_role
from server.memory.owner_credentials import get_active_owner_pin_credential
from server.memory.voice_consent import grant_voice_consent
from server.personal_setup import PersonalSetupInput, PersonalSetupResult, apply_personal_setup
from server.resources import AppResources
from server.settings import settings
from server.voice.speaker_embedding import SpeakerBackendError, model_id
from server.voice.voiceprints import enroll_voiceprint
from server.vision.faces import DetectedFace, enroll_face

from server import db, stt, tts

_CHILD_ANSWER = "Tus hijos son Joaquín y Martina."
_CHILD_QUESTION = "¿Quiénes son mis hijos?"
_PIN = "482173"
_OWNER_NAME = "Pipec"
_FRAME = cv2.imencode(".jpg", np.zeros((10, 10, 3), dtype=np.uint8))[1].tobytes()


def _axis(size: int, axis: int) -> np.ndarray:
    vector = np.zeros(size, dtype=np.float32)
    vector[axis] = 1.0
    return vector


_OWNER_FACE = _axis(512, 0)
_STRANGER_FACE = _axis(512, 1)
_MATCHING_VOICE = _axis(192, 0)  # distance ~0.42 to the centroid of axes 0..2
_OTHER_VOICE = _axis(192, 10)  # orthogonal: distance 1.0


def _detected(embedding: np.ndarray) -> DetectedFace:
    return DetectedFace(embedding=embedding, score=0.9, width=200.0)


def _tone_wav(seconds: float = 3.0) -> bytes:
    t = np.linspace(0.0, seconds, int(16_000 * seconds), endpoint=False)
    samples = (8_000 * np.sin(2 * np.pi * 220 * t)).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(samples.tobytes())
    return buffer.getvalue()


@pytest.fixture
async def fusion_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[PersonalSetupResult]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "identity-fusion.db")
    monkeypatch.setattr(settings, "face_authentication_enabled", True)
    monkeypatch.setattr(settings, "speaker_authentication_enabled", True)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    result = await apply_personal_setup(
        PersonalSetupInput(
            owner_name=_OWNER_NAME, child_names=("Joaquín", "Martina"), pin=SecretStr(_PIN)
        )
    )
    await grant_face_consent(result.owner_entity_id)
    await enroll_face(result.owner_entity_id, _OWNER_FACE, label=_OWNER_NAME)
    await grant_voice_consent(result.owner_entity_id)
    for axis in range(3):
        await enroll_voiceprint(result.owner_entity_id, _axis(192, axis), "owner", model_id())
    yield result
    await db.close_db()
    db._conn = None


def _detect(monkeypatch: pytest.MonkeyPatch, faces: list[DetectedFace]) -> AsyncMock:
    mock = AsyncMock(return_value=faces)
    monkeypatch.setattr(face_auth_module, "_detect_faces_default", mock)
    return mock


def _embed(monkeypatch: pytest.MonkeyPatch, result: object) -> AsyncMock:
    mock = (
        AsyncMock(side_effect=result)
        if isinstance(result, Exception)
        else AsyncMock(return_value=result)
    )
    monkeypatch.setattr(speaker_auth_module, "embed_wav", mock)
    return mock


def _mock_stt_tts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value=_CHILD_QUESTION))
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("AAAA", 42)))


def _files(*, with_frame: bool = True) -> dict[str, tuple[str, bytes, str]]:
    files = {"audio": ("a.wav", _tone_wav(), "audio/wav")}
    if with_frame:
        files["frame"] = ("frame.jpg", _FRAME, "image/jpeg")
    return files


async def _read_person_record(person_entity_id: int) -> PersonRecord | None:
    label = await get_person_label(entity_id=person_entity_id)
    if label is None:
        return None
    return PersonRecord(
        person_id=label.entity_id, display_name=label.display_name, entity_type="person"
    )


def _service() -> OwnerUnlockService:
    registry = IdentitySessionRegistry(
        lookup_person=lambda _pid: None, clock=lambda: datetime.now(UTC), ttl=timedelta(seconds=60)
    )
    return OwnerUnlockService(
        clock=lambda: datetime.now(UTC),
        registry=registry,
        read_credential=get_active_owner_pin_credential,
        read_role=get_active_role,
        read_person=_read_person_record,
    )


@asynccontextmanager
async def _client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient() as http_client:
        app.state.resources = AppResources(
            http_client=http_client, owner_unlock_service=owner_unlock_service
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.mark.integration
async def test_owner_face_and_matching_voice_answer_at_strong_assurance(
    fusion_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    _detect(monkeypatch, [_detected(_OWNER_FACE)])
    embed = _embed(monkeypatch, _MATCHING_VOICE)
    _mock_stt_tts(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe", files=_files())

    body = response.json()
    assert response.status_code == 200
    assert body["llm_response"] == _CHILD_ANSWER
    assert body["identity_source"] == "face_voice"
    assert body["authentication_consumed"] is False
    embed.assert_awaited_once()


@pytest.mark.integration
async def test_owner_face_with_a_different_voice_still_answers_at_basic(
    fusion_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default path: a photograph plus another speaker opens ordinary private data."""
    _detect(monkeypatch, [_detected(_OWNER_FACE)])
    _embed(monkeypatch, _OTHER_VOICE)
    _mock_stt_tts(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe", files=_files())

    body = response.json()
    assert body["llm_response"] == _CHILD_ANSWER
    assert body["identity_source"] == "face"


@pytest.mark.integration
async def test_a_dead_speaker_backend_does_not_fail_the_face_turn(
    fusion_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review Focus 3."""
    _detect(monkeypatch, [_detected(_OWNER_FACE)])
    _embed(monkeypatch, SpeakerBackendError("model unavailable"))
    _mock_stt_tts(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe", files=_files())

    assert response.status_code == 200
    assert response.json()["llm_response"] == _CHILD_ANSWER
    assert response.json()["identity_source"] == "face"


@pytest.mark.integration
async def test_a_verified_voice_without_a_face_denies_and_is_never_embedded(
    fusion_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review Focus 5: a recording alone opens nothing and costs nothing."""
    embed = _embed(monkeypatch, _MATCHING_VOICE)
    _mock_stt_tts(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe", files=_files(with_frame=False))

    body = response.json()
    assert "Joaquín" not in body["llm_response"]
    assert body["identity_source"] is None
    embed.assert_not_awaited()


@pytest.mark.integration
async def test_two_faces_with_a_valid_token_deny_and_keep_the_token(
    fusion_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review Focus 2, end to end: the veto denies, then the same token still works."""
    service = _service()
    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    embed = _embed(monkeypatch, _MATCHING_VOICE)
    _mock_stt_tts(monkeypatch)
    headers = {"X-Iroko-Identity-Token": unlock.token}

    _detect(monkeypatch, [_detected(_OWNER_FACE), _detected(_STRANGER_FACE)])
    async with _client() as client:
        vetoed = await client.post("/transcribe", headers=headers, files=_files())
        alone = await client.post("/transcribe", headers=headers, files=_files(with_frame=False))

    assert "Joaquín" not in vetoed.json()["llm_response"]
    assert vetoed.json()["authentication_consumed"] is False
    assert alone.json()["llm_response"] == _CHILD_ANSWER
    assert alone.json()["identity_source"] == "local_unlock"
    embed.assert_not_awaited()


@pytest.mark.integration
async def test_speaker_evidence_off_leaves_the_face_at_basic_and_never_embeds(
    fusion_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "speaker_authentication_enabled", False)
    _detect(monkeypatch, [_detected(_OWNER_FACE)])
    embed = _embed(monkeypatch, _MATCHING_VOICE)
    _mock_stt_tts(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe", files=_files())

    assert response.json()["identity_source"] == "face"
    embed.assert_not_awaited()


@pytest.mark.integration
async def test_stream_route_reports_the_strong_source(
    fusion_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    _detect(monkeypatch, [_detected(_OWNER_FACE)])
    _embed(monkeypatch, _MATCHING_VOICE)
    _mock_stt_tts(monkeypatch)

    async with _client() as client:
        response = await client.post("/transcribe/stream", files=_files())

    events = [json.loads(line) for line in response.text.strip().split("\n") if line.strip()]
    assert events[-1]["identity_source"] == "face_voice"
    assert [e for e in events if e["type"] == "audio"][0]["text"] == _CHILD_ANSWER
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/integration/test_identity_fusion_turn.py -v`
Expected: FAIL — `identity_source` never equals `"face_voice"`; the schema rejects the value.

- [ ] **Step 3: Wire the turn and the schemas**

In `schemas.py` and `schemas_streaming.py` change the `identity_source` annotation to
`Literal["face", "face_voice", "local_unlock"] | None` and its description to mention voice.

In `routers/transcribe.py`:

1. Replace `_RequestIdentity` and `_build_request_identity`, and **delete**
   `_speaker_augmented_actor_resolver`:

```python
@dataclass
class _RequestIdentity:
    """Uniform per-request actor/consent resolver over the fused identity evidence.

    Attributes:
        resolve_actor: The actor resolver to hand to the controller.
        resolve_consent: The matching consent resolver.
        pin: The underlying PIN resolver, used to report `.consumed`.
        fused: The fusion resolver, used to report `.identity_source`.
    """

    resolve_actor: ActivePersonResolver
    resolve_consent: ConsentResolver
    pin: OwnerRequestResolver
    fused: FusedIdentityResolver

    @property
    def consumed(self) -> bool:
        """Whether this request consumed a fresh one-use owner PIN unlock grant."""
        return self.pin.consumed

    @property
    def identity_source(self) -> Literal["face", "face_voice", "local_unlock"] | None:
        """Which evidence identified the actor, or `None` for none."""
        return self.fused.source


def _build_request_identity(
    owner_unlock_service: OwnerUnlockService,
    token: str | None,
    frame: bytes | None,
    wav_bytes: bytes | None,
) -> _RequestIdentity:
    """Compose this request's actor/consent resolver (Plan 0054, ADR 0016).

    Args:
        owner_unlock_service: Lifespan-owned unlock service (Plan 0040).
        token: Optional one-use owner PIN unlock token from the request header.
        frame: Optional validated webcam frame; `None` when absent or face
            authentication is off.
        wav_bytes: The turn's own audio — WAV, 16 000 Hz, mono, int16.

    Returns:
        A `_RequestIdentity` over one `FusedIdentityResolver`.
    """
    pin = owner_unlock_service.for_request(token)
    fused = build_fused_identity_resolver(pin, frame=frame, wav_bytes=wav_bytes)
    return _RequestIdentity(
        resolve_actor=fused.resolve_actor,
        resolve_consent=fused.resolve_consent,
        pin=pin,
        fused=fused,
    )
```

2. Fix the imports (`ruff check --fix` removes the rest): import
   `FusedIdentityResolver, build_fused_identity_resolver` from
   `server.cognition.identity_fusion`; drop `FaceRequestResolver`,
   `build_default_face_request_resolver`, `compose_face_then_pin_resolver`,
   `SpeakerRequestResolver`, `build_default_speaker_resolver`, `ActivePersonStatus`,
   `get_active_owner_pin_credential`, `aiosqlite`, and `BrainMemoryError` if now unused.
3. Delete `compose_face_then_pin_resolver`, the composition tests in
   `test_face_authentication.py` and `git rm tests/unit/test_speaker_actor_wrapper.py`. Their
   behaviours (identified face short-circuits the PIN, ambiguity denies without the PIN,
   unknown falls through, consent routing) are pinned by Task 4's tests.

- [ ] **Step 4: Update the Plan 0053 turn tests that assumed the old order**

In `tests/integration/test_speaker_evidence_turn.py`:

- `test_flag_on_reads_the_audio_exactly_once` → rename to
  `test_flag_on_without_a_face_never_embeds` and assert `embed.assert_not_awaited()`
  (voice is only consulted after an owner's face; the face-present cases live in
  `test_identity_fusion_turn.py`).
- `test_flag_on_stream_route_consults_the_speaker_once` → rename to
  `test_flag_on_stream_without_a_face_never_embeds`, same assertion.
- Leave `test_flag_on_still_denies_a_protected_question_without_pin_or_face`,
  `test_a_backend_failure_does_not_fail_the_turn`, the role-change test and the subprocess
  import test unchanged.

- [ ] **Step 5: Run the affected suites**

Run:
```bash
uv run ruff check --fix server tests && uv run ruff format server tests
uv run mypy server/src robot/src
uv run pyright
uv run pytest tests/integration/test_identity_fusion_turn.py tests/integration/test_speaker_evidence_turn.py tests/integration/test_face_authenticated_turn.py tests/integration/test_owner_authenticated_turn.py tests/integration/test_owner_authenticated_stream.py tests/integration/test_api_contract.py tests/unit -q
```
Expected: all pass. `test_face_authenticated_turn.py` must pass **unedited**: the face alone
still answers (`identity_source == "face"`). If it fails, the default path regressed — stop
and fix the code, not the test.

- [ ] **Step 6: Commit**

```bash
git add server tests
git commit -m "feat(transcribe): resolve identity from face, voice and pin together"
git log -1 --pretty=%s
```

---

## Task 6: Documentation closure

**Files:** see the Modify table's docs rows. No code.

- [ ] **Step 1:** `current-state.md`: rewrite the *Consented local face evidence* known-gap sentence and the *Speaker recognition* row from measured evidence — the face is the default at `basic`, voice raises to `strong`, reserved data (`SECURITY`) needs `strong`, no reserved capability exists yet, replay is measured but not defended.
- [ ] **Step 2:** `identity-and-access.md`: replace *Initial fusion rules* with the ADR 0016 table and the assurance levels; keep the sentence that identity is never authorization.
- [ ] **Step 3:** `operator-manual.md`: rewrite *Tier 3* (voice raises assurance) and *Tier 4* (fusion is implemented; PIN is optional and administrative; recovery is local administration); add nothing to the flag table (no new variable).
- [ ] **Step 4:** ADR index and ADR 0015: add "decision 2 refined by [ADR 0016](0016-face-and-voice-identity-fusion.md)" to ADR 0015's status line and the index row.
- [ ] **Step 5:** roadmap PC-4 row and personal-companion map, plan indexes (`docs/plans/README.md`, `docs/plans/open/README.md`), and this plan's closure record — each stating plainly that replay is not defended and that no reserved capability exists yet.
- [ ] **Step 6:** Regenerate the architecture diagram with the Archify skill (`validate` then `deliver`, from `.claude/skills/archify`, using POSIX paths). Update the "Known gaps" card first.
- [ ] **Step 7:** `uv run ruff format --check .`, `uv run ruff check .`, `uv run python scripts/check_reserved_terms.py`, and a mechanical link/anchor check on the touched docs.
- [ ] **Step 8: Commit** — `docs(plan): document face-default identity fusion`.

---

## Task 7: Real acceptance, closure and review

- [ ] **Step 1:** `just gate`. Expected: PASS, test count grown by the new tests, coverage at or above the floor.
- [ ] **Step 2: Hand the acceptance list to Pipec and wait.** Do not proceed until he reports outcomes for every case in [What needs Pipec's real hardware](#what-needs-pipecs-real-hardware). An agent never claims any of them.
- [ ] **Step 3:** Record the outcomes (outcomes only) in this plan's closure record and in `current-state.md`; move this plan to `completed/`.
- [ ] **Step 4:** Independent whole-branch review with `superpowers:requesting-code-review`; resolve findings with `superpowers:receiving-code-review`. Pipec decides whether it is a subagent or his own reading.
- [ ] **Step 5:** `superpowers:finishing-a-development-branch`. One PR, squash-merge, branch deleted.

---

## What needs Pipec's real hardware

An agent can produce none of this. These steps run locally on Pipec's own webcam and
microphone with `just run-server` and `just run-robot` (face and speaker authentication on)
and record **outcomes only** — never a frame, audio, name or score.

| # | Case | Expected |
|--:|---|---|
| 1 | You alone, normal light, ask for your children | Answers; server log `Identity fusion: face_and_voice` |
| 2 | You, face visible, voice muffled or whispering | Answers at `basic`; log `face_only` |
| 3 | Photo of you held to the camera, another person speaking | Ordinary private data answers (accepted, as today); log `face_only` |
| 4 | Your voice recorded and played, no face in frame | Denial; log `no_evidence`; no embedding |
| 5 | Photo of you **plus** the recording of the exact question | Answers — **residual risk, recorded, not defended** |
| 6 | Two people in frame | Denial; log `veto_multiple_faces` |
| 7 | Camera covered or dark room | Denial; recovery is local administration, not a spoken step |
| 8 | Speaker model files removed, you in frame | Answers at `basic`; log `backend_unavailable` |
| 9 | Optional, only if you hold a PIN token: two faces + token, then the token alone | First denies, second answers |

Reserved data (`SECURITY`) has no live capability yet, so its `strong` requirement is
proven by the policy tests, not on hardware. Delete every captured file afterward.

## What an agent may never do in this plan

- Record, capture, request, imitate, synthesize, clone or replay a human voice or face,
  in any task, for any reason.
- Touch the microphone or the webcam, or run any command that would.
- Copy a frame, audio, embedding, score or real name into a tracked file, a fixture, a
  commit message or a document.
- Claim an acceptance step Pipec did not run and report.
- Weaken a threshold, a veto, `_RESOLVABLE_SOURCES` semantics beyond ADR 0016, or any
  authorization rule to make a test pass.

Test data is generated in code: axis-aligned synthetic embeddings and a generated sine
tone; detection and the speaker embedding are doubles.

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
grep -rn "compose_face_then_pin_resolver\|_speaker_augmented_actor_resolver" server tests
```

Expected: no match.

## Completion criteria

1. Every task's RED test was observed failing first, and all gates above are green with no
   configuration weakened.
2. `tests/integration/test_face_authenticated_turn.py` passes unedited: the face alone still
   answers ordinary private data.
3. A request with `SECURITY` sensitivity is denied at `basic` with `p0.5.assurance-required`
   and allowed at `strong`; `CHILD_DATA` is allowed at `basic`.
4. Face and voice of different people, or another enrolled person's face, never identify;
   a veto never consumes the PIN token.
5. A dead or unverified voice while the owner's face matched answers at `basic`; no path
   raises to the caller.
6. Public turns and turns without an owner face never build or run the speaker resolver.
7. `identity_source` gains only `"face_voice"`; no other wire change.
8. No name, transcript, distance or score appears in any log, audit row or response.
9. Pipec's real-hardware run recorded outcomes for every case, including the residual
   photo-plus-recording result.
10. Documentation closure states plainly what stays open: replay undefended, no reserved
    capability yet, PIN scoping is Plan 0051.

## Rollback boundary

There is no flag: the default path (the owner's face alone answers ordinary private data)
is unchanged. The additions are the `strong` upgrade, the reserved-data rule (no capability
consumes it yet) and the veto. Rolling back means reverting the PR; no migration is involved.

## Risks

| Risk | Why it matters | Mitigation |
|---|---|---|
| Photograph alone still opens ordinary private data | Unchanged from today | Named in ADR 0016 and the closure record; reserved data needs `strong` |
| Photograph plus a recording of the exact question opens reserved data | Replay is not defended | Measured by Pipec, recorded as residual risk; a liveness plan only if it matters |
| `VOICE` leaves the "unresolvable" invariant of Plan 0053 | A regression could let voice identify alone | The parametrized fusion table pins `(VOICE,)` → `probable`/`none`; Task 1 |
| Removing the composers touches a hot path | A wiring mistake fails every protected turn | `test_face_authenticated_turn.py` must pass unedited; end-to-end tests in Task 5 |
| Embedding cost on every protected turn whose face matched | About 0.5 s | Accepted in ADR 0016; public turns pay nothing |
| Plans 0050/0051 also edit `transcribe.py` | Merge conflict | Agreed order runs them after PC-4; re-audit when promoted |

## Self-review record (2026-09-30)

1. **Spec coverage.** ADR 0016 §1–§2 → Task 1; §3 → Task 2; §4 → Tasks 3–4; §5 → Task 4;
   §6 (PIN optional) → Task 4 (PIN last, token kept) and Task 6 docs; §7 (recovery) → Task 6
   docs and hardware case 7; §8 (reasons, `identity_source`) → Tasks 4–5; §9 (replay) →
   hardware cases 3–5. No requirement is left without a task.
2. **Placeholder scan.** Task 6 lists documentation edits by target and content rather than
   prose; every code step shows code. The old composers are deleted in Task 5, once
   `transcribe.py` stops importing them.
3. **Type consistency.** `IdentityAssurance` (Task 1) is consumed by Tasks 2 and 4;
   `FusedIdentityResolver.source` is exactly the `identity_source` literal of Task 5;
   `FaceAuthenticationVerdict.OTHER_PERSON` (Task 3) is what Task 4 branches on;
   `SpeakerVerdict` and `SpeakerRequestResolver` are unchanged from Plan 0053.
4. **Review Focus.** All five entries have an owning task and a named test.

## Closure record

**Status of this record: Tasks 0–6 done; Task 7 (Pipec's real hardware) pending.** Outcomes
only — never a frame, audio, name or score.

### Execution record (2026-09-30, branch `feat/0054-identity-fusion`)

- Baseline on `main` (`35f9eb5`, after PR #148 was squash-merged at Pipec's instruction):
  `just gate` passed, 1529 tests.
- One commit per task, each new test observed RED first (Task 1: `ImportError`; Task 2: the
  two `SECURITY` denials returned `allowed`; Task 3: no `OTHER_PERSON`; Task 4: no module;
  Task 5: `identity_source` never `face_voice` and the old wrapper embedded without a face).
  A mutation of the veto ordering was caught by four fused-resolver tests.
- Last full `pytest -n auto` on the branch: 1556 passed. `ruff`, `mypy` and `pyright` clean.
  `tests/integration/test_face_authenticated_turn.py` passes **unedited**. The final
  `just gate` of Task 7 Step 1 is recorded below when run.
- One full run showed two transient timing failures in
  `tests/unit/test_speaker_embedding.py` under `-n auto` load (code this plan does not
  touch): 21/21 in isolation, green on two other full runs.

### Rulings taken during execution

| # | Ruling | Why | Cost if wrong |
|--:|---|---|---|
| 1 | `server/src/server/streaming.py` (`stream_response_plan`'s `identity_source` annotation and its docstring) was modified although it was not in the file list | `mypy` and `pyright` failed at the new value; Pipec authorized it explicitly when asked | Revert one annotation |
| 2 | Task 4's tests use a `matches=False` fixture parameter and a `_Pin` named tuple instead of `_match_face`/`_token` accesses and `type: ignore` | Pipec allowed public equivalents; intent unchanged | None |
| 3 | The two Task 4 veto tests also assert consent is `NOT_REQUIRED` | They replace the deleted composer test that pinned it | None |
| 4 | Stale docstrings in `tests/integration/test_speaker_evidence_turn.py` were updated | They said `_RESOLVABLE_SOURCES` was unedited | None |
| 5 | `cognition/speaker_authentication.py` was **not** edited although its docstrings still say `VOICE` is absent from `_RESOLVABLE_SOURCES` | The plan lists it under "Never touched" | One stale docstring, reported to Pipec |

### What stays open

- **Replay is not defended.** A photograph identifies at `basic`, unchanged; a photograph
  plus a recording of the exact question would satisfy `strong` once a reserved capability
  exists.
- **No reserved capability exists yet.** `HIGH_ASSURANCE_CATEGORIES = {SECURITY}` is proven
  only by synthetic policy tests.
- Scoping the PIN grant to a named operation is Plan 0051.

### Real-hardware outcomes (Task 7 Step 2)

Pending: Pipec runs the nine cases of [What needs Pipec's real hardware](#what-needs-pipecs-real-hardware)
and this section then records the outcome of each, outcomes only.

## Execution handoff

Plan written under `docs/plans/open/` — the project's plan location, which overrides the
skill's default path. It is `Draft` until Pipec reads it and promotes it to `NOW`.

**Recommended execution approach: Native** — `superpowers:executing-plans`, one agent
implementing every task in a fresh Claude Code session, with an independent whole-branch
review at the end. The tasks share interfaces closely (Tasks 1, 2 and 4 build one rule
between them), there are only eight, and Pipec's standing rule is no subagents unless he
asks. A shipped mistake is contained: the default path is unchanged and the new behavior
is additive.
