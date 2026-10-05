# 0051 — Scoped owner grants

> **Status:** `Draft` — written 2026-10-05 as the first plan of CM-1, after the queue
> order was confirmed by Pipec the same day (CM-1 first, then the streaming-protocol
> repair, then CM-2). **Not authorized.** Pipec promotes it to `Ready` and selects it as
> `NOW`; until then `NOW` stays empty and nothing here may be executed. The decisions
> below are proposals for that moment.

> **For agentic workers:** REQUIRED SUB-SKILLS: `superpowers:executing-plans`,
> `superpowers:test-driven-development`, `superpowers:verification-before-completion`,
> `superpowers:finishing-a-development-branch`. Execute only while this is the
> explicitly authorized `NOW` item, in a new session. **Pipec's rules win over the
> skills:** one plain branch from `main` (`git checkout -b`), never a git worktree
> (treat any "create a worktree" instruction as "create the branch"), no subagents
> unless Pipec asks, and this plan lives under `docs/plans/`, not
> `docs/superpowers/plans/`. Implement exactly the tasks below, in order, one commit
> per task. If evidence contradicts the plan, stop and report the conflict instead of
> redesigning. Pipec runs every local process (server, robot, scripts that use the
> camera or the microphone); you record what they print, outcomes only.

**Goal:** Make the owner's PIN grant honour what ADR-0009 already requires and
ADR-0015 accepted: a grant is bound to **one named operation**. A grant issued for a
protected read cannot administer biometrics, a grant issued for biometric
administration cannot read protected data, and the branches that read nothing ("¿Quién
soy?", a household question that is not connected yet) stop spending it.

**Architecture:** The grant registry records the scope a token was issued for and
refuses, without spending the token, a presentation for any other scope. The owner
resolver is built for one scope; the unlock endpoint takes an optional `scope` (absent
means the read scope, so the robot and every existing client are unchanged) and the
four biometric-administration routes build their resolver for `biometric_admin`. The
controller gets a second, **observing** actor seam for the branches that read nothing;
the fused resolver gets the matching `peek_actor` that judges face and voice as usual
and lets a presented token only name its owner. Three scripts that administer
biometrics ask for the admin scope. No migration, no new dependency, no change to what
the robot sends.

**Tech Stack:** Python 3.12, FastAPI, pydantic, pytest (+ xdist). No new dependency.

**Spec:** [ADR-0015](../../adr/0015-owner-grant-scope-and-speaker-binding.md) decision 1
(this plan implements it; decisions 2 and 3 are not touched),
[ADR-0009](../../adr/0009-locked-posture-and-scoped-capabilities.md) (a grant is bound to
a named operation), [ADR-0008](../../adr/0008-progressive-owner-authentication.md) (the
grant proves the PIN, not the speaker) and
[ADR-0016](../../adr/0016-face-and-voice-identity-fusion.md) (the PIN is optional and the
credential of local administration); the CM-1 row of the
[roadmap](../../roadmap/cognitive-roadmap.md#canonical-pre-electronics-delivery-portfolio)
and of the [conversational-memory map](../../roadmap/conversational-memory-delivery-map.md);
the *Capability matrix* rows of [`current-state.md`](../../architecture/current-state.md);
and the two characterization tests of Plan 0050's owner → stranger matrix.

**Rehearsal (2026-10-05).** Every diff and code block below was applied onto a scratch
state of `main` (`2fd36d8`) and reverted. With them applied: `just gate` passed **1854
tests** (baseline 1807, so +47), `ruff check` and `ruff format --check` over the explicit
file paths, `mypy` and `pyright` were clean. Each corrected behaviour was written
test-first and its RED observed for the stated reason (`TypeError: ... unexpected
keyword argument 'scope'`; `AttributeError: ... has no attribute 'BIOMETRIC_ADMIN'` and
`'peek_actor'`; `TypeError: ... unexpected keyword argument 'observed_person_resolver'`;
the 20 existing enrolment tests failing once the admin scope is enforced). Two mutation
checks prove the new tests bite: dropping the admin scope from the enrolment routes
fails the four read-grant refusal tests, and unwiring the observer from the streaming
route fails the streaming "who am I" test. Not rehearsed: Task 6 (real hardware) and
Task 7 (documentation). Treat the blocks as rehearsed code, not as a substitute for the
RED/GREEN record each task requires.

## Global Constraints

- No real household data, voice, face or name in any tracked file, test, prompt, doc or
  commit message: the tests use invented canaries (`scripts/check_reserved_terms.py`
  guards this).
- The PIN and the token are never logged, echoed or committed; a refusal logs one closed
  reason (`scope_mismatch`), never the token.
- Wire changes are **additive only**: `POST /auth/owner/unlock` gains an optional
  `scope` request field and a `scope` response field. No field is removed or renamed.
  The robot sends nothing new and never asks for the administration scope.
- Face and voice stay identity evidence, never authorization and never the sole route
  to administration: biometric administration still needs a fresh PIN grant (ADR-0006,
  ADR-0009).
- Type hints on every signature, Google docstrings on public APIs, `ruff` clean over
  the **explicit paths** of every `scripts/` file touched (`just lint` skips `scripts/`
  but the pre-commit hook does not), `mypy server/src robot/src` clean, `Annotated` for
  FastAPI parameters.
- Every new test is observed RED for the stated reason before its implementation.
- A commit title is at most 72 characters (commitizen rejects longer ones silently):
  check `git log -1` after every commit.

## Review Focus

Inputs the spec implies that are most likely to bite, each pinned by a test in its
owning task:

1. A grant presented to the wrong operation is refused **and not spent**, in both
   directions: a read grant at a biometric-administration route, and an administration
   grant at a protected read. A bystander, or a wrong call, must not burn the owner's
   grant (Tasks 1, 2, 4 and 5).
2. A grant is still one use: after a refused wrong-operation presentation it authorizes
   its own operation exactly once, and a second use is denied (Tasks 2 and 5).
3. "¿Quién soy?" and a household question that reads nothing never spend the grant, yet
   still name the owner and still pass through the policy and the audit with the actor
   that was observed; a stranger gets the same denial as before (Tasks 3 and 5).
4. Only the branch that reads authorized data awaits the resolver that spends the grant
   (Task 5).
5. The wire change is additive: no `scope` means the read scope; an unknown scope
   (`root`, empty, `null`, a number) is a 422 that never echoes the PIN; the response
   says which scope it granted (Task 4).
6. Existing tests must not pass for the wrong reason: every enrolment test that builds a
   token to test expiry or reuse must issue it for `biometric_admin`, or it would deny
   because of the scope instead of the condition it names (Task 4).
7. The three scripts that administer biometrics ask for the admin scope, the list of
   such scripts is pinned, and the robot never asks for it (Task 4).
8. The bearer limit is unchanged and stays pinned: a valid read grant still answers
   whoever presents it (the existing characterization test; Task 5).
9. Nothing sensitive in logs: no PIN, no token, only the closed reason (Task 2).

---

## Why this plan exists

| Finding | Evidence in the merged code | Closed by |
|---|---|---|
| The grant is not bound to an operation (ADR-0015 item 1) | `OwnerUnlockScope` has one member; `OwnerRequestResolver.scope` is computed and read only by a unit test; `resolve_consent` returns `GRANTED` to whatever consumes the token | Tasks 1, 2 |
| Biometric administration consumes a read grant | `routers/auth.py` builds the same unscoped resolver for `/face/enroll`, `/face/revoke` and, since Plan 0053 (after the ADR), `/voice/enroll` and `/voice/revoke` | Task 4 |
| "¿Quién soy?" spends the grant and names the owner | `controller._active_identity_plan` awaits the resolver that consumes the token | Task 5 |
| A household answer that reads nothing spends the grant | `_protected_household_plan(actor=None)` resolves through the consuming resolver, then answers "todavía no está conectada" | Task 5 |
| Three admin scripts unlock without a scope | `scripts/onboard.py`, `face_auth_demo.py`, `speaker_auth_demo.py` post `{"pin": ...}` | Task 4 |
| The optional PIN hardware case was never run | Plan 0054 acceptance, case 9 | Task 6 |
| The grant proves the PIN, not the speaker | ADR-0008, pinned by Plan 0050; staged behind ADR-0015 decision 2 and ADR-0016 | not here |

## Task overview

| # | Task | Closes |
|---:|---|---|
| 0 | Revalidate the baseline | — |
| 1 | The registry records the scope of a token | scope stored, wrong operation refused unspent |
| 2 | Owner service and resolver: scope and `peek_actor` | one grant, one operation |
| 3 | The fused resolver can observe without spending | the matching `peek_actor` |
| 4 | HTTP surface and administration scripts | unlock takes a scope; biometric administration requires it |
| 5 | Branches that read nothing observe the actor | "¿Quién soy?" and the stub keep the grant |
| 6 | Real hardware acceptance | the operator's proof, incl. the unrun PIN case |
| 7 | Documentation truth | ADR-0015, `current-state.md`, the manual, the roadmap |

## Decisions

Proposed 2026-10-05; Pipec confirms them when he promotes the plan, and they are not
asked again afterwards.

1. **D-1 — A closed scope set, additive on the wire.** `personal_protected_read` (the
   default) and `biometric_admin`, as ADR-0015 decision 1 says. `POST /auth/owner/unlock`
   accepts an optional `scope`; absent means the read scope. The robot's startup prompt
   and every existing client are unchanged.
2. **D-2 — A wrong-operation presentation is refused and not spent.** The ADR's reason
   for decision 1 is that a bystander must not burn the owner's grant; refusing a grant
   by *consuming* it would reintroduce that. The refusal looks exactly like an absent
   token (same 401 body, same unknown actor) and logs one closed reason.
3. **D-3 — Observing never spends.** The branches that read nothing use an observing
   seam (`observed_person_resolver`, `peek_actor`): the face and the voice are judged as
   always, and a presented token only names its owner. This keeps the bearer limit
   exactly where ADR-0008 and Plan 0050 pinned it (a valid read grant names and answers
   whoever presents it) and removes only the burning. The observing seam defaults to the
   public unknown actor, so a controller built without it can never spend a grant by
   accident.
4. **D-4 — The unlock response echoes the scope.** Additive; lets a client and a test
   assert what was granted.
5. **D-5 — Later operations are later plans.** `read`, `propose`, `confirm`, `correct`
   and `forget` for personal memory, and the `strong` requirement of `SECURITY` data,
   are the other CM-1 plans and CM-3 to CM-5. The rule this plan establishes for them:
   each new protected capability declares its scope in the plan that adds it. This plan
   adds no capability.
6. **D-6 — The lifetime is unchanged.** `OWNER_UNLOCK_TTL_SECONDS` stays 300 s for both
   scopes (ADR-0015 decision 3). A shorter administration window is a setting away if
   Pipec wants it later.
7. **D-7 — The unrun hardware case is part of this acceptance.** Plan 0054's optional PIN
   case (the PIN answers when the face does not identify) is run in Task 6, with the
   scope cases, in one operator session.

## Required reading

- `AGENTS.md` and `docs/architecture/implementation-guardrails.md`.
- ADR-0006, ADR-0008, ADR-0009, ADR-0015 and ADR-0016.
- `docs/architecture/identity-and-access.md` (*Locked posture and capability scope*) and
  the capability rows of `docs/architecture/current-state.md`.
- `server/src/server/cognition/{owner_authentication,identity_sessions,identity_fusion,controller}.py`,
  `server/src/server/routers/{auth,chat,transcribe}.py`, `server/src/server/schemas_auth.py`,
  `scripts/{onboard,face_auth_demo,speaker_auth_demo}.py` and
  `tests/integration/test_owner_stranger_matrix.py`.

## Permitted files

- `server/src/server/cognition/identity_sessions.py`, `owner_authentication.py`,
  `identity_fusion.py`, `controller.py`
- `server/src/server/schemas_auth.py`, `server/src/server/routers/auth.py`, `chat.py`,
  `transcribe.py`
- `scripts/onboard.py`, `scripts/face_auth_demo.py`, `scripts/speaker_auth_demo.py`
- Tests: `tests/unit/test_identity_sessions.py`, `test_owner_authentication.py`,
  `test_identity_fusion.py`, `test_cognitive_controller.py`, new
  `test_biometric_admin_scope_callers.py`; `tests/integration/test_owner_unlock_endpoint.py`,
  `test_owner_face_enrollment.py`, `test_owner_voice_enrollment.py`,
  `test_owner_stranger_matrix.py`, `test_owner_authenticated_turn.py`,
  `test_owner_authenticated_stream.py`
- Docs: `docs/adr/0015-owner-grant-scope-and-speaker-binding.md`,
  `docs/adr/0016-face-and-voice-identity-fusion.md` (three sentences),
  `docs/architecture/current-state.md` and `docs/architecture/identity-and-access.md`,
  `docs/architecture/diagrams/current-state.{json,html}`, `docs/runbooks/operator-manual.md`,
  `docs/roadmap/cognitive-roadmap.md`, `docs/roadmap/conversational-memory-delivery-map.md`,
  `docs/roadmap/personal-companion-delivery-map.md`, `docs/plans/README.md`,
  `docs/plans/open/README.md`, new `docs/evals/0051-scoped-grant-acceptance.md` and
  `docs/evals/README.md`, and this plan.

No new URL, status code, response field other than `scope`, audio contract, database
schema, migration or dependency. The robot (`robot/src`) is **not** edited.

---

## Task 0: Revalidate the baseline

**Files:** this plan's evidence note only. No production change.

- [ ] **Step 1: Branch.** `git checkout main && git pull`, confirm a clean tree, then
  `git checkout -b feat/0051-scoped-owner-grants`. Record the base SHA.
- [ ] **Step 2: Baseline.** Run `just gate`; record its outcome and test count (the
  baseline after the Plan 0057 documentation and the dependency refresh was 1807). A
  pre-existing failure is reported, not hidden. Known intermittent: one full run of the
  rehearsal of Plan 0057 reported
  `tests/slow/test_speaker_embedding_real_model.py::test_the_real_encoder_returns_the_frozen_shape`
  failing and it passed alone and in the next run; capture the traceback first if it
  reappears.
- [ ] **Step 2b: Re-audit the assumptions against the merged code** (queue rule 4). Each
  command must find what this plan names:
  `rg -n "class OwnerUnlockScope|PERSONAL_PROTECTED_READ" server/src/server/cognition/owner_authentication.py`,
  `rg -n "def issue_for_person|def consume_evidence|def evidence_for" server/src/server/cognition/identity_sessions.py`,
  `rg -n "for_request\(" server/src`,
  `rg -n "_active_person_resolver" server/src/server/cognition/controller.py` (three uses),
  `rg -n "auth/owner/unlock" scripts robot/src` (the three scripts and the robot).
  A difference is reported before any code changes.
- [ ] **Step 3: Pin today's behaviour.** Run
  `uv run pytest tests/integration/test_owner_stranger_matrix.py -q -p no:cacheprovider`
  and record that it passes (it holds the two characterization tests this plan rewrites).

---

## Task 1: The registry records the scope of a token

**Files:**
- Modify: `server/src/server/cognition/identity_sessions.py`
- Test: `tests/unit/test_identity_sessions.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `IdentitySessionRegistry.issue_for_person(person, *, source, scope=None)`,
  `evidence_for(token, *, scope=None)` (never consumes) and
  `consume_evidence(token, *, scope=None)`: with a `scope`, a token issued for another
  scope (or for none) yields `None` and **is kept**; `clear` forgets the scope.

- [ ] **Step 1: Write the failing tests** — append to `tests/unit/test_identity_sessions.py`:

```diff
--- a/tests/unit/test_identity_sessions.py
+++ b/tests/unit/test_identity_sessions.py
@@ -169,3 +169,75 @@ def test_issue_for_person_rejects_a_non_person_record() -> None:

     with pytest.raises(ValueError, match="person"):
         registry.issue_for_person(pet, source=IdentityEvidenceSource.LOCAL_UNLOCK)
+
+
+def _scoped_registry(now: list[datetime]) -> SessionIdentityRegistry:
+    return SessionIdentityRegistry(
+        lookup_person=_lookup({42: _person(42)}),
+        clock=lambda: now[0],
+        ttl=timedelta(minutes=5),
+    )
+
+
+def test_a_token_issued_for_one_scope_is_refused_for_another_and_survives() -> None:
+    """Presenting a grant to the wrong operation never burns it (ADR-0015, Plan 0051)."""
+    now = [_NOW]
+    registry = _scoped_registry(now)
+    token = registry.issue_for_person(
+        _person(42), source=IdentityEvidenceSource.LOCAL_UNLOCK, scope="read"
+    )
+
+    assert registry.consume_evidence(token, scope="admin") is None
+    assert registry.evidence_for(token, scope="admin") is None
+
+    assert registry.evidence_for(token, scope="read") is not None
+    assert registry.consume_evidence(token, scope="read") is not None
+    assert registry.consume_evidence(token, scope="read") is None
+
+
+def test_evidence_for_never_consumes_and_respects_the_scope() -> None:
+    now = [_NOW]
+    registry = _scoped_registry(now)
+    token = registry.issue_for_person(
+        _person(42), source=IdentityEvidenceSource.LOCAL_UNLOCK, scope="read"
+    )
+
+    assert registry.evidence_for(token, scope="read") is not None
+    assert registry.evidence_for(token, scope="read") is not None
+    assert registry.evidence_for(token) is not None  # no scope asked: legacy behaviour
+
+
+def test_a_token_without_a_recorded_scope_is_refused_when_a_scope_is_required() -> None:
+    now = [_NOW]
+    registry = _scoped_registry(now)
+    token = registry.select_person(42)
+    assert token is not None
+
+    assert registry.consume_evidence(token, scope="read") is None
+    assert registry.consume_evidence(token) is not None  # unscoped callers are unchanged
+
+
+def test_an_expired_scoped_token_is_gone_for_every_scope() -> None:
+    now = [_NOW]
+    registry = _scoped_registry(now)
+    token = registry.issue_for_person(
+        _person(42), source=IdentityEvidenceSource.LOCAL_UNLOCK, scope="read"
+    )
+
+    now[0] = _NOW + timedelta(minutes=6)
+
+    assert registry.consume_evidence(token, scope="read") is None
+    assert registry.evidence_for(token) is None
+
+
+def test_clearing_a_token_forgets_its_scope() -> None:
+    now = [_NOW]
+    registry = _scoped_registry(now)
+    token = registry.issue_for_person(
+        _person(42), source=IdentityEvidenceSource.LOCAL_UNLOCK, scope="read"
+    )
+
+    registry.clear(token)
+
+    assert registry.evidence_for(token, scope="read") is None
+    assert registry.consume_evidence(token, scope="read") is None
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_identity_sessions.py -q -p no:cacheprovider`.
  Expected: five failures, `TypeError: IdentitySessionRegistry.issue_for_person() got an
  unexpected keyword argument 'scope'` (and the same for `consume_evidence`).

- [ ] **Step 3: Implement.**

```diff
--- a/server/src/server/cognition/identity_sessions.py
+++ b/server/src/server/cognition/identity_sessions.py
@@ -36,6 +36,8 @@ class IdentitySessionRegistry:
         self._clock = clock
         self._ttl = ttl
         self._evidence_by_token: dict[str, IdentityEvidence] = {}
+        # The operation a token was issued for; a token issued without one has no entry.
+        self._scope_by_token: dict[str, str] = {}

     def select_person(self, person_id: int) -> str | None:
         """Record a manual session selection only for an existing person ID.
@@ -77,14 +79,20 @@ class IdentitySessionRegistry:
         self._evidence_by_token[token] = evidence
         return token

-    def evidence_for(self, token: str) -> IdentityEvidence | None:
-        """Return unexpired safe selection evidence for an opaque token.
+    def _scope_allows(self, token: str, scope: str | None) -> bool:
+        """Whether a caller asking for ``scope`` may use ``token`` (``None`` asks for none)."""
+        return scope is None or self._scope_by_token.get(token) == scope
+
+    def evidence_for(self, token: str, *, scope: str | None = None) -> IdentityEvidence | None:
+        """Return unexpired safe selection evidence for an opaque token, without consuming it.

         Args:
             token: Opaque session token returned by :meth:`select_person`.
+            scope: The operation the caller is about to authorize. When given, a token
+                issued for another operation (or for none) yields ``None``.

         Returns:
-            Immutable evidence when still fresh, otherwise ``None``.
+            Immutable evidence when still fresh and within ``scope``, otherwise ``None``.
         """
         evidence = self._evidence_by_token.get(token)
         if evidence is None:
@@ -92,6 +100,8 @@ class IdentitySessionRegistry:
         if evidence.expires_at is not None and evidence.expires_at <= self._clock():
             self.clear(token)
             return None
+        if not self._scope_allows(token, scope):
+            return None
         return evidence

     def clear(self, token: str) -> None:
@@ -101,14 +111,18 @@ class IdentitySessionRegistry:
             token: Opaque session token returned by :meth:`select_person`.
         """
         self._evidence_by_token.pop(token, None)
+        self._scope_by_token.pop(token, None)

-    def issue_for_person(self, person: PersonRecord, *, source: IdentityEvidenceSource) -> str:
+    def issue_for_person(
+        self, person: PersonRecord, *, source: IdentityEvidenceSource, scope: str | None = None
+    ) -> str:
         """Issue one-use evidence for an already-verified person record.

         Args:
             person: A person record verified by the caller (e.g. a successful
                 local-unlock PIN check), not re-verified here.
             source: The evidence source to record, e.g. ``LOCAL_UNLOCK``.
+            scope: The one operation this token may authorize; ``None`` records none.

         Returns:
             An opaque token that must be redeemed exactly once via
@@ -136,21 +150,29 @@ class IdentitySessionRegistry:
         )
         token = _uuid4().hex
         self._evidence_by_token[token] = evidence
+        if scope is not None:
+            self._scope_by_token[token] = scope
         return token

-    def consume_evidence(self, token: str) -> IdentityEvidence | None:
+    def consume_evidence(self, token: str, *, scope: str | None = None) -> IdentityEvidence | None:
         """Redeem one-use evidence exactly once, then invalidate the token.

         Args:
             token: Opaque token returned by :meth:`issue_for_person` or
                 :meth:`select_person`.
+            scope: The operation the caller authorizes. When given, a token issued for
+                another operation (or for none) is refused and **kept**: presenting a
+                grant to the wrong operation never burns it.

         Returns:
-            The evidence if the token was present and unexpired, else
-            ``None``. The token is removed either way — a second call with
-            the same token always returns ``None``.
+            The evidence if the token was present, within ``scope`` and unexpired, else
+            ``None``. A token that is within ``scope`` is removed either way — a second
+            call with the same token always returns ``None``.
         """
+        if token in self._evidence_by_token and not self._scope_allows(token, scope):
+            return None
         evidence = self._evidence_by_token.pop(token, None)
+        self._scope_by_token.pop(token, None)
         if evidence is None:
             return None
         if evidence.expires_at is not None and evidence.expires_at <= self._clock():
```

- [ ] **Step 4: Run, lint, commit.**
  `uv run pytest tests/unit/test_identity_sessions.py -q -p no:cacheprovider` (13 pass),
  `uv run ruff check` and `uv run ruff format --check` over both paths.
  Commit — `feat(server): bind registry tokens to an operation scope`.

---

## Task 2: Owner service and resolver — scope and `peek_actor`

**Files:**
- Modify: `server/src/server/cognition/owner_authentication.py`
- Test: `tests/unit/test_owner_authentication.py`

**Interfaces:**
- Consumes: Task 1's `issue_for_person(..., scope=)`, `consume_evidence(..., scope=)`,
  `evidence_for(..., scope=)`.
- Produces: `OwnerUnlockScope.BIOMETRIC_ADMIN`; `OwnerUnlockResult.scope`;
  `OwnerUnlockService.unlock(pin, scope=PERSONAL_PROTECTED_READ)`;
  `OwnerUnlockService.for_request(token, scope=PERSONAL_PROTECTED_READ)`;
  `OwnerRequestResolver(..., scope=...)` with `peek_actor(event)` (names the owner, never
  spends), `resolve_actor` (spends, only within its scope) and `scope` (the granted
  capability after consumption). A refusal for scope logs `Owner grant refused:
  scope_mismatch`, never the token.

- [ ] **Step 1: Write the failing tests** — append to `tests/unit/test_owner_authentication.py`:

```diff
--- a/tests/unit/test_owner_authentication.py
+++ b/tests/unit/test_owner_authentication.py
@@ -311,3 +311,138 @@ async def test_the_rate_limit_error_reports_when_to_retry() -> None:
 async def _always_wrong(fn):
     """Stand in for the verifier, always rejecting the candidate."""
     return False
+
+
+# --- Plan 0051: every grant is bound to one named operation (ADR-0015) --------
+
+
+@pytest.mark.unit
+async def test_unlock_defaults_to_the_read_scope_and_can_ask_for_biometric_admin() -> None:
+    service = _service(credential=_credential())
+
+    default = await service.unlock(_PIN)
+    admin = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
+
+    assert default is not None
+    assert default.scope is OwnerUnlockScope.PERSONAL_PROTECTED_READ
+    assert admin is not None
+    assert admin.scope is OwnerUnlockScope.BIOMETRIC_ADMIN
+
+
+@pytest.mark.unit
+async def test_a_read_grant_cannot_authorize_biometric_admin_and_is_not_burned() -> None:
+    service = _service(credential=_credential())
+    unlock = await service.unlock(_PIN)
+    assert unlock is not None
+    event = _event()
+
+    admin = service.for_request(unlock.token, scope=OwnerUnlockScope.BIOMETRIC_ADMIN)
+    refused = await admin.resolve_actor(event)
+    refused_consent = await admin.resolve_consent(event, refused)
+
+    assert refused.status is ActivePersonStatus.UNKNOWN
+    assert admin.consumed is False
+    assert refused_consent is not ConsentStatus.GRANTED
+
+    read = service.for_request(unlock.token)
+    owner = await read.resolve_actor(event)
+    assert owner.status is ActivePersonStatus.IDENTIFIED
+    assert read.consumed is True
+
+
+@pytest.mark.unit
+async def test_a_biometric_admin_grant_cannot_authorize_a_read_and_is_not_burned() -> None:
+    service = _service(credential=_credential())
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
+    assert unlock is not None
+    event = _event()
+
+    read = service.for_request(unlock.token)
+    refused = await read.resolve_actor(event)
+
+    assert refused.status is ActivePersonStatus.UNKNOWN
+    assert read.consumed is False
+
+    admin = service.for_request(unlock.token, scope=OwnerUnlockScope.BIOMETRIC_ADMIN)
+    owner = await admin.resolve_actor(event)
+    consent = await admin.resolve_consent(event, owner)
+    assert owner.status is ActivePersonStatus.IDENTIFIED
+    assert admin.consumed is True
+    assert consent is ConsentStatus.GRANTED
+
+
+@pytest.mark.unit
+async def test_the_granted_scope_names_only_the_operation_that_consumed_the_grant() -> None:
+    service = _service(credential=_credential())
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
+    assert unlock is not None
+    admin = service.for_request(unlock.token, scope=OwnerUnlockScope.BIOMETRIC_ADMIN)
+
+    assert admin.scope == frozenset()  # nothing before consumption
+    await admin.resolve_actor(_event())
+
+    assert admin.scope == frozenset({OwnerUnlockScope.BIOMETRIC_ADMIN.value})
+
+
+@pytest.mark.unit
+async def test_peeking_identifies_the_owner_without_spending_the_grant() -> None:
+    service = _service(credential=_credential())
+    unlock = await service.unlock(_PIN)
+    assert unlock is not None
+    event = _event()
+
+    peeking = service.for_request(unlock.token)
+    seen = await peeking.peek_actor(event)
+    seen_again = await peeking.peek_actor(event)
+
+    assert seen.status is ActivePersonStatus.IDENTIFIED
+    assert seen.person_id == _OWNER_ID
+    assert seen_again.status is ActivePersonStatus.IDENTIFIED
+    assert peeking.consumed is False
+    assert peeking.scope == frozenset()
+
+    reading = service.for_request(unlock.token)
+    assert (await reading.resolve_actor(event)).status is ActivePersonStatus.IDENTIFIED
+    assert reading.consumed is True
+
+
+@pytest.mark.unit
+async def test_peeking_is_unknown_without_a_token_for_this_scope_or_after_expiry() -> None:
+    now = _NOW
+
+    def clock() -> datetime:
+        return now
+
+    service = _service(clock=clock, credential=_credential())
+    unlock = await service.unlock(_PIN)
+    assert unlock is not None
+    event = _event()
+
+    assert (await service.for_request(None).peek_actor(event)).status is ActivePersonStatus.UNKNOWN
+    assert (await service.for_request("not-a-token").peek_actor(event)).status is (
+        ActivePersonStatus.UNKNOWN
+    )
+    admin = service.for_request(unlock.token, scope=OwnerUnlockScope.BIOMETRIC_ADMIN)
+    assert (await admin.peek_actor(event)).status is ActivePersonStatus.UNKNOWN
+
+    now = _NOW + timedelta(seconds=61)
+    assert (await service.for_request(unlock.token).peek_actor(event)).status is (
+        ActivePersonStatus.UNKNOWN
+    )
+
+
+@pytest.mark.unit
+async def test_a_scope_mismatch_is_logged_as_a_closed_reason_and_never_the_token(
+    caplog: pytest.LogCaptureFixture,
+) -> None:
+    service = _service(credential=_credential())
+    unlock = await service.unlock(_PIN)
+    assert unlock is not None
+
+    with caplog.at_level(logging.INFO):
+        admin = service.for_request(unlock.token, scope=OwnerUnlockScope.BIOMETRIC_ADMIN)
+        await admin.resolve_actor(_event())
+
+    joined = "\n".join(record.getMessage() for record in caplog.records)
+    assert "scope_mismatch" in joined
+    assert unlock.token not in joined
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_owner_authentication.py -q -p no:cacheprovider`.
  Expected: seven failures, `AttributeError: type object 'OwnerUnlockScope' has no
  attribute 'BIOMETRIC_ADMIN'` and `'OwnerRequestResolver' object has no attribute
  'peek_actor'`. (The file takes about two minutes: it verifies real scrypt hashes.)

- [ ] **Step 3: Implement.**

```diff
--- a/server/src/server/cognition/owner_authentication.py
+++ b/server/src/server/cognition/owner_authentication.py
@@ -4,14 +4,16 @@ Verifies the persistent PIN credential from the ``personal`` setup, issues an
 opaque one-use token, and exposes a request-scoped resolver that the
 controller awaits only for protected branches. Authentication here never
 substitutes for the existing authorization/consent evaluation — it only
-supplies fresh, consumable identity evidence and a narrowly scoped consent
-signal for one child-data read.
+supplies fresh, consumable identity evidence and a consent signal bound to one
+named operation (`OwnerUnlockScope`, ADR-0015): a grant issued for one operation
+never authorizes another.
 """

 import asyncio
 from collections.abc import Awaitable, Callable
 from datetime import datetime, timedelta
 from enum import StrEnum
+import logging
 from math import ceil

 from pydantic import BaseModel, ConfigDict
@@ -22,6 +24,7 @@ from server.cognition.identity import (
     ActivePersonContext,
     ActivePersonStatus,
     HouseholdRole,
+    IdentityEvidence,
     IdentityEvidenceSource,
     PersonRecord,
     resolve_active_person,
@@ -43,6 +46,8 @@ __all__ = [
     "OwnerUnlockService",
 ]

+logger = logging.getLogger(__name__)
+
 _MAX_FAILURES = 5
 _FAILURE_WINDOW = timedelta(seconds=60)
 _BLOCK_DURATION = timedelta(seconds=60)
@@ -74,9 +79,16 @@ class OwnerUnlockRateLimitedError(Exception):


 class OwnerUnlockScope(StrEnum):
-    """Closed capability granted by one consumed owner unlock."""
+    """Closed set of operations one owner unlock can be bound to (ADR-0015 decision 1).
+
+    Attributes:
+        PERSONAL_PROTECTED_READ: One protected read of the owner's confirmed child data
+            (the default, so every existing client is unchanged).
+        BIOMETRIC_ADMIN: Enrolling or revoking the owner's face or voice.
+    """

     PERSONAL_PROTECTED_READ = "personal_protected_read"
+    BIOMETRIC_ADMIN = "biometric_admin"


 class OwnerUnlockResult(BaseModel):
@@ -86,6 +98,7 @@ class OwnerUnlockResult(BaseModel):

     token: str
     expires_at: datetime
+    scope: OwnerUnlockScope = OwnerUnlockScope.PERSONAL_PROTECTED_READ


 async def _default_to_thread(fn: Callable[[], bool]) -> bool:
@@ -112,7 +125,7 @@ def _unknown_active_person(event: CognitiveEvent[TextTurnPayload]) -> ActivePers


 class OwnerRequestResolver:
-    """Request-scoped actor/consent resolver bound to one optional token."""
+    """Request-scoped actor/consent resolver bound to one optional token and one operation."""

     def __init__(
         self,
@@ -122,6 +135,7 @@ class OwnerRequestResolver:
         read_role: RoleReader,
         read_person: PersonReader,
         clock: Clock,
+        scope: OwnerUnlockScope = OwnerUnlockScope.PERSONAL_PROTECTED_READ,
     ) -> None:
         """Create a resolver for exactly one HTTP request.

@@ -131,12 +145,15 @@ class OwnerRequestResolver:
             read_role: Boundary that reads a person's active household role.
             read_person: Boundary that reads a person's safe display record.
             clock: Source of the resolution timestamp.
+            scope: The one operation this request authorizes. A token issued for another
+                operation is refused and left unspent.
         """
         self._token = token
         self._registry = registry
         self._read_role = read_role
         self._read_person = read_person
         self._clock = clock
+        self._scope = scope
         self.consumed = False

     @property
@@ -144,7 +161,31 @@ class OwnerRequestResolver:
         """Return the exact granted capability, or empty before consumption."""
         if not self.consumed:
             return frozenset()
-        return frozenset({OwnerUnlockScope.PERSONAL_PROTECTED_READ.value, _CHILD_DATA_CATEGORY})
+        if self._scope is OwnerUnlockScope.PERSONAL_PROTECTED_READ:
+            return frozenset({self._scope.value, _CHILD_DATA_CATEGORY})
+        return frozenset({self._scope.value})
+
+    async def peek_actor(self, event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
+        """Name the owner behind the token without spending the grant.
+
+        Used by branches that only need to know who is asking ("who am I", a household
+        question that reads nothing): a bystander or a harmless question never burns the
+        owner's one-use grant.
+
+        Args:
+            event: The event this observation is scoped to.
+
+        Returns:
+            The identified owner context, or the safe unknown actor when the token is
+            absent, expired, unknown or issued for another operation.
+        """
+        if self._token is None:
+            return _unknown_active_person(event)
+        evidence = self._registry.evidence_for(self._token, scope=self._scope.value)
+        if evidence is None:
+            self._log_scope_mismatch()
+            return _unknown_active_person(event)
+        return await self._context_for(evidence, event)

     async def resolve_actor(self, event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
         """Consume the bound token at most once and resolve the owner actor.
@@ -154,14 +195,25 @@ class OwnerRequestResolver:

         Returns:
             The identified owner context, or the safe unknown actor when the
-            token is absent, already consumed, expired, or invalid.
+            token is absent, already consumed, expired, invalid or issued for
+            another operation (in which case it is not consumed).
         """
         if self._token is None:
             return _unknown_active_person(event)
-        evidence = self._registry.consume_evidence(self._token)
-        if evidence is None or evidence.candidate_person_id is None:
+        evidence = self._registry.consume_evidence(self._token, scope=self._scope.value)
+        if evidence is None:
+            self._log_scope_mismatch()
             return _unknown_active_person(event)
+        context = await self._context_for(evidence, event)
+        self.consumed = context.person_id is not None
+        return context

+    async def _context_for(
+        self, evidence: IdentityEvidence, event: CognitiveEvent[TextTurnPayload]
+    ) -> ActivePersonContext:
+        """Resolve the owner context a piece of grant evidence stands for."""
+        if evidence.candidate_person_id is None:
+            return _unknown_active_person(event)
         person = await self._read_person(evidence.candidate_person_id)
         if person is None:
             return _unknown_active_person(event)
@@ -170,14 +222,17 @@ class OwnerRequestResolver:
         def _lookup_person(person_id: int) -> PersonRecord | None:
             return person if person_id == person.person_id else None

-        context = resolve_active_person(
+        return resolve_active_person(
             evidence=(evidence,),
             lookup_person=_lookup_person,
             lookup_role=lambda _person_id: role,
             clock=self._clock,
         )
-        self.consumed = context.person_id is not None
-        return context
+
+    def _log_scope_mismatch(self) -> None:
+        """Log a closed reason when a live token was refused for another operation."""
+        if self._token is not None and self._registry.evidence_for(self._token) is not None:
+            logger.info("Owner grant refused: scope_mismatch")

     async def resolve_consent(
         self,
@@ -259,11 +314,14 @@ class OwnerUnlockService:
             self._blocked_until = now + _BLOCK_DURATION
             self._failures.clear()

-    async def unlock(self, pin: str) -> OwnerUnlockResult | None:
-        """Verify a candidate PIN and issue one opaque one-use grant.
+    async def unlock(
+        self, pin: str, scope: OwnerUnlockScope = OwnerUnlockScope.PERSONAL_PROTECTED_READ
+    ) -> OwnerUnlockResult | None:
+        """Verify a candidate PIN and issue one opaque one-use grant for one operation.

         Args:
             pin: Candidate PIN from the local unlock request.
+            scope: The one operation the grant may authorize.

         Returns:
             The opaque token and its expiry, or ``None`` for any failure —
@@ -296,18 +354,24 @@ class OwnerUnlockService:
             if person is None:
                 return None
             token = self._registry.issue_for_person(
-                person, source=IdentityEvidenceSource.LOCAL_UNLOCK
+                person, source=IdentityEvidenceSource.LOCAL_UNLOCK, scope=scope.value
             )
             evidence = self._registry.evidence_for(token)
             if evidence is None or evidence.expires_at is None:
                 return None
-            return OwnerUnlockResult(token=token, expires_at=evidence.expires_at)
+            return OwnerUnlockResult(token=token, expires_at=evidence.expires_at, scope=scope)

-    def for_request(self, token: str | None) -> OwnerRequestResolver:
-        """Build a fresh resolver scoped to exactly one HTTP request.
+    def for_request(
+        self,
+        token: str | None,
+        scope: OwnerUnlockScope = OwnerUnlockScope.PERSONAL_PROTECTED_READ,
+    ) -> OwnerRequestResolver:
+        """Build a fresh resolver scoped to exactly one HTTP request and one operation.

         Args:
             token: Optional opaque token carried by the current request.
+            scope: The operation this request authorizes; a token issued for another
+                operation is refused and left unspent.

         Returns:
             A resolver that consumes the token at most once.
@@ -318,6 +382,7 @@ class OwnerUnlockService:
             read_role=self._read_role,
             read_person=self._read_person,
             clock=self._clock,
+            scope=scope,
         )


```

- [ ] **Step 4: Run, lint, commit.**
  `uv run pytest tests/unit/test_owner_authentication.py tests/unit/test_identity_sessions.py -q -p no:cacheprovider`
  (33 pass), then `ruff check` and `ruff format --check` over the two paths.
  Commit — `feat(server): scope owner grants and observe without spending`.

---

## Task 3: The fused resolver can observe without spending

**Files:**
- Modify: `server/src/server/cognition/identity_fusion.py`
- Test: `tests/unit/test_identity_fusion.py`

**Interfaces:**
- Consumes: Task 2's `OwnerRequestResolver.peek_actor`.
- Produces: `FusedIdentityResolver.peek_actor(event)`: the same face-then-voice-then-PIN
  judgement as `resolve_actor`, with the PIN step only naming the token's owner; cached
  per request apart from `resolve_actor`'s cache; a token issued for another scope is
  ignored and untouched.

- [ ] **Step 1: Fix the helper that issues unscoped tokens.** After Task 1 a token with no
  recorded scope is refused when a scope is required, so the file's `_pin` helper must
  issue its token for the read scope (without this, three existing tests fail for the
  wrong reason):

```diff
--- a/tests/unit/test_identity_fusion.py
+++ b/tests/unit/test_identity_fusion.py
@@ -35,7 +35,7 @@ from server.cognition.models import (
     Confidence,
     ConfidenceBasis,
 )
-from server.cognition.owner_authentication import OwnerRequestResolver
+from server.cognition.owner_authentication import OwnerRequestResolver, OwnerUnlockScope
 from server.cognition.response_plan import TextTurnPayload
 from server.cognition.speaker_authentication import SpeakerVerdict
 from server.exceptions import BrainMemoryError
@@ -182,12 +182,16 @@ class _Pin(NamedTuple):
     token: str | None


-def _pin(*, with_token: bool = False) -> _Pin:
+def _pin(
+    *, with_token: bool = False, scope: OwnerUnlockScope = OwnerUnlockScope.PERSONAL_PROTECTED_READ
+) -> _Pin:
     registry = IdentitySessionRegistry(
         lookup_person=lambda _pid: None, clock=lambda: _NOW, ttl=timedelta(seconds=60)
     )
     token = (
-        registry.issue_for_person(_OWNER, source=IdentityEvidenceSource.LOCAL_UNLOCK)
+        registry.issue_for_person(
+            _OWNER, source=IdentityEvidenceSource.LOCAL_UNLOCK, scope=scope.value
+        )
         if with_token
         else None
     )
```

- [ ] **Step 2: Write the failing tests** — append to `tests/unit/test_identity_fusion.py`:

```diff
--- a/tests/unit/test_identity_fusion.py
+++ b/tests/unit/test_identity_fusion.py
@@ -505,3 +509,89 @@ async def test_the_fused_actor_reaches_reserved_data_only_with_strong_assurance(
     assert denied.policy_id == "p0.5.assurance-required"
     for actor in (with_voice, with_pin):
         assert evaluate_authorization(_reserved_read(actor)).decision is AuthorizationStatus.ALLOWED
+
+
+# --- Plan 0051: observing the actor never spends the grant (ADR-0015) ----------
+
+
+async def test_observing_with_a_pin_token_names_the_owner_and_leaves_the_grant_spendable() -> None:
+    pin = _pin(with_token=True)
+    fused = _fused(face=None, pin=pin.resolver)
+
+    actor = await fused.peek_actor(_event())
+
+    assert actor.status is ActivePersonStatus.IDENTIFIED
+    assert actor.person_id == _OWNER_ID
+    assert fused.last_reason is FusionReason.PIN
+    assert fused.source == "local_unlock"
+    assert fused.consumed is False
+    assert _token_is_still_spendable(pin)
+
+
+async def test_a_spending_resolution_after_an_observation_still_consumes_the_grant() -> None:
+    pin = _pin(with_token=True)
+    fused = _fused(face=None, pin=pin.resolver)
+    event = _event()
+
+    await fused.peek_actor(event)
+    actor = await fused.resolve_actor(event)
+
+    assert actor.status is ActivePersonStatus.IDENTIFIED
+    assert fused.consumed is True
+    assert not _token_is_still_spendable(pin)
+
+
+async def test_observing_with_an_identified_face_never_touches_a_presented_token() -> None:
+    pin = _pin(with_token=True)
+    fused = _fused(face=_face_resolver(), pin=pin.resolver)
+
+    actor = await fused.peek_actor(_event())
+
+    assert actor.person_id == _OWNER_ID
+    assert fused.source == "face"
+    assert _token_is_still_spendable(pin)
+
+
+async def test_observing_keeps_every_veto_and_still_does_not_touch_the_token() -> None:
+    pin = _pin(with_token=True)
+    fused = _fused(face=_face_resolver(faces=2), pin=pin.resolver)
+
+    actor = await fused.peek_actor(_event())
+
+    assert actor.status is not ActivePersonStatus.IDENTIFIED
+    assert fused.last_reason is FusionReason.VETO_MULTIPLE_FACES
+    assert _token_is_still_spendable(pin)
+
+
+async def test_observing_is_cached_so_the_face_is_detected_once() -> None:
+    detect_calls: list[int] = []
+    fused = _fused(face=_face_resolver(detect_calls=detect_calls))
+    event = _event()
+
+    first = await fused.peek_actor(event)
+    second = await fused.peek_actor(event)
+
+    assert first is second
+    assert detect_calls == [1]
+
+
+async def test_observing_without_evidence_is_the_unknown_actor() -> None:
+    fused = _fused(face=None)
+
+    actor = await fused.peek_actor(_event())
+
+    assert actor.status is ActivePersonStatus.UNKNOWN
+    assert fused.last_reason is FusionReason.NO_EVIDENCE
+    assert fused.source is None
+
+
+async def test_observing_ignores_a_token_issued_for_another_operation() -> None:
+    pin = _pin(with_token=True, scope=OwnerUnlockScope.BIOMETRIC_ADMIN)
+    fused = _fused(face=None, pin=pin.resolver)
+
+    actor = await fused.peek_actor(_event())
+
+    assert actor.status is ActivePersonStatus.UNKNOWN
+    assert fused.last_reason is FusionReason.NO_EVIDENCE
+    assert pin.token is not None
+    assert pin.registry.evidence_for(pin.token) is not None  # refused, never spent
```

- [ ] **Step 3: Run them to see them fail.**
  `uv run pytest tests/unit/test_identity_fusion.py -q -p no:cacheprovider`.
  Expected: seven failures, `AttributeError: 'FusedIdentityResolver' object has no
  attribute 'peek_actor'`.

- [ ] **Step 4: Implement.**

```diff
--- a/server/src/server/cognition/identity_fusion.py
+++ b/server/src/server/cognition/identity_fusion.py
@@ -97,6 +97,7 @@ class FusedIdentityResolver:
         self._speaker_factory = speaker_factory
         self._clock = clock
         self._cached: ActivePersonContext | None = None
+        self._peeked: ActivePersonContext | None = None
         self.last_reason: FusionReason | None = None
         self.source: IdentitySource | None = None

@@ -117,14 +118,38 @@ class FusedIdentityResolver:
         """
         if self._cached is not None:
             return self._cached
-        context = await self._resolve(event)
+        context = await self._resolve(event, consume=True)
         self._cached = context
+        self._log_outcome()
+        return context
+
+    async def peek_actor(self, event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
+        """Resolve the actor the same way, but never spend the PIN grant (ADR-0015).
+
+        For the branches that read nothing ("who am I", a household question that is not
+        connected yet): the face and the voice are judged as usual, a presented token only
+        names its owner, and it stays spendable by the branch that reads data.
+
+        Args:
+            event: The event this observation is scoped to.
+
+        Returns:
+            The same context `resolve_actor` would return, with the token unspent.
+        """
+        if self._peeked is not None:
+            return self._peeked
+        context = await self._resolve(event, consume=False)
+        self._peeked = context
+        self._log_outcome()
+        return context
+
+    def _log_outcome(self) -> None:
+        """Log the closed reason of this request's identity outcome, never any content."""
         logger.info(
             "Identity fusion: %s",
             self.last_reason.value if self.last_reason else "none",
             extra={"event": "identity.fusion", "reason": self.last_reason},
         )
-        return context

     async def resolve_consent(
         self, event: CognitiveEvent[TextTurnPayload], actor: ActivePersonContext
@@ -144,13 +169,26 @@ class FusedIdentityResolver:
             return await self._pin.resolve_consent(event, actor)
         return ConsentStatus.NOT_REQUIRED

-    async def _resolve(self, event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
-        """Run face, then voice, then PIN, stopping at the first identification or veto."""
+    async def _resolve(
+        self, event: CognitiveEvent[TextTurnPayload], *, consume: bool
+    ) -> ActivePersonContext:
+        """Run face, then voice, then PIN, stopping at the first identification or veto.
+
+        Args:
+            event: The event this resolution is scoped to.
+            consume: Whether the PIN step spends the token (a read) or only names its
+                owner (an observation).
+        """
         face_outcome = await self._resolve_face(event)
         if face_outcome is not None:
             return face_outcome
-        pin_context = await self._pin.resolve_actor(event)
-        if self._pin.consumed:
+        if consume:
+            pin_context = await self._pin.resolve_actor(event)
+            by_pin = self._pin.consumed
+        else:
+            pin_context = await self._pin.peek_actor(event)
+            by_pin = pin_context.status is ActivePersonStatus.IDENTIFIED
+        if by_pin:
             self.last_reason = FusionReason.PIN
             self.source = "local_unlock"
         else:
```

- [ ] **Step 5: Run, lint, commit.**
  `uv run pytest tests/unit/test_identity_fusion.py -q -p no:cacheprovider` (35 pass),
  then `ruff check` and `ruff format --check`. Commit —
  `feat(server): let fusion observe the actor without a grant`.

---

## Task 4: HTTP surface and administration scripts

**Files:**
- Modify: `server/src/server/schemas_auth.py`, `server/src/server/routers/auth.py`,
  `scripts/onboard.py`, `scripts/face_auth_demo.py`, `scripts/speaker_auth_demo.py`
- Create: `tests/unit/test_biometric_admin_scope_callers.py`
- Test: `tests/integration/test_owner_unlock_endpoint.py`,
  `test_owner_face_enrollment.py`, `test_owner_voice_enrollment.py`

**Interfaces:**
- Consumes: Task 2's `OwnerUnlockService.unlock(pin, scope)` and
  `for_request(token, scope=)`.
- Produces: `OwnerUnlockRequest.scope` (default `personal_protected_read`),
  `OwnerUnlockResponse.scope`; the four biometric routes build their resolver for
  `biometric_admin`; the three administration scripts unlock for it.

- [ ] **Step 1: Write the failing tests.** The endpoint tests (the fake service takes a
  scope, the response and schema tests expect the additive field, and new tests cover the
  default, the explicit admin scope and an unknown scope):

```diff
--- a/tests/integration/test_owner_unlock_endpoint.py
+++ b/tests/integration/test_owner_unlock_endpoint.py
@@ -10,6 +10,7 @@ import pytest
 from server.cognition.owner_authentication import (
     OwnerUnlockRateLimitedError,
     OwnerUnlockResult,
+    OwnerUnlockScope,
 )
 from server.dependencies import get_owner_unlock_service
 from server.main import app
@@ -24,9 +25,13 @@ class _FakeService:
         self._result = result
         self._raises = raises
         self.received_pin: str | None = None
+        self.received_scope: OwnerUnlockScope | None = None

-    async def unlock(self, pin: str) -> OwnerUnlockResult | None:
+    async def unlock(
+        self, pin: str, scope: OwnerUnlockScope = OwnerUnlockScope.PERSONAL_PROTECTED_READ
+    ) -> OwnerUnlockResult | None:
         self.received_pin = pin
+        self.received_scope = scope
         if self._raises is not None:
             raise self._raises
         return self._result
@@ -56,7 +61,7 @@ async def _remote_client() -> AsyncIterator[AsyncClient]:


 @pytest.mark.integration
-async def test_loopback_with_valid_pin_returns_only_token_and_expiry(
+async def test_loopback_with_valid_pin_returns_only_token_expiry_and_scope(
     monkeypatch: pytest.MonkeyPatch,
 ) -> None:
     """A loopback caller with a correct PIN receives exactly token and expiry."""
@@ -67,7 +72,7 @@ async def test_loopback_with_valid_pin_returns_only_token_and_expiry(
         response = await client.post("/auth/owner/unlock", json={"pin": "482173"})

     assert response.status_code == 200
-    assert set(response.json()) == {"token", "expires_at"}
+    assert set(response.json()) == {"token", "expires_at", "scope"}
     assert response.json()["token"] == "opaque-token"  # noqa: S105 — fixture value
     assert fake.received_pin == "482173"

@@ -140,8 +145,11 @@ async def test_openapi_exposes_no_person_role_or_session_fields() -> None:
     schemas = response.json()["components"]["schemas"]
     unlock_request = schemas["OwnerUnlockRequest"]
     unlock_response = schemas["OwnerUnlockResponse"]
-    assert set(unlock_request["properties"]) == {"pin"}
-    assert set(unlock_response["properties"]) == {"token", "expires_at"}
+    assert set(unlock_request["properties"]) == {"pin", "scope"}
+    assert set(unlock_response["properties"]) == {"token", "expires_at", "scope"}
+    scope_schema = schemas["OwnerUnlockScope"]
+    assert scope_schema["enum"] == ["personal_protected_read", "biometric_admin"]
+    assert "scope" not in unlock_request.get("required", [])  # additive: clients unchanged


 @pytest.mark.integration
@@ -295,3 +303,52 @@ async def test_an_unparseable_client_address_is_forbidden(
         response = await client.post("/auth/owner/unlock", json={"pin": "482173"})

     assert response.status_code == 403
+
+
+@pytest.mark.integration
+async def test_an_unlock_without_a_scope_is_a_read_grant_and_says_so(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    """Absent `scope` keeps every existing client unchanged (ADR-0015 decision 1)."""
+    fake = _FakeService(result=_result())
+    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: fake)
+
+    async with _loopback_client() as client:
+        response = await client.post("/auth/owner/unlock", json={"pin": "482173"})
+
+    assert fake.received_scope is OwnerUnlockScope.PERSONAL_PROTECTED_READ
+    assert response.json()["scope"] == "personal_protected_read"
+
+
+@pytest.mark.integration
+async def test_an_unlock_can_ask_for_biometric_admin_and_the_response_echoes_it(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    result = _result().model_copy(update={"scope": OwnerUnlockScope.BIOMETRIC_ADMIN})
+    fake = _FakeService(result=result)
+    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: fake)
+
+    async with _loopback_client() as client:
+        response = await client.post(
+            "/auth/owner/unlock", json={"pin": "482173", "scope": "biometric_admin"}
+        )
+
+    assert response.status_code == 200
+    assert fake.received_scope is OwnerUnlockScope.BIOMETRIC_ADMIN
+    assert response.json()["scope"] == "biometric_admin"
+
+
+@pytest.mark.integration
+@pytest.mark.parametrize("scope", ["root", "personal_protected_write", "", None, 3])
+async def test_an_unknown_scope_is_rejected_without_echoing_the_pin(
+    scope: object, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    fake = _FakeService(result=_result())
+    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: fake)
+
+    async with _loopback_client() as client:
+        response = await client.post("/auth/owner/unlock", json={"pin": "482173", "scope": scope})
+
+    assert response.status_code == 422
+    assert "482173" not in response.text
+    assert fake.received_pin is None
```

  The face and voice enrolment tests: every `service.unlock(_PIN)` becomes
  `service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)` (so the expiry, replay and
  failure tests deny for the reason they name, see Review Focus 6), and each file gains
  two read-grant refusal tests:

```diff
--- a/tests/integration/test_owner_face_enrollment.py
+++ b/tests/integration/test_owner_face_enrollment.py
@@ -21,7 +21,11 @@ from pydantic import SecretStr
 import pytest
 from server.cognition.identity import PersonRecord
 from server.cognition.identity_sessions import IdentitySessionRegistry
-from server.cognition.owner_authentication import OwnerUnlockService, owner_unlock_service
+from server.cognition.owner_authentication import (
+    OwnerUnlockScope,
+    OwnerUnlockService,
+    owner_unlock_service,
+)
 from server.dependencies import get_owner_unlock_service
 from server.exceptions import EnrollmentRejectedError
 from server.main import app
@@ -174,7 +178,7 @@ async def test_expired_token_denies_without_touching_face_model(

     service = _real_service(clock=clock)
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None
     now = now + timedelta(seconds=61)

@@ -199,7 +203,7 @@ async def test_consumed_token_denies_second_use_without_touching_face_model(
     """Reusing an already-consumed token must deny without a second enrollment."""
     service = _real_service()
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None
     monkeypatch.setattr(
         vision,
@@ -271,7 +275,7 @@ async def test_multiple_faces_rejection_maps_to_422_without_persisting_consent(
     """A multi-face frame is rejected with its code and grants no consent."""
     service = _real_service()
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None
     monkeypatch.setattr(
         vision,
@@ -304,7 +308,7 @@ async def test_other_rejection_codes_map_to_422_without_persisting_consent(
     """Every other rejection code also maps to 422 and grants no consent."""
     service = _real_service()
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None
     monkeypatch.setattr(
         vision,
@@ -333,7 +337,7 @@ async def test_oversized_enrollment_image_returns_413_without_touching_the_face_
     """An authenticated caller still cannot bypass the per-file byte budget."""
     service = _real_service()
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None
     enroll = AsyncMock(wraps=vision.enroll_person)
     monkeypatch.setattr(vision, "enroll_person", enroll)
@@ -357,7 +361,7 @@ async def test_successful_enroll_grants_consent_and_creates_one_profile(
     """A successful enrollment returns 200, grants consent, and persists one profile."""
     service = _real_service()
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None
     monkeypatch.setattr(vision, "enroll_person", _fake_enroll_person)
     grant = AsyncMock(wraps=auth_module.grant_face_consent)
@@ -394,7 +398,7 @@ async def test_second_enrollment_for_same_owner_persists_profile_and_reuses_cons
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
     monkeypatch.setattr(vision, "enroll_person", _fake_enroll_person)

-    first_unlock = await service.unlock(_PIN)
+    first_unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert first_unlock is not None
     async with _loopback_client() as client:
         first = await client.post(
@@ -403,7 +407,7 @@ async def test_second_enrollment_for_same_owner_persists_profile_and_reuses_cons
             files=_enroll_files(),
         )

-    second_unlock = await service.unlock(_PIN)
+    second_unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert second_unlock is not None
     async with _loopback_client() as client:
         second = await client.post(
@@ -442,7 +446,7 @@ async def test_extra_name_field_is_ignored_and_owner_name_is_used(
     """An injected `name` form field never overrides the token owner's name."""
     service = _real_service()
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None
     enroll = AsyncMock(side_effect=_fake_enroll_person)
     monkeypatch.setattr(vision, "enroll_person", enroll)
@@ -472,7 +476,7 @@ async def test_revoke_with_valid_token_purges_consent_and_returns_204(
     """A valid token revokes exactly the token owner's consent."""
     service = _real_service()
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None
     revoke = AsyncMock(wraps=auth_module.revoke_face_consent)
     monkeypatch.setattr(auth_module, "revoke_face_consent", revoke)
@@ -520,3 +524,50 @@ async def test_revoke_with_invalid_token_denies_without_purging(

     assert response.status_code == 401
     revoke.assert_not_awaited()
+
+
+@pytest.mark.integration
+async def test_a_read_grant_denies_face_enrollment_without_touching_the_model(
+    face_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    """A grant issued for a protected read is not a biometric-administration grant."""
+    service = _real_service()
+    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
+    unlock = await service.unlock(_PIN)  # the default scope: personal_protected_read
+    assert unlock is not None
+    enroll = AsyncMock()
+    monkeypatch.setattr(vision, "enroll_person", enroll)
+    grant = AsyncMock()
+    monkeypatch.setattr(auth_module, "grant_face_consent", grant)
+
+    async with _loopback_client() as client:
+        response = await client.post(
+            "/auth/owner/face/enroll",
+            headers={"X-Iroko-Identity-Token": unlock.token},
+            files=_enroll_files(),
+        )
+
+    assert response.status_code == 401
+    assert response.json() == {"detail": "Owner authentication failed"}
+    enroll.assert_not_awaited()
+    grant.assert_not_awaited()
+
+
+@pytest.mark.integration
+async def test_a_read_grant_denies_face_revocation_and_revokes_nothing(
+    face_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    service = _real_service()
+    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
+    unlock = await service.unlock(_PIN)
+    assert unlock is not None
+    revoke = AsyncMock()
+    monkeypatch.setattr(auth_module, "revoke_face_consent", revoke)
+
+    async with _loopback_client() as client:
+        response = await client.post(
+            "/auth/owner/face/revoke", headers={"X-Iroko-Identity-Token": unlock.token}
+        )
+
+    assert response.status_code == 401
+    revoke.assert_not_awaited()
```

```diff
--- a/tests/integration/test_owner_voice_enrollment.py
+++ b/tests/integration/test_owner_voice_enrollment.py
@@ -24,7 +24,11 @@ from pydantic import SecretStr
 import pytest
 from server.cognition.identity import PersonRecord
 from server.cognition.identity_sessions import IdentitySessionRegistry
-from server.cognition.owner_authentication import OwnerUnlockService, owner_unlock_service
+from server.cognition.owner_authentication import (
+    OwnerUnlockScope,
+    OwnerUnlockService,
+    owner_unlock_service,
+)
 from server.dependencies import get_owner_unlock_service
 from server.main import app
 from server.memory.entity_labels import get_person_label
@@ -195,7 +199,7 @@ async def test_expired_token_denies_without_touching_the_speaker_model(

     service = _real_service(clock=clock)
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None
     now = now + timedelta(seconds=61)

@@ -220,7 +224,7 @@ async def test_consumed_token_denies_second_use_without_touching_the_speaker_mod
     """Reusing an already-consumed token must deny without a second enrollment."""
     service = _real_service()
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None
     monkeypatch.setattr(auth_module, "embed_wav", _fake_embed_wav)

@@ -288,7 +292,7 @@ async def test_oversized_enrollment_upload_returns_413_without_touching_the_spea
     """An authenticated caller still cannot bypass the per-file byte budget."""
     service = _real_service()
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None
     embed = AsyncMock(wraps=_fake_embed_wav)
     monkeypatch.setattr(auth_module, "embed_wav", embed)
@@ -312,7 +316,7 @@ async def test_empty_body_returns_422_without_touching_the_speaker_model(
     """An empty upload is rejected before any embedding is attempted."""
     service = _real_service()
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None
     embed = AsyncMock()
     monkeypatch.setattr(auth_module, "embed_wav", embed)
@@ -335,7 +339,7 @@ async def test_off_contract_audio_returns_422_without_touching_the_speaker_model
     """A 44.1kHz stereo clip fails the audio contract before it is embedded."""
     service = _real_service()
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None
     embed = AsyncMock()
     monkeypatch.setattr(auth_module, "embed_wav", embed)
@@ -359,7 +363,7 @@ async def test_a_one_second_clip_returns_422_without_touching_the_speaker_model(
     """Shorter than `speaker_min_enrollment_s` (2.0s) is rejected outright."""
     service = _real_service()
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None
     embed = AsyncMock()
     monkeypatch.setattr(auth_module, "embed_wav", embed)
@@ -382,7 +386,7 @@ async def test_a_near_silent_clip_returns_422_without_touching_the_speaker_model
     """Review Focus 1 — a format-perfect but near-silent clip never enrolls."""
     service = _real_service()
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None
     embed = AsyncMock()
     monkeypatch.setattr(auth_module, "embed_wav", embed)
@@ -406,7 +410,7 @@ async def test_successful_enroll_grants_consent_and_creates_one_profile(
     """A successful enrollment returns 200, grants consent, and persists one profile."""
     service = _real_service()
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None
     monkeypatch.setattr(auth_module, "embed_wav", _fake_embed_wav)
     grant = AsyncMock(wraps=auth_module.grant_voice_consent)
@@ -454,7 +458,7 @@ async def test_second_enrollment_for_same_owner_persists_profile_and_reuses_cons
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
     monkeypatch.setattr(auth_module, "embed_wav", _fake_embed_wav)

-    first_unlock = await service.unlock(_PIN)
+    first_unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert first_unlock is not None
     async with _loopback_client() as client:
         first = await client.post(
@@ -463,7 +467,7 @@ async def test_second_enrollment_for_same_owner_persists_profile_and_reuses_cons
             files=_enroll_files(),
         )

-    second_unlock = await service.unlock(_PIN)
+    second_unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert second_unlock is not None
     async with _loopback_client() as client:
         second = await client.post(
@@ -510,7 +514,7 @@ async def test_every_enroll_attempt_writes_one_audit_event(
     before = (await cursor.fetchone())[0]  # type: ignore[index]
     await cursor.close()

-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None
     async with _loopback_client() as client:
         allowed = await client.post(
@@ -548,7 +552,7 @@ async def test_no_response_body_or_log_contains_the_owner_name(
     """
     service = _real_service()
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None
     monkeypatch.setattr(auth_module, "embed_wav", _fake_embed_wav)

@@ -572,7 +576,7 @@ async def test_revoke_with_valid_token_purges_consent_and_returns_204(
     """A valid token revokes exactly the token owner's consent."""
     service = _real_service()
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None
     revoke = AsyncMock(wraps=auth_module.revoke_voice_consent)
     monkeypatch.setattr(auth_module, "revoke_voice_consent", revoke)
@@ -631,7 +635,7 @@ async def test_flag_off_enroll_returns_503_without_a_token_or_a_write(
     monkeypatch.setattr(settings, "speaker_authentication_enabled", False)
     service = _real_service()
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None
     embed = AsyncMock()
     monkeypatch.setattr(auth_module, "embed_wav", embed)
@@ -665,7 +669,7 @@ async def test_flag_off_revoke_still_works_and_purges(
     service = _real_service()
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
     monkeypatch.setattr(auth_module, "embed_wav", _fake_embed_wav)
-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None
     async with _loopback_client() as client:
         enroll_response = await client.post(
@@ -676,7 +680,7 @@ async def test_flag_off_revoke_still_works_and_purges(
     assert enroll_response.status_code == 200

     monkeypatch.setattr(settings, "speaker_authentication_enabled", False)
-    revoke_unlock = await service.unlock(_PIN)
+    revoke_unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert revoke_unlock is not None
     async with _loopback_client() as client:
         response = await client.post(
@@ -721,7 +725,7 @@ async def test_a_rejected_clip_does_not_burn_the_one_use_token(
     service = _real_service()
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
     monkeypatch.setattr(auth_module, "embed_wav", _fake_embed_wav)
-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None

     async with _loopback_client() as client:
@@ -749,7 +753,7 @@ async def test_a_dead_speaker_backend_returns_503_and_enrolls_nothing(
     monkeypatch.setattr(
         auth_module, "embed_wav", AsyncMock(side_effect=SpeakerBackendError("model unavailable"))
     )
-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None

     async with _loopback_client() as client:
@@ -775,7 +779,7 @@ async def test_the_stored_label_is_not_the_owner_name(
     service = _real_service()
     monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
     monkeypatch.setattr(auth_module, "embed_wav", _fake_embed_wav)
-    unlock = await service.unlock(_PIN)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
     assert unlock is not None

     async with _loopback_client() as client:
@@ -791,3 +795,47 @@ async def test_the_stored_label_is_not_the_owner_name(
     await cursor.close()
     assert row is not None
     assert _OWNER_NAME.casefold() not in str(row[0]).casefold()
+
+
+@pytest.mark.integration
+async def test_a_read_grant_denies_voice_enrollment_without_touching_the_speaker_model(
+    voice_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    """A grant issued for a protected read is not a biometric-administration grant."""
+    service = _real_service()
+    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
+    unlock = await service.unlock(_PIN)  # the default scope: personal_protected_read
+    assert unlock is not None
+    embed = AsyncMock()
+    monkeypatch.setattr(auth_module, "embed_wav", embed)
+
+    async with _loopback_client() as client:
+        response = await client.post(
+            "/auth/owner/voice/enroll",
+            headers={"X-Iroko-Identity-Token": unlock.token},
+            files=_enroll_files(),
+        )
+
+    assert response.status_code == 401
+    assert response.json() == {"detail": "Owner authentication failed"}
+    embed.assert_not_awaited()
+
+
+@pytest.mark.integration
+async def test_a_read_grant_denies_voice_revocation_and_revokes_nothing(
+    voice_db: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    service = _real_service()
+    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
+    unlock = await service.unlock(_PIN)
+    assert unlock is not None
+    revoke = AsyncMock()
+    monkeypatch.setattr(auth_module, "revoke_voice_consent", revoke)
+
+    async with _loopback_client() as client:
+        response = await client.post(
+            "/auth/owner/voice/revoke", headers={"X-Iroko-Identity-Token": unlock.token}
+        )
+
+    assert response.status_code == 401
+    revoke.assert_not_awaited()
```

  And the guard that pins the callers of the administration routes:

```python
"""Every caller of biometric administration unlocks for that operation (Plan 0051)."""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_ADMIN_ROUTES = ("/auth/owner/face/", "/auth/owner/voice/")
_ADMIN_CALLERS = {"face_auth_demo.py", "onboard.py", "speaker_auth_demo.py"}
_SCOPE_FIELD = '"scope": "biometric_admin"'


def _scripts_calling_the_admin_routes() -> dict[str, str]:
    sources = {
        path.name: path.read_text(encoding="utf-8") for path in (_ROOT / "scripts").glob("*.py")
    }
    return {
        name: text
        for name, text in sources.items()
        if any(route in text for route in _ADMIN_ROUTES)
    }


@pytest.mark.unit
def test_the_scripts_that_administer_biometrics_are_exactly_the_known_ones() -> None:
    assert set(_scripts_calling_the_admin_routes()) == _ADMIN_CALLERS


@pytest.mark.unit
@pytest.mark.parametrize("name", sorted(_ADMIN_CALLERS))
def test_a_biometric_admin_script_unlocks_with_the_admin_scope(name: str) -> None:
    """A read grant is refused by the admin routes, so these scripts must ask for the other."""
    assert _SCOPE_FIELD in _scripts_calling_the_admin_routes()[name]


@pytest.mark.unit
def test_the_robot_never_asks_for_the_administration_scope() -> None:
    """The robot keeps only read grants: it is a generic client of the audio API."""
    sources = (_ROOT / "robot" / "src" / "robot").rglob("*.py")

    assert not [path.name for path in sources if "biometric_admin" in path.read_text("utf-8")]
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/integration/test_owner_unlock_endpoint.py tests/integration/test_owner_face_enrollment.py tests/integration/test_owner_voice_enrollment.py tests/unit/test_biometric_admin_scope_callers.py -q -p no:cacheprovider`.
  Expected: the unlock tests fail on the missing `scope` field and the `received_scope`
  assertions; the enrolment tests that expect success fail with 401 (an administration
  grant is refused by a route that still builds its resolver for the read scope); the four
  new read-grant tests fail (the route still accepts a read grant); the guard fails three
  times (the scripts lack `"scope": "biometric_admin"`).

- [ ] **Step 3: Implement the schemas and the routes.**

```diff
--- a/server/src/server/schemas_auth.py
+++ b/server/src/server/schemas_auth.py
@@ -5,6 +5,7 @@ from typing import Annotated

 from pydantic import AfterValidator, BaseModel, ConfigDict, Field, SecretStr

+from server.cognition.owner_authentication import OwnerUnlockScope
 from server.cognition.pin_credentials import validate_pin

 __all__ = [
@@ -45,6 +46,15 @@ class OwnerUnlockRequest(BaseModel):
         AfterValidator(_require_pin_shape),
         Field(description="Local owner PIN — 6 to 12 ASCII digits."),
     ]
+    scope: Annotated[
+        OwnerUnlockScope,
+        Field(
+            description=(
+                "The one operation the grant may authorize: `personal_protected_read` "
+                "(the default) or `biometric_admin` (face or voice enrolment and revocation)."
+            )
+        ),
+    ] = OwnerUnlockScope.PERSONAL_PROTECTED_READ


 class OwnerUnlockResponse(BaseModel):
@@ -54,6 +64,7 @@ class OwnerUnlockResponse(BaseModel):

     token: str
     expires_at: datetime
+    scope: OwnerUnlockScope = Field(description="The operation this grant is bound to.")


 class FaceEnrollResponse(BaseModel):
```

```diff
--- a/server/src/server/routers/auth.py
+++ b/server/src/server/routers/auth.py
@@ -4,9 +4,10 @@ Never trusts `X-Forwarded-For` or any other proxy header — the server does
 not enable `proxy_headers`, and every route additionally checks the raw ASGI
 connection origin before touching any downstream service.

-Face enrollment/revocation are the ONLY way to register or purge biometric
-authentication evidence: both require a fresh PIN-consumed token from
-`POST /auth/owner/unlock`, enroll or revoke exclusively the token's own
+Face and voice enrollment/revocation are the ONLY way to register or purge
+biometric authentication evidence: all require a fresh PIN-consumed token from
+`POST /auth/owner/unlock` issued for `biometric_admin` (a read grant is refused
+and stays unspent, ADR-0015), enroll or revoke exclusively the token's own
 owner, and route through the same deterministic authorization pipeline
 (`evaluate_authorization`) every other protected action uses. This is
 separate from — and never modifies — the quarantined public
@@ -48,6 +49,7 @@ from server.cognition.models import (
 )
 from server.cognition.owner_authentication import (
     OwnerUnlockRateLimitedError,
+    OwnerUnlockScope,
     OwnerUnlockService,
 )
 from server.cognition.response_plan import TextTurnPayload
@@ -129,15 +131,16 @@ async def unlock_owner(
     response: Response,
     owner_unlock_service: OwnerUnlockServiceDep,
 ) -> OwnerUnlockResponse:
-    """Verify the local owner PIN and issue one opaque one-use grant.
+    """Verify the local owner PIN and issue one opaque one-use grant for one operation.

     Args:
-        request: The candidate PIN — never logged or echoed.
+        request: The candidate PIN — never logged or echoed — and the optional scope the
+            grant is bound to (`personal_protected_read` when absent).
         http_request: Raw ASGI request used only to check loopback origin.
         owner_unlock_service: Lifespan-owned unlock service (Plan 0040).

     Returns:
-        The opaque token and its expiry on a successful local unlock.
+        The opaque token, its expiry and the scope it is bound to.

     Raises:
         HTTPException: 403 for a non-loopback caller, 401 for a wrong PIN or
@@ -147,7 +150,7 @@ async def unlock_owner(
     if not _is_loopback(http_request):
         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Local access only")
     try:
-        result = await owner_unlock_service.unlock(request.pin.get_secret_value())
+        result = await owner_unlock_service.unlock(request.pin.get_secret_value(), request.scope)
     except OwnerUnlockRateLimitedError as exc:
         raise HTTPException(
             status_code=status.HTTP_429_TOO_MANY_REQUESTS,
@@ -158,7 +161,7 @@ async def unlock_owner(
         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_UNAUTHORIZED_DETAIL)
     # The body carries a usable grant; no cache may retain it.
     response.headers["Cache-Control"] = "no-store"
-    return OwnerUnlockResponse(token=result.token, expires_at=result.expires_at)
+    return OwnerUnlockResponse(token=result.token, expires_at=result.expires_at, scope=result.scope)


 def _face_event(event_type: str) -> CognitiveEvent[TextTurnPayload]:
@@ -194,7 +197,8 @@ async def _authorize_biometric_action(
 ) -> tuple[ActivePersonContext, AuthorizationRequest, AuthorizationDecision]:
     """Resolve the request-scoped actor and evaluate the biometric-admin policy.

-    Consumes the bound one-use token at most once via a fresh resolver, then
+    Consumes the bound one-use token at most once via a fresh resolver bound to
+    `biometric_admin` (a token issued for a read is refused and not spent), then
     evaluates `ENROLL_BIOMETRIC` through the same deterministic
     `evaluate_authorization` pipeline every other protected action uses —
     covering both the owner-role check and the explicit consent check for a
@@ -211,7 +215,7 @@ async def _authorize_biometric_action(
         decision. The decision is `ALLOWED` only for a fresh, consumed
         owner grant.
     """
-    resolver = owner_unlock_service.for_request(token)
+    resolver = owner_unlock_service.for_request(token, scope=OwnerUnlockScope.BIOMETRIC_ADMIN)
     event = _face_event(event_type)
     actor = await resolver.resolve_actor(event)
     consent = await resolver.resolve_consent(event, actor)
@@ -418,8 +422,7 @@ async def enroll_owner_voice(
     stricter on purpose: less voice data collected while the feature is off).

     ADR-0015 decision 1: this is `biometric_admin`, not
-    `personal_protected_read`. Plan 0051 binds the grant's scope; until then
-    it consumes the same unscoped one-use token the face routes consume.
+    `personal_protected_read`: the token must have been issued with that scope.

     Args:
         http_request: Raw ASGI request used only to check loopback origin.
@@ -498,8 +501,7 @@ async def revoke_owner_voice(
     """Revoke the token's own owner's voice consent and purge stored voiceprints.

     ADR-0015 decision 1: this is `biometric_admin`, not
-    `personal_protected_read`. Plan 0051 binds the grant's scope; until then
-    it consumes the same unscoped one-use token the face routes consume.
+    `personal_protected_read`: the token must have been issued with that scope.

     Carries no `speaker_authentication_enabled` check — unlike enrolment,
     revocation must keep working even with the feature nominally off, so an
```

- [ ] **Step 4: Make the three administration scripts ask for the scope.**

```diff
--- a/scripts/onboard.py
+++ b/scripts/onboard.py
@@ -69,7 +69,9 @@ async def _run_face_phase(url: str, device: int) -> None:
     print("== Paso 2/2: enrolar tu cara ==")  # noqa: T201
     pin = await asyncio.to_thread(getpass.getpass, "Owner PIN: ")
     async with httpx.AsyncClient(timeout=30) as client:
-        unlock_resp = await client.post(f"{url}/auth/owner/unlock", json={"pin": pin})
+        unlock_resp = await client.post(
+            f"{url}/auth/owner/unlock", json={"pin": pin, "scope": "biometric_admin"}
+        )
         if unlock_resp.is_error:
             print(f"PIN rechazado: {unlock_resp.status_code}")  # noqa: T201
             raise SystemExit(1)
```

```diff
--- a/scripts/face_auth_demo.py
+++ b/scripts/face_auth_demo.py
@@ -90,7 +90,9 @@ async def _unlock(client: httpx.AsyncClient, url: str) -> str:
         SystemExit: If the PIN is rejected or the server is unreachable.
     """
     pin = await _read_pin()
-    resp = await client.post(f"{url}/auth/owner/unlock", json={"pin": pin})
+    resp = await client.post(
+        f"{url}/auth/owner/unlock", json={"pin": pin, "scope": "biometric_admin"}
+    )
     if resp.is_error:
         logger.error("Unlock rejected: %s %s", resp.status_code, resp.text[:200])
         raise SystemExit(1)
```

```diff
--- a/scripts/speaker_auth_demo.py
+++ b/scripts/speaker_auth_demo.py
@@ -93,7 +93,9 @@ async def _unlock(client: httpx.AsyncClient, url: str) -> str:
         SystemExit: If the PIN is rejected or the server is unreachable.
     """
     pin = await _read_pin()
-    resp = await client.post(f"{url}/auth/owner/unlock", json={"pin": pin})
+    resp = await client.post(
+        f"{url}/auth/owner/unlock", json={"pin": pin, "scope": "biometric_admin"}
+    )
     if resp.is_error:
         logger.error("Unlock rejected: %s %s", resp.status_code, resp.text[:200])
         raise SystemExit(1)
```

- [ ] **Step 5: Run them, then prove the refusal tests bite.**
  The four files above must pass. Then, **temporarily**, change
  `for_request(token, scope=OwnerUnlockScope.BIOMETRIC_ADMIN)` in
  `_authorize_biometric_action` back to `for_request(token)` and run
  `uv run pytest tests/integration/test_owner_face_enrollment.py tests/integration/test_owner_voice_enrollment.py -q -p no:cacheprovider -k read_grant`:
  the four refusal tests must fail. Restore the line.

- [ ] **Step 6: Lint and commit.** `ruff check` and `ruff format --check` over the
  **explicit paths** of every file above (the scripts included), then
  `uv run pytest tests/integration/test_openapi_contract.py tests/integration/test_api_contract.py -q -p no:cacheprovider`
  (the schema is additive). Commit —
  `feat(server): require biometric_admin for face and voice admin`.

---

## Task 5: Branches that read nothing observe the actor

**Files:**
- Modify: `server/src/server/cognition/controller.py`, `server/src/server/routers/chat.py`,
  `server/src/server/routers/transcribe.py`
- Test: `tests/unit/test_cognitive_controller.py`,
  `tests/integration/test_owner_stranger_matrix.py`,
  `test_owner_authenticated_turn.py`, `test_owner_authenticated_stream.py`

**Interfaces:**
- Consumes: Task 2's `OwnerRequestResolver.peek_actor`, Task 3's
  `FusedIdentityResolver.peek_actor`.
- Produces: `CognitiveController(..., observed_person_resolver=<defaults to the public
  unknown actor>)`: `_active_identity_plan` and `_protected_household_plan` (when the
  caller did not already resolve the actor) use it; only the children read awaits
  `active_person_resolver`. The chat and voice routes hand the controller their observing
  resolver, keeping the actor log line.

This task changes behaviour in production: the controller seam and the two routes land
in one commit so that "¿Quién soy?" is never left without an observer.

- [ ] **Step 1: Write the failing tests.** The controller unit tests (the existing
  "greets the authenticated owner" test moves to the observing seam; four new ones pin
  that who-am-i and the not-connected answer never await the spending resolver, that a
  stranger is denied, and that the children read is the only branch that spends):

```diff
--- a/tests/unit/test_cognitive_controller.py
+++ b/tests/unit/test_cognitive_controller.py
@@ -558,13 +558,13 @@ async def test_controller_biometric_enrollment_returns_fixed_denial_without_came

 @pytest.mark.asyncio
 async def test_controller_active_identity_greets_the_authenticated_owner() -> None:
-    """ACTIVE_IDENTITY consumes the same request-scoped grant as a household read."""
+    """ACTIVE_IDENTITY names the observed owner and never spends a grant (ADR-0015)."""
     legacy_turn = AsyncMock()
     owner = _actor(HouseholdRole.OWNER, person_id=1)
     controller = CognitiveController(
         today=lambda: date(2026, 8, 12),
         legacy_turn=legacy_turn,
-        active_person_resolver=_resolver(owner),
+        observed_person_resolver=_resolver(owner),
     )

     plan = await controller.handle(_event("¿Quién soy?"))
@@ -587,3 +587,97 @@ async def test_controller_active_identity_denies_without_fresh_evidence() -> Non
     assert plan.status is KnowledgeStatus.UNKNOWN
     assert plan.response == "Todavía no puedo confirmar quién sos."
     legacy_turn.assert_not_awaited()
+
+
+@pytest.mark.asyncio
+async def test_who_am_i_never_awaits_the_resolver_that_spends_the_grant() -> None:
+    """The answer comes from the observed actor; the consuming resolver stays untouched."""
+    owner = _actor(HouseholdRole.OWNER, person_id=1)
+    spending = AsyncMock(return_value=owner)
+    controller = CognitiveController(
+        today=lambda: date(2026, 8, 12),
+        legacy_turn=AsyncMock(),
+        active_person_resolver=spending,
+        observed_person_resolver=_resolver(owner),
+    )
+
+    plan = await controller.handle(_event("¿Quién soy?"))
+
+    assert plan.response == "Sos Ada."
+    spending.assert_not_awaited()
+
+
+@pytest.mark.asyncio
+async def test_a_household_question_that_reads_nothing_never_spends_the_grant() -> None:
+    """The "not connected yet" answer reads no data, so it must not burn the owner's grant."""
+    owner = _actor(HouseholdRole.OWNER, person_id=7)
+    spending = AsyncMock(return_value=owner)
+    audit = AsyncMock()
+    seen: list[ActivePersonContext] = []
+
+    def policy(request: AuthorizationRequest) -> AuthorizationDecision:
+        seen.append(request.actor)
+        return _decision(request, AuthorizationStatus.ALLOWED)
+
+    controller = CognitiveController(
+        today=lambda: date(2026, 8, 12),
+        legacy_turn=AsyncMock(),
+        active_person_resolver=spending,
+        observed_person_resolver=_resolver(owner),
+        policy_evaluator=policy,
+        audit_writer=audit,
+    )
+
+    plan = await controller.handle(_event("¿Cómo se llama mi esposa?"))
+
+    assert plan.status is KnowledgeStatus.UNKNOWN
+    assert "todavía" in plan.response
+    spending.assert_not_awaited()
+    assert seen == [owner]  # the policy still judged the observed actor
+    audit.assert_awaited_once()
+
+
+@pytest.mark.asyncio
+async def test_an_observed_stranger_is_denied_a_household_question() -> None:
+    controller = CognitiveController(
+        today=lambda: date(2026, 8, 12),
+        legacy_turn=AsyncMock(),
+        observed_person_resolver=_resolver(_actor(HouseholdRole.UNKNOWN, None)),
+    )
+
+    plan = await controller.handle(_event("¿Cómo se llama mi esposa?"))
+
+    assert plan.status is KnowledgeStatus.UNAUTHORIZED
+
+
+@pytest.mark.asyncio
+async def test_the_children_read_is_the_only_branch_that_spends_the_grant() -> None:
+    """Only the branch that reads authorized data awaits the consuming resolver."""
+    owner = _actor(HouseholdRole.OWNER, person_id=7)
+    spending = AsyncMock(return_value=owner)
+    observed = AsyncMock(return_value=owner)
+    tools = Mock()
+    tools.get_children = AsyncMock(
+        return_value=HouseholdToolResult(
+            tool_name=HouseholdToolName.GET_CHILDREN,
+            status=KnowledgeStatus.KNOWN,
+            value=("Joaquín",),
+        )
+    )
+    controller = CognitiveController(
+        today=lambda: date(2026, 8, 12),
+        legacy_turn=AsyncMock(),
+        active_person_resolver=spending,
+        observed_person_resolver=observed,
+        household_tools=tools,
+        consent_resolver=AsyncMock(return_value=ConsentStatus.GRANTED),
+    )
+
+    await controller.handle(_event("¿Quién soy?"))
+    await controller.handle(_event("¿Cómo se llama mi esposa?"))
+    spending.assert_not_awaited()
+
+    plan = await controller.handle(_event("¿Cómo se llaman mis hijos?"))
+
+    spending.assert_awaited_once()
+    assert plan.status is KnowledgeStatus.KNOWN
```

  The owner → stranger matrix: the "who am I" characterization is rewritten (the grant
  survives), and four tests pin the scoped grant on the real `/transcribe` route and the
  real administration route (the bearer characterization stays):

```diff
--- a/tests/integration/test_owner_stranger_matrix.py
+++ b/tests/integration/test_owner_stranger_matrix.py
@@ -5,8 +5,9 @@ receives their private data; anyone else can chat but gets none of it, changes
 nothing and inherits nothing. Every value is an invented canary — the real
 proof, with the owner's own data, runs locally and records outcomes only.

-Two tests are characterizations of documented limits (ADR-0008, ADR-0015): they
-pass today and must be rewritten deliberately when ADR-0015 changes the grant.
+One test is a characterization of a documented limit (ADR-0008): the grant proves the
+PIN, not the speaker, and stays until speaker binding changes it. The grant itself is
+bound to one named operation (ADR-0015, Plan 0051).
 """

 from collections.abc import AsyncGenerator, AsyncIterator
@@ -20,7 +21,11 @@ from pydantic import SecretStr
 import pytest
 from server.cognition.identity import PersonRecord
 from server.cognition.identity_sessions import IdentitySessionRegistry
-from server.cognition.owner_authentication import OwnerUnlockService, owner_unlock_service
+from server.cognition.owner_authentication import (
+    OwnerUnlockScope,
+    OwnerUnlockService,
+    owner_unlock_service,
+)
 from server.dependencies import get_owner_unlock_service
 from server.main import app
 from server.memory.declarative import assert_fact
@@ -109,6 +114,13 @@ class _Voice:
         self._wav = wav
         self.service = service

+    async def revoke_face(self, token: str) -> int:
+        """Ask for a biometric-administration action (a face revocation) and return its status."""
+        response = await self._client.post(
+            "/auth/owner/face/revoke", headers={"X-Iroko-Identity-Token": token}
+        )
+        return response.status_code
+
     async def speak(self, text: str, *, token: str | None = None) -> dict[str, object]:
         """Speak *text* (optionally presenting a grant) and return the JSON body."""
         self._stt.return_value = text
@@ -297,14 +309,11 @@ async def test_a_valid_grant_answers_whoever_presents_it_documented_limit(


 @pytest.mark.integration
-async def test_who_am_i_with_a_grant_names_the_owner_and_spends_it_documented_limit(
-    voice: _Voice,
-) -> None:
-    """DOCUMENTED LIMIT (ADR-0015): "who am I" consumes the one-use grant.
+async def test_who_am_i_names_the_owner_and_keeps_the_grant(voice: _Voice) -> None:
+    """ADR-0015: "who am I" confirms identity from the request and spends no grant.

-    The answer names the grant's owner to whoever presents it, and the grant is
-    gone afterwards, so a later protected question is denied. Pinned so that
-    ADR-0015's decision about the grant's scope changes this deliberately.
+    A bystander who asks it cannot burn the owner's read grant; the grant still
+    answers the next protected question.
     """
     unlock = await voice.service.unlock(_PIN)
     assert unlock is not None
@@ -313,5 +322,64 @@ async def test_who_am_i_with_a_grant_names_the_owner_and_spends_it_documented_li
     later = await voice.speak(_CHILD_QUESTION, token=unlock.token)

     assert identity["llm_response"] == "Sos Owner."
-    assert identity["authentication_consumed"] is True
-    assert later["llm_response"] == _DENIAL
+    assert identity["authentication_consumed"] is False
+    assert later["llm_response"] == _CHILD_ANSWER
+    assert later["authentication_consumed"] is True
+
+
+@pytest.mark.integration
+async def test_a_household_question_that_reads_nothing_keeps_the_grant(voice: _Voice) -> None:
+    """The "not connected yet" answer reads no data, so it must not burn the grant."""
+    unlock = await voice.service.unlock(_PIN)
+    assert unlock is not None
+
+    stub = await voice.speak("¿Cómo se llama mi esposa?", token=unlock.token)
+    later = await voice.speak(_CHILD_QUESTION, token=unlock.token)
+
+    assert "todavía no está conectada" in str(stub["llm_response"])
+    assert stub["authentication_consumed"] is False
+    assert later["llm_response"] == _CHILD_ANSWER
+
+
+@pytest.mark.integration
+async def test_a_read_grant_cannot_administer_biometrics_and_still_answers_a_read(
+    voice: _Voice,
+) -> None:
+    """A token issued for a protected read is refused by biometric administration, unspent."""
+    unlock = await voice.service.unlock(_PIN)
+    assert unlock is not None
+
+    refused = await voice.revoke_face(unlock.token)
+    answer = await voice.speak(_CHILD_QUESTION, token=unlock.token)
+
+    assert refused == 401
+    assert answer["llm_response"] == _CHILD_ANSWER
+    assert answer["authentication_consumed"] is True
+
+
+@pytest.mark.integration
+async def test_a_biometric_admin_grant_cannot_read_and_still_administers(voice: _Voice) -> None:
+    """A token issued for biometric administration is refused by a read, unspent."""
+    unlock = await voice.service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
+    assert unlock is not None
+
+    answer = await voice.speak(_CHILD_QUESTION, token=unlock.token)
+    administered = await voice.revoke_face(unlock.token)
+
+    assert answer["llm_response"] == _DENIAL
+    assert answer["authentication_consumed"] is False
+    assert administered == 204
+
+
+@pytest.mark.integration
+async def test_an_administration_grant_is_one_use_even_after_a_refused_read(
+    voice: _Voice,
+) -> None:
+    unlock = await voice.service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
+    assert unlock is not None
+
+    await voice.speak(_CHILD_QUESTION, token=unlock.token)
+    first = await voice.revoke_face(unlock.token)
+    second = await voice.revoke_face(unlock.token)
+
+    assert (first, second) == (204, 401)
```

  Classic chat and the stream, same two behaviours:

```diff
--- a/tests/integration/test_owner_authenticated_turn.py
+++ b/tests/integration/test_owner_authenticated_turn.py
@@ -17,7 +17,11 @@ from pydantic import SecretStr
 import pytest
 from server.cognition.identity import PersonRecord
 from server.cognition.identity_sessions import IdentitySessionRegistry
-from server.cognition.owner_authentication import OwnerUnlockService, owner_unlock_service
+from server.cognition.owner_authentication import (
+    OwnerUnlockScope,
+    OwnerUnlockService,
+    owner_unlock_service,
+)
 from server.dependencies import get_owner_unlock_service
 from server.main import app
 from server.memory.entity_labels import get_person_label
@@ -304,3 +308,53 @@ async def test_transcribe_replayed_token_denies_without_reading_v4(
     assert first.json()["authentication_consumed"] is True
     assert second.json()["authentication_consumed"] is False
     reader_spy.assert_not_awaited()
+
+
+@pytest.mark.integration
+async def test_chat_who_am_i_names_the_owner_and_keeps_the_grant(
+    acceptance_db: None, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    """ADR-0015: "who am I" over `/chat` spends no grant; the next read still answers."""
+    service = _service()
+    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
+    unlock = await service.unlock(_PIN)
+    assert unlock is not None
+    headers = {"X-Iroko-Identity-Token": unlock.token}
+
+    async with _client() as client:
+        identity = await client.post(
+            "/chat",
+            headers=headers,
+            json={"message": "¿Quién soy?", "conversation_id": "acceptance-owner"},
+        )
+        read = await client.post(
+            "/chat",
+            headers=headers,
+            json={"message": _CHILD_QUESTION, "conversation_id": "acceptance-owner"},
+        )
+
+    assert identity.json()["response"] == "Sos Pipec."
+    assert identity.json()["authentication_consumed"] is False
+    assert read.json()["response"] == _CHILD_ANSWER
+    assert read.json()["authentication_consumed"] is True
+
+
+@pytest.mark.integration
+async def test_chat_refuses_an_administration_grant_for_a_read_and_keeps_it(
+    acceptance_db: None, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    """A token issued for biometric administration never answers a protected read."""
+    service = _service()
+    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
+    assert unlock is not None
+
+    async with _client() as client:
+        response = await client.post(
+            "/chat",
+            headers={"X-Iroko-Identity-Token": unlock.token},
+            json={"message": _CHILD_QUESTION, "conversation_id": "acceptance-owner"},
+        )
+
+    assert response.json()["response"] != _CHILD_ANSWER
+    assert response.json()["authentication_consumed"] is False
```

```diff
--- a/tests/integration/test_owner_authenticated_stream.py
+++ b/tests/integration/test_owner_authenticated_stream.py
@@ -21,7 +21,11 @@ from pydantic import SecretStr
 import pytest
 from server.cognition.identity import PersonRecord
 from server.cognition.identity_sessions import IdentitySessionRegistry
-from server.cognition.owner_authentication import OwnerUnlockService, owner_unlock_service
+from server.cognition.owner_authentication import (
+    OwnerUnlockScope,
+    OwnerUnlockService,
+    owner_unlock_service,
+)
 from server.dependencies import get_owner_unlock_service
 from server.main import app
 from server.memory.entity_labels import get_person_label
@@ -260,3 +264,56 @@ async def test_stream_generic_turn_with_valid_token_does_not_consume_it(
     audio_events = [event for event in protected_events if event["type"] == "audio"]
     assert audio_events[0]["text"] == _CHILD_ANSWER
     assert protected_events[-1]["authentication_consumed"] is True
+
+
+@pytest.mark.integration
+async def test_stream_who_am_i_names_the_owner_and_keeps_the_grant(
+    acceptance_db: None, monkeypatch: pytest.MonkeyPatch, silence_wav_bytes: bytes
+) -> None:
+    """ADR-0015 parity: "who am I" over the stream spends no grant either."""
+    service = _service()
+    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
+    unlock = await service.unlock(_PIN)
+    assert unlock is not None
+
+    async with _client() as client:
+        _mock_stt_tts(monkeypatch, text="¿Quién soy?")
+        identity = await _post_stream(
+            client, token=unlock.token, silence_wav_bytes=silence_wav_bytes
+        )
+
+        identity_events = _parse_ndjson(identity)
+        spoken = [event for event in identity_events if event["type"] == "audio"]
+        assert spoken[0]["text"] == "Sos Pipec."
+        assert identity_events[-1]["authentication_consumed"] is False
+
+        _mock_stt_tts(monkeypatch, text=_CHILD_QUESTION)
+        protected = await _post_stream(
+            client, token=unlock.token, silence_wav_bytes=silence_wav_bytes
+        )
+
+    protected_events = _parse_ndjson(protected)
+    audio_events = [event for event in protected_events if event["type"] == "audio"]
+    assert audio_events[0]["text"] == _CHILD_ANSWER
+    assert protected_events[-1]["authentication_consumed"] is True
+
+
+@pytest.mark.integration
+async def test_stream_refuses_an_administration_grant_for_a_read_and_keeps_it(
+    acceptance_db: None, monkeypatch: pytest.MonkeyPatch, silence_wav_bytes: bytes
+) -> None:
+    service = _service()
+    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
+    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
+    assert unlock is not None
+    _mock_stt_tts(monkeypatch, text=_CHILD_QUESTION)
+
+    async with _client() as client:
+        response = await _post_stream(
+            client, token=unlock.token, silence_wav_bytes=silence_wav_bytes
+        )
+
+    events = _parse_ndjson(response)
+    audio_events = [event for event in events if event["type"] == "audio"]
+    assert audio_events[0]["text"] != _CHILD_ANSWER
+    assert events[-1]["authentication_consumed"] is False
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_cognitive_controller.py tests/integration/test_owner_stranger_matrix.py tests/integration/test_owner_authenticated_turn.py tests/integration/test_owner_authenticated_stream.py -q -p no:cacheprovider`.
  Expected: `TypeError: CognitiveController.__init__() got an unexpected keyword argument
  'observed_person_resolver'` in the controller tests, and the who-am-i and
  not-connected integration tests failing (the grant is still spent, or the answer is the
  unknown copy).

- [ ] **Step 3: Implement the controller seam.**

```diff
--- a/server/src/server/cognition/controller.py
+++ b/server/src/server/cognition/controller.py
@@ -104,6 +104,7 @@ class CognitiveController:
         today: Callable[[], date],
         legacy_turn: LegacyTextTurn,
         active_person_resolver: ActivePersonResolver = _unknown_active_person,
+        observed_person_resolver: ActivePersonResolver = _unknown_active_person,
         policy_evaluator: PolicyEvaluator = evaluate_authorization,
         audit_writer: AuditWriter = _discard_audit,
         household_tools: HouseholdKnowledgeTools | None = None,
@@ -115,7 +116,11 @@ class CognitiveController:
         Args:
             today: Local date boundary owned by the adapter composition root.
             legacy_turn: Existing generic text-turn service for safe fallback.
-            active_person_resolver: Trusted internal active-person boundary.
+            active_person_resolver: Trusted internal active-person boundary that may
+                spend a one-use grant; awaited only by the branch that reads data.
+            observed_person_resolver: The same actor seen from the evidence already on
+                the request, without spending any grant (ADR-0015); used by the
+                branches that read nothing. Defaults to the public unknown actor.
             policy_evaluator: Pure deterministic authorization evaluator.
             audit_writer: Local safe-audit boundary for protected decisions.
             household_tools: Optional closed P0.5-B2 family-tool collaborator.
@@ -125,6 +130,7 @@ class CognitiveController:
         self._today = today
         self._legacy_turn = legacy_turn
         self._active_person_resolver = active_person_resolver
+        self._observed_person_resolver = observed_person_resolver
         self._policy_evaluator = policy_evaluator
         self._audit_writer = audit_writer
         self._household_tools = household_tools
@@ -211,9 +217,13 @@ class CognitiveController:
         need: InformationNeed,
         actor: ActivePersonContext | None = None,
     ) -> ResponsePlan:
-        """Authorize and audit a protected branch before any legacy delegation."""
+        """Authorize and audit a protected branch before any legacy delegation.
+
+        When the caller did not already resolve the actor, it is only observed: this
+        branch answers "not connected yet" and reads no data, so it never spends a grant.
+        """
         request = AuthorizationRequest(
-            actor=await self._active_person_resolver(event) if actor is None else actor,
+            actor=await self._observed_person_resolver(event) if actor is None else actor,
             action=AuthorizationAction.READ_HOUSEHOLD_DATA,
             visibility=frozenset({DataVisibility.HOUSEHOLD}),
             sensitivity=frozenset({DataSensitivity.PRIVATE}),
@@ -234,13 +244,12 @@ class CognitiveController:
         self,
         event: CognitiveEvent[TextTurnPayload],
     ) -> ResponsePlan:
-        """Confirm the speaker only from this request's fresh owner evidence.
+        """Confirm the speaker only from the evidence already on this request.

-        Reuses the same injected `active_person_resolver` the protected
-        household branches already use, so this consumes the same one-use
-        owner grant a household read would — no separate identity mechanism.
+        Uses the observed actor and never spends a one-use grant (ADR-0015): a
+        bystander asking "who am I" cannot burn the owner's read grant.
         """
-        actor = await self._active_person_resolver(event)
+        actor = await self._observed_person_resolver(event)
         if actor.status is ActivePersonStatus.IDENTIFIED and actor.display_name is not None:
             return ResponsePlan(
                 need=InformationNeed.ACTIVE_IDENTITY,
```

- [ ] **Step 4: Wire the routes.**

```diff
--- a/server/src/server/routers/chat.py
+++ b/server/src/server/routers/chat.py
@@ -78,6 +78,12 @@ async def chat(
         turn_log.log_actor("chat", actor)
         return actor

+    async def observe_actor(event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
+        """Name the actor for branches that read nothing, without spending the grant."""
+        actor = await request_identity.peek_actor(event)
+        turn_log.log_actor("chat", actor)
+        return actor
+
     async def legacy_turn(message: str, conversation_id: str) -> TextTurnResult:
         """Delegate to text-turn orchestration with the shared HTTP client."""
         return await process_text_turn(resources.http_client, message, conversation_id)
@@ -86,6 +92,7 @@ async def chat(
         today=_today,
         legacy_turn=legacy_turn,
         active_person_resolver=resolve_actor,
+        observed_person_resolver=observe_actor,
         policy_evaluator=evaluate_authorization,
         audit_writer=record_authorization_decision,
         household_tools=HouseholdKnowledgeTools(reader=PolicyGatedV4Reader()),
```

```diff
--- a/server/src/server/routers/transcribe.py
+++ b/server/src/server/routers/transcribe.py
@@ -129,12 +129,14 @@ class _RequestIdentity:
     """Uniform per-request actor/consent resolver over the fused identity evidence.

     Attributes:
-        resolve_actor: The actor resolver to hand to the controller.
+        resolve_actor: The actor resolver to hand to the controller; it may spend the grant.
+        peek_actor: The same actor observed without spending any grant (ADR-0015).
         resolve_consent: The matching consent resolver.
         fused: The fusion resolver, the source of `.consumed` and `.identity_source`.
     """

     resolve_actor: ActivePersonResolver
+    peek_actor: ActivePersonResolver
     resolve_consent: ConsentResolver
     fused: FusedIdentityResolver

@@ -171,6 +173,7 @@ def _build_request_identity(
     fused = build_fused_identity_resolver(pin, frame=frame, wav_bytes=wav_bytes)
     return _RequestIdentity(
         resolve_actor=fused.resolve_actor,
+        peek_actor=fused.peek_actor,
         resolve_consent=fused.resolve_consent,
         fused=fused,
     )
@@ -189,6 +192,19 @@ def _logged_voice_actor_resolver(
     return resolve_actor


+def _logged_voice_observer(
+    request_identity: _RequestIdentity,
+) -> ActivePersonResolver:
+    """Wrap the observing resolver to keep the actor log line without spending a grant."""
+
+    async def observe_actor(event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
+        actor = await request_identity.peek_actor(event)
+        turn_log.log_actor("voice", actor)
+        return actor
+
+    return observe_actor
+
+
 def _voice_controller(
     client: httpx.AsyncClient,
     background_tasks: BackgroundTasks,
@@ -227,6 +243,7 @@ def _voice_controller(
         today=_today,
         legacy_turn=legacy_turn,
         active_person_resolver=_logged_voice_actor_resolver(request_identity),
+        observed_person_resolver=_logged_voice_observer(request_identity),
         policy_evaluator=evaluate_authorization,
         audit_writer=record_authorization_decision,
         household_tools=HouseholdKnowledgeTools(reader=PolicyGatedV4Reader()),
```

- [ ] **Step 5: Run them, then prove the streaming test bites.** The four files above
  must pass. Then **temporarily** delete the line
  `observed_person_resolver=_logged_voice_observer(request_identity),` from
  `_voice_controller` in `transcribe.py` and run
  `uv run pytest tests/integration/test_owner_authenticated_stream.py -q -p no:cacheprovider -k who_am_i`:
  it must fail. Restore the line.

- [ ] **Step 6: Lint, run the whole selection and commit.** `ruff check` and
  `ruff format --check` over the explicit paths, then
  `uv run pytest -m "not slow and not hardware and not eval" -n auto -q -p no:cacheprovider`
  (all pass; the rehearsal's final full gate was 1854 tests). Commit —
  `feat(server): observe the actor on branches that read nothing`.

---

## Task 6: Real hardware acceptance

**Files:** Create `docs/evals/0051-scoped-grant-acceptance.md`; modify `docs/evals/README.md`
and this plan (execution record). No production code.

Pipec runs these on his machine with the server and robot he starts himself; the
executor records outcomes only (a status, a yes or no, a timing), never a name, a
transcript or a photo. Record the active flags (`FACE_AUTHENTICATION_ENABLED`,
`SPEAKER_AUTHENTICATION_ENABLED`, `ROBOT_STREAMING`).

- [ ] **Step 1: Administration still works with its own scope.** `just setup-personal
  status` reports ready. `just onboard` (face phase) completes: it asks for the PIN,
  enrols the face and prints the profile id. With the speaker flag on,
  `just speaker-auth-demo --enroll` enrols one reference and `--revoke` purges.
- [ ] **Step 2: The read grant still answers, once.** `ROBOT_OWNER_UNLOCK_PROMPT=true`,
  `just run-server` and `just run-robot`: enter the PIN once, ask the protected child
  question: answered, `authentication_consumed=true`. Ask it again with no new PIN:
  denied. Do it in classic and in streaming mode.
- [ ] **Step 3: "¿Quién soy?" keeps the grant.** With a fresh PIN, ask "¿Quién soy?"
  first: the robot names the owner and `authentication_consumed=false`; then the child
  question: answered, `authentication_consumed=true`. Classic and streaming.
- [ ] **Step 4: A household question that reads nothing keeps the grant.** With a fresh
  PIN, ask "¿Cómo se llama mi esposa?": "todavía no está conectada" with
  `authentication_consumed=false`; then the child question: answered.
- [ ] **Step 5: The scopes refuse each other.** With the server's loopback address,
  unlock for `biometric_admin` and present that token to a protected read (a child
  question): refused, token not spent, and the same token then authorizes
  `POST /auth/owner/face/revoke` (204, only if Pipec accepts revoking and re-enrolling
  his face afterwards; otherwise record this case as not run). Unlock for the default
  scope and present that token to `POST /auth/owner/face/revoke`: 401.
- [ ] **Step 6: The unrun PIN case of Plan 0054 (D-7).** With the face not identifying
  (camera covered, or `FACE_AUTHENTICATION_ENABLED=false`), a presented read grant
  answers the child question with identity source `pin`, assurance `strong`. Record it,
  or record that it was not run and why.
- [ ] **Step 7: Record.** `docs/evals/0051-scoped-grant-acceptance.md` holds: date, commit
  SHA, hardware line, the flags, one row per case above with its outcome, and a
  *Limitations* paragraph (one owner, one machine; replay and the bearer limit are not
  defended here; the cross-scope case was run through loopback HTTP, not through the
  robot, which never asks for the admin scope). Numbers and outcomes only.
- [ ] **Step 8: Commit** — `docs(evals): record the scoped grant acceptance`.

---

## Task 7: Documentation truth

**Files:** the docs listed under *Permitted files*. No production code.

- [ ] **Step 1: ADR-0015.** Add a line to its header: *Decision 1 implemented by Plan 0051
  on the merge date; decisions 2 and 3 are unchanged.* Update *Test consequences* to say
  the two characterization tests were rewritten as the plan describes, and add the
  decision this plan took where the ADR left room: a wrong-operation presentation is
  refused and not spent, and the unlock response echoes the scope. Do not reopen decisions
  2 and 3. In ADR-0016, the sentences that say the PIN stays a bearer token "until Plan
  0051 scopes it" (and the matching review trigger) now say: scoped by Plan 0051, still a
  bearer of the PIN, never of the speaker.
- [ ] **Step 2: `current-state.md`.** Update the *One-use owner-authenticated classic turn*
  row (a grant authorizes exactly one operation, named at unlock; the default is the
  read), the *Consented local face evidence* and *Speaker recognition* rows (their
  enrol and revoke routes require a `biometric_admin` grant), and the capability-matrix
  line that said grants are not operation-bound: now they are; the bearer limit stays
  documented. Preserve every other row.
- [ ] **Step 3: `identity-and-access.md`.** In *Locked posture and capability scope*, state
  that the PIN grant is bound to the one operation named at unlock and list the two
  scopes.
- [ ] **Step 4: Operator manual.** In *Tier 1*, say the grant authorizes one read; in the
  face and voice enrolment sections say the scripts unlock for `biometric_admin`
  themselves and that enrolling and then asking a protected question takes two unlocks.
- [ ] **Step 5: Roadmap and maps.** Mark Plan 0051 closed in the CM-1 row of the roadmap
  and of the conversational-memory map (CM-1 stays open for its other plans: the
  `read`/`propose`/`confirm`/`correct`/`forget` capabilities); update the *What is really
  missing* row; fix `personal-companion-delivery-map.md` where it describes the
  enrolment routes as requiring only a PIN-consumed token.
- [ ] **Step 6: Board.** `docs/plans/README.md` and `docs/plans/open/README.md` move 0051
  to closed with its result, `NOW` is empty again, and the next item is Plan 0057 then
  the streaming repair (hard gate of CM-2). Move this file to `docs/plans/completed/` in
  the closure PR. The next free plan number is recorded.
- [ ] **Step 7: Architecture diagram.** `current-state.md` changed, so (Pipec's standing
  preference) refresh the Archify diagram: update
  `docs/architecture/diagrams/current-state.json` only if a node's text changes, then
  `validate` → `deliver` to regenerate the `.html`; if no node changes, still run
  `validate` and record "diagram unchanged".
- [ ] **Step 8: Verify and commit.** Python blocks in these docs are checked by CI's
  `ruff format --check` (the local hooks skip `.md`): run `uv run ruff format --check .`
  and `uv run ruff check .`. Check every relative link in the touched docs (the scratch
  link checker used for Plan 0057's documentation, or any equivalent), then
  `uv run python scripts/check_reserved_terms.py`, `git diff --check`, and commit —
  `docs: align current-state and roadmap with plan 0051`.

## Non-goals

Each exclusion has an owner so that nothing is left as text only:

- **Binding the grant to the speaker, a face veto and liveness** (ADR-0015 decision 2).
  Owner: PC-4 and its follow-ups (closed) and ADR-0016. The bearer limit stays pinned by
  the matrix test that this plan keeps.
- **The memory capabilities `read`, `propose`, `confirm`, `correct` and `forget`.** Owner:
  the later plans of CM-1. Each declares its scope in the plan that adds the capability
  (D-5).
- **The `strong` requirement of `SECURITY` data.** Owner: CM-3 and CM-5 (roadmap).
- **A shorter lifetime for the administration scope.** Owner: Pipec, if he wants it; the
  setting exists (ADR-0015 decision 3).
- **A persistent or shared grant registry.** Owner: none; the registry is process-local
  by design.
- **Any change to the robot.** The robot keeps unlocking for the default scope.
- **The streaming-protocol repair.** Owner: Plan 0057 and the repair that follows it,
  ordered after CM-1 and before CM-2.

## Verification

Run before claiming done, in this order:

```powershell
uv lock --check
just lint
just typecheck
just test
just audit
just check
uv run ruff format --check .
uv build --all-packages
git diff --check
git diff --stat main -- robot
```

`git diff --stat main -- robot` must print nothing (the robot is not edited).

Plus `ruff check` and `ruff format --check` over the **explicit paths** of every file of
Tasks 1 to 5 (`just lint` does not look at `scripts/`; the pre-commit hook does), and the
exact deterministic CI coverage command:

```powershell
uv run pytest -m "not slow and not hardware and not eval" `
  --cov=server/src --cov=robot/src --cov-report=term --cov-fail-under=80
```

## Completion criteria

- The registry records the scope a token was issued for and refuses, without spending
  it, a presentation for another scope (Task 1).
- `unlock` issues a read grant by default and an administration grant on request; a
  resolver built for one scope never consumes a token issued for the other; `peek_actor`
  names the owner without spending; a refusal logs only the closed reason (Task 2).
- The fused resolver observes without spending and ignores a token of another scope
  (Task 3).
- `POST /auth/owner/unlock` accepts and echoes `scope` (additive, an unknown scope is a
  422 without the PIN); face and voice enrol and revoke require an administration grant
  and refuse a read grant unspent; the three scripts unlock for the admin scope and the
  robot never does (Task 4).
- "¿Quién soy?" and a household answer that reads nothing never spend the grant, over
  classic, `/transcribe` and the stream; only the children read does; the observing seam
  defaults to the unknown actor (Task 5).
- The hardware cases are recorded, including the unrun PIN case of Plan 0054, or each
  not-run case is recorded with its reason (Task 6).
- ADR-0015, `current-state.md`, the manual, the roadmap and the board match the code;
  every gate above passes; `git diff --stat main -- robot` is empty (Task 7).

## Real runtime acceptance

Task 6 is the acceptance: Pipec's own session, recorded outcomes only.

## Rollback

Revert the squash-merged PR as one unit. The only wire change is additive (an optional
request field and a response field), there is no migration and no new dependency, and the
robot is untouched, so a revert restores the unscoped grant exactly as it was.

## Execution record

_Empty until the plan is promoted and executed._

## Closure

One PR from `feat/0051-scoped-owner-grants`, based on `main` after the Task 0
revalidation. On merge: move this file to `completed/`, update the board, the roadmap
rows, `current-state.md` and ADR-0015, and record the PR number and squash SHA in a small
documentation PR (as for Plans 0050, 0055 and 0056). CM-1 stays open for its other
plans; CM-2 stays gated on the streaming-protocol repair.
