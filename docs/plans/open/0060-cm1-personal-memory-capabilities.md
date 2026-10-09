# 0060 — Personal-memory capabilities (CM-1)

> **Status:** `Draft` — written 2026-10-08 as the rest of CM-1, after Pipec confirmed the queue
> order the same day (CM-1 before CM-2). **Not authorized.** Pipec promotes it to `Ready` and
> selects it as `NOW`; until then `NOW` stays empty and nothing here may be executed. Decision D-3
> (`confirm` needs `strong`) was chosen by Pipec on 2026-10-08; the others are proposals for the
> moment of promotion, D-4 to D-6 came out of independent security and architecture reviews of the
> draft [ADR 0019](../../adr/0019-personal-memory-capabilities.md) (`Proposed`, becomes `Accepted`
> when this plan closes; the reasoning is in the ADR), and **D-10 is an open decision Pipec must
> settle at promotion**.

> **For agentic workers:** REQUIRED SUB-SKILLS: `superpowers:executing-plans`,
> `superpowers:test-driven-development`, `superpowers:verification-before-completion`,
> `superpowers:finishing-a-development-branch`. Execute only while this is the explicitly
> authorized `NOW` item, in a new session. **Pipec's rules win over the skills:** one plain branch
> from `main` (`git checkout -b`), never a git worktree (treat any "create a worktree" instruction
> as "create the branch"), no subagents unless Pipec asks, and this plan lives under `docs/plans/`,
> not `docs/superpowers/plans/`. Implement exactly the tasks below, in order, one commit per task.
> If evidence contradicts the plan, stop and report the conflict instead of redesigning. Pipec runs
> every local process (server, robot, scripts that use the camera or the microphone); you record
> what they print, outcomes only. The Bash tool of this environment loses backslashes and non-ASCII
> characters in heredocs: create and edit files with the Write and Edit tools.

**Goal:** Give personal memory the five closed capabilities the
[conversational-memory map](../../roadmap/conversational-memory-delivery-map.md) names
(`read_personal_conversation_memory`, `propose_personal_memory`, `confirm_personal_memory`,
`correct_personal_memory`, `forget_personal_memory`) as **pure authorization policy**: owner only,
own data only, a minimum identity assurance per capability, and an owner PIN grant that counts only
for the operation it was issued for and only once spent. Nothing is stored, read, routed or spoken:
no consumer exists, and architecture guards keep it so until a later plan wires one.

**Architecture:** Five new `AuthorizationAction` members and a read-only capability table in
`cognition/authorization.py` that a fixed-order evaluator reads (owner, own data, assurance, grant,
consent). The grant scope and the "spent" flag travel inside the `local_unlock` evidence
(`IdentityEvidence.grant_scope`, `grant_spent`), set by the grant registry, so the policy stays a
pure function of the request and a peeked grant cannot authorize. `OwnerUnlockScope` gains
`personal_memory_read` and `personal_memory_forget`. The eleven old actions are pinned by a
characterization digest before anything changes. The V4 reader serves household data only and is
not touched.

**Tech Stack:** Python 3.12, pydantic, pytest (+ xdist). No new dependency, no migration.

**Spec:** [ADR 0019](../../adr/0019-personal-memory-capabilities.md) (this plan implements it),
[ADR 0009](../../adr/0009-locked-posture-and-scoped-capabilities.md) (a grant is bound to a named
operation), [ADR 0015](../../adr/0015-owner-grant-scope-and-speaker-binding.md) decision 1 (the
closed scope set), [ADR 0016](../../adr/0016-face-and-voice-identity-fusion.md) §3 (assurance) and
§9 (replay); the CM-1 row of the
[roadmap](../../roadmap/cognitive-roadmap.md#canonical-pre-electronics-delivery-portfolio) and of
the [conversational-memory map](../../roadmap/conversational-memory-delivery-map.md); the
*Capability matrix* of [`current-state.md`](../../architecture/current-state.md).

**Rehearsal (2026-10-08).** Every diff below was produced test-first in a scratch copy of `main`
(`29cfbc0`), one commit per task, with the real virtual environment, and then reworked once after
independent code and security reviews. Under the CI marker filter
(`-m "not slow and not hardware and not eval" -n auto`) the suite went from **2298** to **2472**
passed (+174: Task 1 +23, Task 2 0, Task 3 +7, Task 4 +69, Task 5 +21, Task 6 +44, Task 7 +10).
`ruff check .`, `ruff format --check .` (416 files), `mypy server/src robot/src` (103 files) and
pyright (0 errors) were clean after every task. The RED of each task was observed for the stated
reason. Four things are green on arrival by design and prove themselves by a mutation step: the
Task 1 characterization, the Task 5 oracle matrix, the Task 7 guards and invariant sweep, and the
four scope-string tests of `test_biometric_admin_scope_callers.py` (Task 6). Not rehearsed:
Task 8 (real runtime) and Task 9 (documentation). Treat the diffs as rehearsed code, not as a
substitute for the RED/GREEN record each task requires. `just gate` counts more tests than the CI
filter (2315 at `29cfbc0`). `authorization.py` grows from about 400 to 610 lines and
`test_personal_memory_policy.py` is 962 lines (exhaustive matrices, parametrized); see D-8.

## Global Constraints

- No real household data, voice, face or name in any tracked file, test, prompt, doc or commit
  message: the tests use invented canaries (`scripts/check_reserved_terms.py` guards this).
- The PIN and the token are never logged, echoed or committed. Every decision reason is a fixed
  sentence with no protected value, id or name (a test pins it).
- Wire changes are **additive only**: `POST /auth/owner/unlock` accepts two more values of the
  optional `scope` field and echoes them. No field is removed or renamed. `IdentityEvidence` gains
  two defaulted fields. The robot sends nothing new and never asks for the new scopes.
- The eleven existing actions keep their exact decisions (Task 1 pins them before any change).
- Face and voice stay identity evidence, never authorization and never the sole route to an
  irreversible operation (ADR 0006, ADR 0009).
- Type hints on every signature, Google docstrings on public APIs, `ruff` clean over the **explicit
  paths** of every file touched, `mypy server/src robot/src` clean, no `Any` without a comment, no
  `# type: ignore`.
- Every new test is observed RED for the stated reason before its implementation. Four things are
  the documented exceptions, green on arrival and proven by a mutation step: the Task 1
  characterization, the Task 5 oracle matrix, the Task 7 guards and sweep, and the four scope-string
  tests of `test_biometric_admin_scope_callers.py` (Task 6).
- A commit title is at most 72 characters (commitizen rejects longer ones silently): check
  `git log -1` after every commit.

## Review Focus

Inputs the spec implies that are most likely to bite, each pinned by a test in its owning task:

1. A grant issued for another operation never counts, in every direction: a `personal_protected_read`,
   `biometric_admin` or `personal_memory_read` grant cannot forget; a `personal_protected_read` or
   `biometric_admin` grant cannot read personal memory; a forget grant cannot read. Presented to the
   wrong resolver, each is refused **and not spent** (Task 6).
2. A grant that was only peeked ("who am I" style) names its owner but authorizes nothing: forget
   is denied with a peeked forget grant and allowed with the same grant after `resolve_actor` spent
   it, using the real resolvers (Task 6).
3. Face and a verified voice (`strong`, no PIN) never forget; `confirm` is reachable only that way;
   `propose`, `confirm` and `correct` deny any `local_unlock` item whatever its scope (Task 6).
4. `IdentityAssurance` is a `str` enum: `basic < none` alphabetically. Assurance is compared only
   through an explicit rank, and `none` never reaches any minimum (Tasks 3 and 4).
5. `SECURITY` data below `strong` stops at the generic gate with its `p0.5.assurance-required` id
   for all five actions (Task 4).
6. Consent is strict: `not_required`, `missing` and `revoked` all deny a sensitive category for the
   four consent-bearing capabilities; `forget` ignores consent entirely, a revoked one included;
   sensitivity `private` behaves like `normal` (Tasks 4 and 5).
7. Own data: a missing target, another person's id and a visibility outside the capability's set
   are denied; `forget` reaches `personal`, `private` and `temporary` and nothing else (Tasks 4, 5).
8. Non-owner roles are denied, never asked for confirmation, and apart from the generic `security`
   gate that runs first (ADR 0019 §5) see no category-dependent id (Task 4).
9. Nothing consumes the new surface: the new action names, the four old memory actions, the two new
   scopes and `select_person` are referenced only where the guards allow, and a synthetic offender
   trips each guard (Task 7).
10. `strong` is only ever produced from a `local_unlock` item or a face and a voice, over every
    subset of the six evidence sources (Task 7).
11. The decision audit accepts the new action names with no migration (Task 4).
12. OpenAPI is additive: the scope enum lists four values, `scope` stays optional, the response
    echoes it, invalid scopes stay 422 (Task 6).
13. A `local_unlock` item that names another person than the actor, or that is expired, never
    counts, even when marked spent (Task 6): the real resolvers cannot build one today, but the
    evidence tuple is the caller's input and an irreversible capability should not trust it blindly.
14. As drafted, a photograph of the owner reaches `medical`, `biometric`, `location` and `child_data`
    personal memory for read, propose and correct (the face grants consent automatically); the
    matrix pins that on purpose until D-10 is decided (Tasks 4 and 5).

---

## Why this plan exists

| Finding | Evidence in the merged code | Closed by |
|---|---|---|
| The five capabilities exist only in documents | `AuthorizationAction` has eleven members; `PROPOSE_MEMORY` allows any owner regardless of whose data, `COMMIT_MEMORY` and `DELETE_HOUSEHOLD_DATA` are owner-only administration | Tasks 2 to 5 |
| A read grant would authorize a forget the day a branch exists | a spent PIN grant yields `strong` and granted consent; `/chat` and `/transcribe` spend the default read scope before the intent is known | Task 6 |
| A peeked grant is indistinguishable from a spent one | `peek_actor` and `resolve_actor` return the same `ActivePersonContext`; only `consent` differs | Task 6 |
| `IdentityAssurance` compares alphabetically | `str, Enum` at `identity.py`; `"basic" < "none"` | Tasks 3 and 4 |
| The default scope would be widened | ADR 0009 and ADR 0015 define `personal_protected_read` as one read of confirmed `child_data` | Task 6 (a new read scope) |
| Nothing prevents a later caller from using the old memory actions | `PROPOSE_MEMORY`, `COMMIT_MEMORY`, `DELETE_HOUSEHOLD_DATA`, `EXPORT_HOUSEHOLD_DATA` are referenced only by the policy today | Task 7 |
| The V4 reader serves personal data? | **No**: all ten predicates are `household`, writers store the default, the reader withholds other labels; nothing to connect | Task 0 re-audits it |
| The speaker is not bound to the grant; face and voice are replayable | ADR 0015 decision 2, ADR 0016 §9 | not here |

## Task overview

| # | Task | Closes |
|---:|---|---|
| 0 | Revalidate the baseline | — |
| 1 | Pin the eleven old actions | nothing old can move unnoticed |
| 2 | Five new actions | the vocabulary |
| 3 | The capability table | declared minimums, scopes and visibilities |
| 4 | The evaluator | owner, own data, assurance, consent, fixed order |
| 5 | The exhaustive matrix | every cell checked against an independent oracle |
| 6 | Evidence-carried grants and the two scopes | a read grant cannot forget; a peeked grant authorizes nothing |
| 7 | Guards and invariants | nothing consumes it; `strong` has only two sources |
| 8 | Real runtime acceptance | the unlock endpoint with the new scopes |
| 9 | Documentation truth | ADR 0019 `Accepted`, the matrices, the diagram |

## Decisions

Proposed 2026-10-08. D-3 is Pipec's own choice (2026-10-08, after the security audit); the rest are
confirmed by Pipec when he promotes the plan, and are not asked again afterwards.

1. **D-1 — Five new closed actions; the old ones do not move.** The names are the memory map's.
   `PROPOSE_MEMORY`, `COMMIT_MEMORY`, `DELETE_HOUSEHOLD_DATA` and `EXPORT_HOUSEHOLD_DATA` stay as
   they are (CM-3 decides whether to retire them) and a guard forbids any new use.
2. **D-2 — Owner only, own data only.** `target_person_id` must equal the actor's person id and the
   visibility must lie inside the capability's set: `personal` for read, propose, confirm and
   correct; `personal`, `private` or `temporary` for forget (erasure must reach whatever a writer can
   store under the owner's name). Others get `denied`, never `requires_confirmation`.
3. **D-3 — Minimum assurance per capability.** `read`, `propose`, `correct`: `basic` (the owner's
   face). `confirm` and `forget`: `strong`. `confirm` is the commit point of a memory, and a face
   alone cannot tell the owner from a photograph or from a second person speaking beside them;
   a consequence is that `confirm` is reachable only through face and a verified voice (it has no
   PIN route) until a plan that wires it adds a `personal_memory_confirm` scope.
4. **D-4 — `forget` requires a spent forget grant and ignores consent.** Face and voice at `strong`
   never suffice (both are replayable, ADR 0016 §9). Consent is not applied because withdrawing
   consent is a reason to erase.
5. **D-5 — Two new unlock scopes, `personal_protected_read` unchanged.** `personal_memory_read` and
   `personal_memory_forget`. The default scope that `/chat` and `/transcribe` spend keeps meaning one
   read of confirmed `child_data`; widening it would let a default-scope token read every personal
   category.
6. **D-6 — The scope and the spent state travel in the evidence.** No `grant_scope` on the request:
   a caller-supplied value is the discipline ADR 0015 rejected, and it cannot tell a peek from a spend.
7. **D-7 — Policy only; nothing is wired.** The wiring obligations (consuming resolver with the
   capability's own scope, classification before retrieval, audit before the side effect, generic
   denial text, `correct` that supersedes, `forget` only after CM-3's confirmation and a shorter
   grant lifetime) are written in ADR 0019 §6, and the guards of Task 7 enforce the no-consumer rule.
   Two of them need to be remembered here: single use protects a request, not an erasure (the
   resolver hands the same spent actor to every later evaluation in the request), so `forget` is
   evaluated at most once per spent grant and a second target needs a fresh grant; and only the
   confirmed-execution turn calls the consuming resolver with the forget scope, because a peeked
   grant is always denied, so the "are you sure?" turn must not gate on a `forget` decision.
8. **D-8 — The policy stays in `authorization.py`.** It grows from about 400 to about 610 lines
   (and `test_personal_memory_policy.py` is about 960 lines of exhaustive, parametrized matrices,
   trimmed once from 1,244 by a review with the coverage kept) and
   the old dispatcher is renamed `_evaluate_legacy_request` (unchanged) so the new dispatcher stays
   under the return-count limit. The size guideline says to split when a second responsibility
   appears; extracting the request types so a separate module can import them is deferred.
9. **D-9 — Acceptance is automated plus one short operator check.** Nothing consumes the new
   capabilities, so there is no spoken turn to try; Pipec confirms the unlock endpoint accepts and
   echoes the two new scopes and that the default scope is unchanged (Task 8).
10. **D-10 — OPEN, Pipec decides at promotion: should `biometric`, `medical` and `location` data
    require `strong` for `read`, `propose` and `correct`?** The draft pins today's behaviour: `basic`
    plus consent, and the face resolver grants consent to any identified owner, so a photograph
    reaches those categories (not `security`, which the generic gate already holds at `strong`).
    The stricter option adds a category set to `PersonalMemoryCapability` (Task 3), raises the
    assurance check in the evaluator (Task 4) and changes the oracle (Task 5), at the cost that those
    reads then need a verified voice or a spent `personal_memory_read` grant. If Pipec chooses it,
    re-rehearse Tasks 3 to 5 before executing.

## Required reading

- `AGENTS.md`, `docs/architecture/implementation-guardrails.md` and `.claude/rules/`.
- [ADR 0019](../../adr/0019-personal-memory-capabilities.md), ADR 0006, ADR 0008, ADR 0009,
  ADR 0015 and ADR 0016.
- `docs/architecture/identity-and-access.md` (*Locked posture and capability scope*, *Fusion rules
  and assurance*) and the capability rows of `docs/architecture/current-state.md`.
- `server/src/server/cognition/{authorization,models,identity,identity_sessions,identity_fusion,owner_authentication}.py`,
  `server/src/server/schemas_auth.py`, `server/src/server/memory/{policy_gated_v4_reader,predicate_registry}.py`
  (read only), `tests/unit/test_household_authorization_policy.py`,
  `tests/unit/test_architecture_guards.py` and `tests/integration/test_owner_unlock_endpoint.py`.

## Permitted files

- Production: `server/src/server/cognition/models.py`, `authorization.py`, `identity.py`,
  `identity_sessions.py`, `owner_authentication.py` and `server/src/server/schemas_auth.py`.
- Tests: new `tests/unit/test_authorization_characterization.py`,
  `test_personal_memory_policy.py`, `test_personal_memory_grants.py`,
  `test_identity_assurance_invariants.py` and `tests/integration/test_personal_memory_audit.py`;
  modified `tests/unit/test_cognitive_models.py`, `test_identity_sessions.py`,
  `test_owner_authentication.py`, `test_biometric_admin_scope_callers.py`,
  `test_architecture_guards.py` and `tests/integration/test_owner_unlock_endpoint.py`.
- Docs (Tasks 8 and 9): ADR 0019, ADR 0015 and ADR 0016 (status lines and one sentence each),
  `docs/adr/README.md`, `docs/architecture/current-state.md`, `identity-and-access.md`,
  `docs/architecture/diagrams/current-state.{json,html}`, `docs/runbooks/operator-manual.md`,
  `docs/roadmap/cognitive-roadmap.md`, `conversational-memory-delivery-map.md`,
  `docs/architecture/README.md`, `docs/plans/README.md`, `docs/plans/open/README.md`,
  `docs/plans/completed/README.md`, a new `docs/evals/0060-personal-memory-capabilities-acceptance.md`
  with `docs/evals/README.md`, and this plan.

No new URL, status code, response field, audio contract, database schema, migration, setting or
dependency. The robot (`robot/src`) and the V4 reader are **not** edited. `docs/roadmap/tabla-tareas.md`
is excluded from git and is updated locally only.

---

## Task 0: Revalidate the baseline

**Files:** this plan's evidence note only. No production change.

- [ ] **Step 1: Branch.** `git checkout main && git pull`, confirm a clean tree, then
  `git checkout -b feat/0060-personal-memory-capabilities`. Record the base SHA (the rehearsal ran at
  `29cfbc0`; if `main` moved, say so and re-check that the diffs below still apply). The diffs
  are applied by hand with the Write and Edit tools (new files whole, existing files hunk by hunk);
  blank context lines in the blocks lost their single leading space in this document, so
  `git apply` needs `--recount --ignore-whitespace` if you prefer it.
- [ ] **Step 2: Baseline.** Run `just gate`; record its outcome and test count (2315 at `29cfbc0`).
  A pre-existing failure is reported, not hidden.
- [ ] **Step 2b: Re-audit the assumptions against the merged code** (queue rule 4). Each command
  must find what this plan names:
  `rg -n "default_visibility" server/src/server/memory/predicate_registry.py` (only the
  `household` default; no predicate overrides it: the V4 reader serves household data only),
  `rg -n "AuthorizationAction\." server/src` (the five new names are absent),
  `rg -n "PROPOSE_MEMORY|COMMIT_MEMORY|DELETE_HOUSEHOLD_DATA|EXPORT_HOUSEHOLD_DATA" server/src`
  (only `cognition/models.py` and `cognition/authorization.py`),
  `rg -n "select_person\(" server/src` (the definition only),
  `rg -n "class OwnerUnlockScope|PERSONAL_PROTECTED_READ" server/src/server/cognition/owner_authentication.py`,
  `rg -n "def issue_for_person|def consume_evidence|def evidence_for" server/src/server/cognition/identity_sessions.py`.
  A difference is reported before any code changes.
- [ ] **Step 3: Pin today's guards.** Run
  `uv run pytest tests/unit/test_architecture_guards.py tests/unit/test_household_authorization_policy.py tests/integration/test_owner_unlock_endpoint.py -q -p no:cacheprovider`
  and record that it passes.

---

## Task 1: Pin the eleven old actions

**Files:**
- Test: new `tests/unit/test_authorization_characterization.py`

**Interfaces:**
- Consumes: `evaluate_authorization`, `AuthorizationRequest` (unchanged).
- Produces: a SHA-256 digest and a readable `(decision, policy_id)` count per old action over a
  fixed grid of 138,006 cases, plus a pinned grid size. It never iterates the enum, so a new member
  cannot change the grid.

- [ ] **Step 1: Write the characterization test** — create the file from this diff (it is green on
  the baseline; the digests were recorded at `29cfbc0`):

```diff
diff --git a/tests/unit/test_authorization_characterization.py b/tests/unit/test_authorization_characterization.py
new file mode 100644
index 0000000..9b1870a
--- /dev/null
+++ b/tests/unit/test_authorization_characterization.py
@@ -0,0 +1,330 @@
+"""Characterization guard: the eleven pre-existing authorization actions never change.
+
+Plan 0060 adds personal-memory actions to the policy. This file pins the exact decision of
+every action that existed before, over a fixed grid, so a new action cannot shift an old one
+by accident. The grid uses literal value tuples (never enum iteration): a new enum member
+therefore cannot silently enter it, and a renamed or removed value fails loudly.
+
+The expected digests and counts below were recorded at main 29cfbc0.
+"""
+
+from collections import Counter
+from datetime import UTC, datetime
+from functools import cache
+from hashlib import sha256
+from itertools import combinations, product
+from uuid import UUID
+
+import pytest
+from server.cognition.authorization import (
+    AuthorizationRequest,
+    ConsentStatus,
+    DataSensitivity,
+    DataVisibility,
+    evaluate_authorization,
+)
+from server.cognition.identity import (
+    ActivePersonContext,
+    ActivePersonStatus,
+    HouseholdRole,
+    IdentityAssurance,
+)
+from server.cognition.models import (
+    AuthorizationAction,
+    Confidence,
+    ConfidenceBasis,
+)
+
+pytestmark = pytest.mark.unit
+
+_REQUESTED_AT = datetime(2026, 8, 12, 12, tzinfo=UTC)
+_CORRELATION_ID = UUID("11111111-1111-1111-1111-111111111111")
+
+_LEGACY_ACTIONS = (
+    "general_conversation",
+    "read_household_data",
+    "execute_household_tool",
+    "propose_memory",
+    "commit_memory",
+    "manage_household_role",
+    "enroll_biometric",
+    "export_household_data",
+    "delete_household_data",
+    "consider_cloud_escalation",
+    "propose_physical_action",
+)
+_ROLES = ("owner", "adult", "child", "guest", "unknown")
+_ASSURANCES = ("none", "basic", "strong")
+_VISIBILITIES = ("public", "household", "adults", "personal", "private", "temporary")
+_SENSITIVITIES = (
+    "normal",
+    "private",
+    "biometric",
+    "medical",
+    "location",
+    "child_data",
+    "security",
+)
+_CONSENTS = ("not_required", "granted", "missing", "revoked")
+_PERSON_ID = 7
+_TARGETS = (None, 7, 8)
+_PASS_B_ROLES = ("owner", "adult", "child")
+_PASS_B_VISIBILITIES = (("personal",), ("household",))
+
+
+def _subsets(values: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
+    """Return every non-empty subset of a literal value tuple, in a stable order."""
+    return tuple(
+        subset for size in range(1, len(values) + 1) for subset in combinations(values, size)
+    )
+
+
+def _actor(
+    *,
+    role: str,
+    status: ActivePersonStatus,
+    assurance: str,
+    person_id: int | None,
+) -> ActivePersonContext:
+    """Build one pre-validated active person without media or database content."""
+    return ActivePersonContext(
+        person_id=person_id,
+        display_name="Ada" if person_id is not None else None,
+        status=status,
+        confidence=Confidence(
+            score=1.0 if person_id is not None else 0.0,
+            basis=ConfidenceBasis.ASSERTED,
+            calibrated=False,
+        ),
+        role=HouseholdRole(role),
+        evidence=(),
+        resolved_at=_REQUESTED_AT,
+        assurance=IdentityAssurance(assurance),
+    )
+
+
+def _identified(role: str, assurance: str) -> ActivePersonContext:
+    """Return an identified person 7 with one role and assurance."""
+    return _actor(
+        role=role,
+        status=ActivePersonStatus.IDENTIFIED,
+        assurance=assurance,
+        person_id=_PERSON_ID,
+    )
+
+
+def _all_actors() -> tuple[ActivePersonContext, ...]:
+    """Return the 18 actors of pass A: 15 identified, one probable owner, two unresolved."""
+    identified = tuple(_identified(role, assurance) for role in _ROLES for assurance in _ASSURANCES)
+    probable_owner = _actor(
+        role="owner",
+        status=ActivePersonStatus.PROBABLE,
+        assurance="none",
+        person_id=_PERSON_ID,
+    )
+    unknown = _actor(
+        role="unknown", status=ActivePersonStatus.UNKNOWN, assurance="none", person_id=None
+    )
+    ambiguous = _actor(
+        role="unknown", status=ActivePersonStatus.AMBIGUOUS, assurance="none", person_id=None
+    )
+    return (*identified, probable_owner, unknown, ambiguous)
+
+
+def _line(
+    action: str,
+    actor: ActivePersonContext,
+    target: int | None,
+    visibility: tuple[str, ...],
+    sensitivity: tuple[str, ...],
+    consent: str,
+) -> str:
+    """Evaluate one case and render it as one canonical, value-only line."""
+    request = AuthorizationRequest.model_construct(
+        actor=actor,
+        action=AuthorizationAction(action),
+        target_person_id=target,
+        visibility=frozenset(DataVisibility(item) for item in visibility),
+        sensitivity=frozenset(DataSensitivity(item) for item in sensitivity),
+        consent=ConsentStatus(consent),
+        correlation_id=_CORRELATION_ID,
+        requested_at=_REQUESTED_AT,
+    )
+    decision = evaluate_authorization(request)
+    left = "|".join(
+        (
+            action,
+            actor.role.value,
+            actor.status.value,
+            actor.assurance.value,
+            str(target),
+            ",".join(sorted(visibility)),
+            ",".join(sorted(sensitivity)),
+            consent,
+        )
+    )
+    right = "|".join(
+        (
+            decision.decision.value,
+            decision.policy_id,
+            ",".join(sorted(decision.data_categories)),
+            decision.reason,
+        )
+    )
+    return f"{left} -> {right}"
+
+
+def _grid_cases(action: str) -> tuple[str, ...]:
+    """Return the canonical lines of both passes for one action."""
+    visibilities = _subsets(_VISIBILITIES)
+    sensitivities = _subsets(_SENSITIVITIES)
+    normal = ("normal",)
+    pass_a = (
+        _line(action, actor, target, visibility, normal, "not_required")
+        for actor, target, visibility in product(_all_actors(), _TARGETS, visibilities)
+    )
+    pass_b_actors = tuple(
+        _identified(role, assurance) for role in _PASS_B_ROLES for assurance in _ASSURANCES
+    )
+    pass_b = (
+        _line(action, actor, _PERSON_ID, visibility, sensitivity, consent)
+        for actor, sensitivity, consent, visibility in product(
+            pass_b_actors, sensitivities, _CONSENTS, _PASS_B_VISIBILITIES
+        )
+    )
+    return (*pass_a, *pass_b)
+
+
+@cache
+def _characterize(action: str) -> tuple[str, dict[tuple[str, str], int], int]:
+    """Return (digest, (decision, policy_id) counts, case count) for one action."""
+    lines = _grid_cases(action)
+    counts: Counter[tuple[str, str]] = Counter()
+    for line in lines:
+        outcome = line.split(" -> ", maxsplit=1)[1].split("|")
+        counts[(outcome[0], outcome[1])] += 1
+    digest = sha256("\n".join(lines).encode("utf-8")).hexdigest()
+    return digest, dict(counts), len(lines)
+
+
+# Recorded at main 29cfbc0.
+_EXPECTED_DIGESTS: dict[str, str] = {
+    "general_conversation": ("45ae2d0642f8fbfbeb5ea7a2f4cd1e1b5a5487a5ab01e97a5473d52f6461c638"),
+    "read_household_data": ("dd378d2f1c75fa7ca09aca3a137fb09aa11d7f35f55ca5d8c9cea9f2b05523c6"),
+    "execute_household_tool": ("0b9de2733707a882238b887d99624f5306c0e1394ad7de8b524925b15b9fa7f7"),
+    "propose_memory": ("1a66187ddf8212a1f5a08bae175b8da2236cfb6e59b96564a62ac8acd9743743"),
+    "commit_memory": ("56b0f98d4ae17bb5b5d7e68b266df3f752bf429ff193d950fc88253c18c3407a"),
+    "manage_household_role": ("10e8e49deca66537dad7ebc4a05d2181a1e738eae9c16855449ced9ad90176eb"),
+    "enroll_biometric": ("fea4b8d850f64302c906f7f7cdb727c2259ec2566c087c67f6c4b9b2bd234902"),
+    "export_household_data": ("b585ee06d63c0f07d02b5ad38c97ce087ed8d17062870845dcbd55e8941ff6fe"),
+    "delete_household_data": ("79addcdc97888ca7da9d5fa2957ef131eeffbf5a4e212760293987628a957557"),
+    "consider_cloud_escalation": (
+        "aa691a4c88c764ade6254529d2608753e7e44f12f1da59217512c58e9f44db30"
+    ),
+    "propose_physical_action": ("1c89aadbb5b591fc19f2fd63c4a44157f4140f9e25acbd811ae6b06384c4e4a7"),
+}
+_EXPECTED_COUNTS: dict[str, dict[tuple[str, str], int]] = {
+    "general_conversation": {
+        ("allowed", "p0.5.general-conversation"): 54,
+        ("denied", "p0.5.general-conversation-unclassified"): 12492,
+    },
+    "read_household_data": {
+        ("allowed", "p0.5.adult-household"): 45,
+        ("allowed", "p0.5.household-public"): 18,
+        ("allowed", "p0.5.own-normal-personal"): 48,
+        ("allowed", "p0.5.owner-household"): 63,
+        ("allowed", "p0.5.owner-sensitive-consent"): 488,
+        ("denied", "p0.5.assurance-required"): 3072,
+        ("denied", "p0.5.consent-required"): 4392,
+        ("denied", "p0.5.identity-unresolved"): 1134,
+        ("denied", "p0.5.protected-default-deny"): 2301,
+        ("requires_confirmation", "p0.5.child-public-confirmation"): 9,
+        ("requires_confirmation", "p0.5.sensitive-confirmation"): 976,
+    },
+    "execute_household_tool": {
+        ("allowed", "p0.5.adult-household"): 45,
+        ("allowed", "p0.5.household-public"): 18,
+        ("allowed", "p0.5.own-normal-personal"): 48,
+        ("allowed", "p0.5.owner-household"): 63,
+        ("allowed", "p0.5.owner-sensitive-consent"): 488,
+        ("denied", "p0.5.assurance-required"): 3072,
+        ("denied", "p0.5.consent-required"): 4392,
+        ("denied", "p0.5.identity-unresolved"): 1134,
+        ("denied", "p0.5.protected-default-deny"): 2301,
+        ("requires_confirmation", "p0.5.child-public-confirmation"): 9,
+        ("requires_confirmation", "p0.5.sensitive-confirmation"): 976,
+    },
+    "propose_memory": {
+        ("allowed", "p0.5.owner-memory-proposal"): 2591,
+        ("denied", "p0.5.assurance-required"): 3072,
+        ("denied", "p0.5.default-deny"): 567,
+        ("denied", "p0.5.identity-unresolved"): 1134,
+        ("requires_confirmation", "p0.5.memory-proposal-confirmation"): 5182,
+    },
+    "commit_memory": {
+        ("allowed", "p0.5.owner-administration"): 2591,
+        ("denied", "p0.5.assurance-required"): 3072,
+        ("denied", "p0.5.default-deny"): 5749,
+        ("denied", "p0.5.identity-unresolved"): 1134,
+    },
+    "manage_household_role": {
+        ("allowed", "p0.5.owner-administration"): 2591,
+        ("denied", "p0.5.assurance-required"): 3072,
+        ("denied", "p0.5.default-deny"): 5749,
+        ("denied", "p0.5.identity-unresolved"): 1134,
+    },
+    "enroll_biometric": {
+        ("allowed", "p0.5.owner-consented-sensitive-action"): 506,
+        ("denied", "p0.5.assurance-required"): 3072,
+        ("denied", "p0.5.consent-required"): 2085,
+        ("denied", "p0.5.default-deny"): 5749,
+        ("denied", "p0.5.identity-unresolved"): 1134,
+    },
+    "export_household_data": {
+        ("allowed", "p0.5.owner-administration"): 2591,
+        ("denied", "p0.5.assurance-required"): 3072,
+        ("denied", "p0.5.default-deny"): 5749,
+        ("denied", "p0.5.identity-unresolved"): 1134,
+    },
+    "delete_household_data": {
+        ("allowed", "p0.5.owner-administration"): 2591,
+        ("denied", "p0.5.assurance-required"): 3072,
+        ("denied", "p0.5.default-deny"): 5749,
+        ("denied", "p0.5.identity-unresolved"): 1134,
+    },
+    "consider_cloud_escalation": {
+        ("allowed", "p0.5.owner-consented-sensitive-action"): 506,
+        ("denied", "p0.5.assurance-required"): 3072,
+        ("denied", "p0.5.consent-required"): 2085,
+        ("denied", "p0.5.default-deny"): 5749,
+        ("denied", "p0.5.identity-unresolved"): 1134,
+    },
+    "propose_physical_action": {
+        ("allowed", "p0.5.physical-action-proposal"): 5182,
+        ("denied", "p0.5.assurance-required"): 3072,
+        ("denied", "p0.5.default-deny"): 3158,
+        ("denied", "p0.5.identity-unresolved"): 1134,
+    },
+}
+_EXPECTED_GRID_SIZE = 138006
+
+
+@pytest.mark.parametrize("action", _LEGACY_ACTIONS)
+def test_legacy_action_decisions_are_unchanged(action: str) -> None:
+    """Every decision, policy id, category set and reason of an old action is pinned."""
+    digest, _, _ = _characterize(action)
+
+    assert digest == _EXPECTED_DIGESTS[action]
+
+
+@pytest.mark.parametrize("action", _LEGACY_ACTIONS)
+def test_legacy_decision_counts_are_unchanged(action: str) -> None:
+    """The (decision, policy id) histogram stays readable when the digest above fails."""
+    _, counts, _ = _characterize(action)
+
+    assert counts == _EXPECTED_COUNTS[action]
+
+
+def test_characterization_grid_size_is_pinned() -> None:
+    """A silently shrunken grid would weaken both pins above."""
+    assert sum(_characterize(action)[2] for action in _LEGACY_ACTIONS) == _EXPECTED_GRID_SIZE
```

- [ ] **Step 2: Run it on the unchanged code.**
  `uv run pytest tests/unit/test_authorization_characterization.py -q -p no:cacheprovider`
  Expected: **23 passed** (about 2 to 8 s). If a digest differs, `main` is not the baseline of the
  rehearsal: stop and report which action moved before going on.
- [ ] **Step 3: Prove it bites.** Temporarily change `{HouseholdRole.OWNER, HouseholdRole.ADULT}`
  to `{HouseholdRole.OWNER}` in `_evaluate_physical_action_proposal` (that one set literal only);
  the rehearsal saw 2 failures (the `propose_physical_action` digest and counts tests).
  Revert it.
- [ ] **Step 4: Lint and commit.**
  `uv run ruff check tests/unit/test_authorization_characterization.py` and
  `uv run ruff format --check tests/unit/test_authorization_characterization.py`, then commit
  `test(server): pin the old authorization decisions (plan 0060)`.

---

## Task 2: Five new actions

**Files:**
- Modify: `server/src/server/cognition/models.py`
- Test: `tests/unit/test_cognitive_models.py`

**Interfaces:**
- Produces: `AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY`, `PROPOSE_PERSONAL_MEMORY`,
  `CONFIRM_PERSONAL_MEMORY`, `CORRECT_PERSONAL_MEMORY`, `FORGET_PERSONAL_MEMORY`, appended in this
  order after `PROPOSE_PHYSICAL_ACTION`.

- [ ] **Step 1: Write the failing test** — extend the enum snapshot:

```diff
diff --git a/tests/unit/test_cognitive_models.py b/tests/unit/test_cognitive_models.py
index 6e1dcb8..0673bf8 100644
--- a/tests/unit/test_cognitive_models.py
+++ b/tests/unit/test_cognitive_models.py
@@ -142,6 +142,11 @@ def _event_values() -> dict[str, object]:
                 "delete_household_data",
                 "consider_cloud_escalation",
                 "propose_physical_action",
+                "read_personal_conversation_memory",
+                "propose_personal_memory",
+                "confirm_personal_memory",
+                "correct_personal_memory",
+                "forget_personal_memory",
             ],
         ),
         (ObservationModality, ["text", "audio", "visual", "sensor", "system"]),
```

- [ ] **Step 2: Run it to see it fail.**
  `uv run pytest tests/unit/test_cognitive_models.py -q -p no:cacheprovider`
  Expected RED: the snapshot assertion fails with `Right contains 5 more items, first extra item:
  'read_personal_conversation_memory'`.
- [ ] **Step 3: Implement.**

```diff
diff --git a/server/src/server/cognition/models.py b/server/src/server/cognition/models.py
index ee9e1ba..ead7752 100644
--- a/server/src/server/cognition/models.py
+++ b/server/src/server/cognition/models.py
@@ -70,6 +70,11 @@ class AuthorizationAction(str, _Enum):  # noqa: UP042
     DELETE_HOUSEHOLD_DATA = "delete_household_data"
     CONSIDER_CLOUD_ESCALATION = "consider_cloud_escalation"
     PROPOSE_PHYSICAL_ACTION = "propose_physical_action"
+    READ_PERSONAL_CONVERSATION_MEMORY = "read_personal_conversation_memory"
+    PROPOSE_PERSONAL_MEMORY = "propose_personal_memory"
+    CONFIRM_PERSONAL_MEMORY = "confirm_personal_memory"
+    CORRECT_PERSONAL_MEMORY = "correct_personal_memory"
+    FORGET_PERSONAL_MEMORY = "forget_personal_memory"


 class ObservationModality(str, _Enum):  # noqa: UP042
```

- [ ] **Step 4: Run, lint, commit.** `uv run pytest tests/unit/test_cognitive_models.py
  tests/unit/test_authorization_characterization.py -q -p no:cacheprovider` passes (the new members
  fall through to the existing default deny, so the characterization is unchanged); `ruff check` and
  `ruff format --check` over both test files and `models.py`; commit
  `feat(server): add the five personal-memory actions (plan 0060)`.

---

## Task 3: The capability table

**Files:**
- Modify: `server/src/server/cognition/authorization.py`
- Test: new `tests/unit/test_personal_memory_policy.py`

**Interfaces:**
- Consumes: the five actions of Task 2.
- Produces: `ASSURANCE_RANK` (`none` 0, `basic` 1, `strong` 2),
  `PersonalMemoryCapability(min_assurance, consent_applies, requires_unlock, unlock_scope,
  visibilities)` and the read-only `PERSONAL_MEMORY_CAPABILITIES`, exported in `__all__`.

- [ ] **Step 1: Write the failing tests** (one literal-table equality test, drift tests against
  `DataSensitivity`, `HIGH_ASSURANCE_CATEGORIES` and the sensitive set, the rank test and a read-only
  test; RED is an `ImportError`):

```diff
diff --git a/tests/unit/test_personal_memory_policy.py b/tests/unit/test_personal_memory_policy.py
new file mode 100644
index 0000000..11a3dab
--- /dev/null
+++ b/tests/unit/test_personal_memory_policy.py
@@ -0,0 +1,160 @@
+"""Unit tests for the personal-memory capabilities of the authorization policy (ADR 0019)."""
+
+from typing import TYPE_CHECKING, cast
+
+import pytest
+from server.cognition import authorization
+from server.cognition.authorization import (
+    ASSURANCE_RANK,
+    HIGH_ASSURANCE_CATEGORIES,
+    PERSONAL_MEMORY_CAPABILITIES,
+    DataSensitivity,
+    DataVisibility,
+    PersonalMemoryCapability,
+)
+from server.cognition.identity import IdentityAssurance
+from server.cognition.models import AuthorizationAction
+
+if TYPE_CHECKING:
+    from collections.abc import MutableMapping
+
+pytestmark = pytest.mark.unit
+
+_LEGACY_ACTIONS = frozenset(
+    {
+        "general_conversation",
+        "read_household_data",
+        "execute_household_tool",
+        "propose_memory",
+        "commit_memory",
+        "manage_household_role",
+        "enroll_biometric",
+        "export_household_data",
+        "delete_household_data",
+        "consider_cloud_escalation",
+        "propose_physical_action",
+    }
+)
+_READ = AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY
+_PROPOSE = AuthorizationAction.PROPOSE_PERSONAL_MEMORY
+_CONFIRM = AuthorizationAction.CONFIRM_PERSONAL_MEMORY
+_CORRECT = AuthorizationAction.CORRECT_PERSONAL_MEMORY
+_FORGET = AuthorizationAction.FORGET_PERSONAL_MEMORY
+_PERSONAL_ONLY = frozenset({DataVisibility.PERSONAL})
+_FORGET_VISIBILITIES = frozenset(
+    {DataVisibility.PERSONAL, DataVisibility.PRIVATE, DataVisibility.TEMPORARY}
+)
+_SENSITIVE_LITERAL = frozenset(
+    {
+        DataSensitivity.BIOMETRIC,
+        DataSensitivity.MEDICAL,
+        DataSensitivity.LOCATION,
+        DataSensitivity.CHILD_DATA,
+        DataSensitivity.SECURITY,
+    }
+)
+_ORDINARY_LITERAL = frozenset({DataSensitivity.NORMAL, DataSensitivity.PRIVATE})
+
+# ADR 0019 §3, restated as literals. Owner amendment 2026-10-08: confirm needs STRONG.
+_EXPECTED_TABLE = {
+    _READ: PersonalMemoryCapability(
+        min_assurance=IdentityAssurance.BASIC,
+        consent_applies=True,
+        requires_unlock=False,
+        unlock_scope="personal_memory_read",
+        visibilities=_PERSONAL_ONLY,
+    ),
+    _PROPOSE: PersonalMemoryCapability(
+        min_assurance=IdentityAssurance.BASIC,
+        consent_applies=True,
+        requires_unlock=False,
+        unlock_scope=None,
+        visibilities=_PERSONAL_ONLY,
+    ),
+    _CONFIRM: PersonalMemoryCapability(
+        min_assurance=IdentityAssurance.STRONG,
+        consent_applies=True,
+        requires_unlock=False,
+        unlock_scope=None,
+        visibilities=_PERSONAL_ONLY,
+    ),
+    _CORRECT: PersonalMemoryCapability(
+        min_assurance=IdentityAssurance.BASIC,
+        consent_applies=True,
+        requires_unlock=False,
+        unlock_scope=None,
+        visibilities=_PERSONAL_ONLY,
+    ),
+    _FORGET: PersonalMemoryCapability(
+        min_assurance=IdentityAssurance.STRONG,
+        consent_applies=False,
+        requires_unlock=True,
+        unlock_scope="personal_memory_forget",
+        visibilities=_FORGET_VISIBILITIES,
+    ),
+}
+
+
+# --- structure of the capability table --------------------------------------
+
+
+def test_the_capability_table_is_exactly_the_one_in_adr_0019() -> None:
+    """One literal table: five new actions, nothing else, no capability accepts no assurance."""
+    assert dict(PERSONAL_MEMORY_CAPABILITIES) == _EXPECTED_TABLE
+    for capability in PERSONAL_MEMORY_CAPABILITIES.values():
+        assert capability.min_assurance is not IdentityAssurance.NONE
+        assert capability.visibilities
+
+
+def test_every_action_is_either_legacy_or_a_personal_memory_capability() -> None:
+    all_values = {action.value for action in AuthorizationAction}
+    new_values = {action.value for action in PERSONAL_MEMORY_CAPABILITIES}
+
+    assert all_values == _LEGACY_ACTIONS | new_values
+    assert not _LEGACY_ACTIONS & new_values
+
+
+def test_requiring_an_unlock_implies_naming_the_scope_it_must_carry() -> None:
+    for capability in PERSONAL_MEMORY_CAPABILITIES.values():
+        assert not capability.requires_unlock or capability.unlock_scope is not None
+
+
+def test_every_sensitivity_is_ordinary_or_sensitive_never_both_nor_neither() -> None:
+    """Adding a DataSensitivity member fails here until it is classified."""
+    sensitive = authorization._SENSITIVE_CATEGORIES
+
+    for category in DataSensitivity:
+        assert (category in _ORDINARY_LITERAL) != (category in sensitive), category.value
+    assert sensitive == _SENSITIVE_LITERAL
+    assert _ORDINARY_LITERAL | sensitive == set(DataSensitivity)
+
+
+def test_high_assurance_categories_are_sensitive_categories() -> None:
+    assert HIGH_ASSURANCE_CATEGORIES <= authorization._SENSITIVE_CATEGORIES
+    assert set(HIGH_ASSURANCE_CATEGORIES) == {DataSensitivity.SECURITY}
+
+
+def test_assurance_rank_is_total_and_not_lexicographic() -> None:
+    """`IdentityAssurance` is a str enum: comparing members orders them alphabetically."""
+    assert IdentityAssurance.BASIC < IdentityAssurance.NONE  # the trap, documented
+    assert set(ASSURANCE_RANK) == set(IdentityAssurance)
+    assert (
+        ASSURANCE_RANK[IdentityAssurance.NONE]
+        < ASSURANCE_RANK[IdentityAssurance.BASIC]
+        < ASSURANCE_RANK[IdentityAssurance.STRONG]
+    )
+
+
+def test_the_tables_are_read_only() -> None:
+    capabilities = cast(
+        "MutableMapping[AuthorizationAction, PersonalMemoryCapability]",
+        PERSONAL_MEMORY_CAPABILITIES,
+    )
+    ranks = cast("MutableMapping[IdentityAssurance, int]", ASSURANCE_RANK)
+
+    with pytest.raises(TypeError):
+        capabilities[_FORGET] = PERSONAL_MEMORY_CAPABILITIES[_READ]
+    with pytest.raises(TypeError):
+        ranks[IdentityAssurance.NONE] = 9
+    with pytest.raises(TypeError):
+        del capabilities[_READ]
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_personal_memory_policy.py -q -p no:cacheprovider`
  Expected RED: `ImportError: cannot import name 'ASSURANCE_RANK' from
  'server.cognition.authorization'`.
- [ ] **Step 3: Implement.** The table is where each capability declares its minimum assurance, its
  consent rule, its PIN route and its visibilities; there is no per-category assurance table (the
  `SECURITY` rule is the existing generic gate):

```diff
diff --git a/server/src/server/cognition/authorization.py b/server/src/server/cognition/authorization.py
index bbfe7ff..e62d28a 100644
--- a/server/src/server/cognition/authorization.py
+++ b/server/src/server/cognition/authorization.py
@@ -1,7 +1,10 @@
 """Pure, fail-closed authorization contracts and household policy."""

+from collections.abc import Mapping
+from dataclasses import dataclass
 from datetime import datetime
 from enum import StrEnum
+from types import MappingProxyType
 from typing import Annotated
 from uuid import UUID

@@ -24,11 +27,14 @@ _StrictInteger = Annotated[int, Field(strict=True)]
 _StrictUUID = Annotated[UUID, Field(strict=True)]

 __all__ = [
+    "ASSURANCE_RANK",
     "HIGH_ASSURANCE_CATEGORIES",
+    "PERSONAL_MEMORY_CAPABILITIES",
     "AuthorizationRequest",
     "ConsentStatus",
     "DataSensitivity",
     "DataVisibility",
+    "PersonalMemoryCapability",
     "evaluate_authorization",
 ]

@@ -95,6 +101,85 @@ _SENSITIVE_CATEGORIES = frozenset(
 # §3). Only SECURITY today; others join when a capability declares them.
 HIGH_ASSURANCE_CATEGORIES = frozenset({DataSensitivity.SECURITY})

+# `IdentityAssurance` is a str enum, so `<` on its members is alphabetical (`basic` < `none`).
+# Compare assurance only through this rank (ADR 0019 §3).
+ASSURANCE_RANK: Mapping[IdentityAssurance, int] = MappingProxyType(
+    {
+        IdentityAssurance.NONE: 0,
+        IdentityAssurance.BASIC: 1,
+        IdentityAssurance.STRONG: 2,
+    }
+)
+
+
+@dataclass(frozen=True)
+class PersonalMemoryCapability:
+    """What one personal-memory action demands of the actor and the data (ADR 0019 §3).
+
+    Attributes:
+        min_assurance: Lowest identity assurance that may exercise the capability.
+        consent_applies: Whether sensitive categories also need granted consent.
+        requires_unlock: Whether an owner PIN grant spent for this operation is mandatory.
+        unlock_scope: The one owner-unlock scope a PIN grant may carry, or None when a
+            PIN grant never counts for this capability.
+        visibilities: The only data visibilities the capability may touch.
+    """
+
+    min_assurance: IdentityAssurance
+    consent_applies: bool
+    requires_unlock: bool
+    unlock_scope: str | None
+    visibilities: frozenset[DataVisibility]
+
+
+_PERSONAL_ONLY = frozenset({DataVisibility.PERSONAL})
+
+# Scopes are plain strings: importing `OwnerUnlockScope` would create an import cycle with
+# `owner_authentication`; a drift test pins them to its members.
+PERSONAL_MEMORY_CAPABILITIES: Mapping[AuthorizationAction, PersonalMemoryCapability] = (
+    MappingProxyType(
+        {
+            AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY: PersonalMemoryCapability(
+                min_assurance=IdentityAssurance.BASIC,
+                consent_applies=True,
+                requires_unlock=False,
+                unlock_scope="personal_memory_read",
+                visibilities=_PERSONAL_ONLY,
+            ),
+            AuthorizationAction.PROPOSE_PERSONAL_MEMORY: PersonalMemoryCapability(
+                min_assurance=IdentityAssurance.BASIC,
+                consent_applies=True,
+                requires_unlock=False,
+                unlock_scope=None,
+                visibilities=_PERSONAL_ONLY,
+            ),
+            AuthorizationAction.CONFIRM_PERSONAL_MEMORY: PersonalMemoryCapability(
+                min_assurance=IdentityAssurance.STRONG,
+                consent_applies=True,
+                requires_unlock=False,
+                unlock_scope=None,
+                visibilities=_PERSONAL_ONLY,
+            ),
+            AuthorizationAction.CORRECT_PERSONAL_MEMORY: PersonalMemoryCapability(
+                min_assurance=IdentityAssurance.BASIC,
+                consent_applies=True,
+                requires_unlock=False,
+                unlock_scope=None,
+                visibilities=_PERSONAL_ONLY,
+            ),
+            AuthorizationAction.FORGET_PERSONAL_MEMORY: PersonalMemoryCapability(
+                min_assurance=IdentityAssurance.STRONG,
+                consent_applies=False,
+                requires_unlock=True,
+                unlock_scope="personal_memory_forget",
+                visibilities=frozenset(
+                    {DataVisibility.PERSONAL, DataVisibility.PRIVATE, DataVisibility.TEMPORARY}
+                ),
+            ),
+        }
+    )
+)
+

 def _lacks_required_assurance(request: AuthorizationRequest) -> bool:
     """Return whether a reserved request is made with less than `strong` assurance."""
```

- [ ] **Step 4: Run, lint, commit.** `uv run pytest tests/unit/test_personal_memory_policy.py
  tests/unit/test_authorization_characterization.py -q -p no:cacheprovider` (7 new tests pass);
  `ruff check` and `ruff format --check` over the touched paths; `uv run mypy server/src`; commit
  `feat(server): declare personal-memory capabilities (plan 0060)`.

---

## Task 4: The evaluator

**Files:**
- Modify: `server/src/server/cognition/authorization.py`
- Test: `tests/unit/test_personal_memory_policy.py`, new `tests/integration/test_personal_memory_audit.py`

**Interfaces:**
- Consumes: `PERSONAL_MEMORY_CAPABILITIES`, `ASSURANCE_RANK`, the existing `_has_sensitive_data`,
  `_decision` and the generic gates in `evaluate_authorization`.
- Produces: the dispatch in `_evaluate_resolved_request` and `_evaluate_personal_memory`, with
  policy ids `cm1.personal-memory.{owner-only,own-data-only,assurance-required,grant-scope,
  consent-required,allowed}`. The old dispatcher is renamed `_evaluate_legacy_request`, unchanged.
  In this task the grant rule is not there yet (Task 6 adds it).

- [ ] **Step 1: Write the failing tests** (cases per action, precedence, consent, visibilities,
  fail-closed, and a round trip through the audit table against a temporary SQLite database):

```diff
diff --git a/tests/integration/test_personal_memory_audit.py b/tests/integration/test_personal_memory_audit.py
new file mode 100644
index 0000000..ff942c3
--- /dev/null
+++ b/tests/integration/test_personal_memory_audit.py
@@ -0,0 +1,102 @@
+"""A personal-memory decision is appended to the audit table unchanged (ADR 0019 §6)."""
+
+from collections.abc import AsyncIterator
+from datetime import UTC, datetime
+from pathlib import Path
+from uuid import UUID
+
+import pytest
+from server.cognition.authorization import (
+    AuthorizationRequest,
+    ConsentStatus,
+    DataSensitivity,
+    DataVisibility,
+    evaluate_authorization,
+)
+from server.cognition.identity import (
+    ActivePersonContext,
+    ActivePersonStatus,
+    HouseholdRole,
+    IdentityAssurance,
+)
+from server.cognition.models import (
+    AuthorizationAction,
+    AuthorizationStatus,
+    Confidence,
+    ConfidenceBasis,
+)
+from server.memory.declarative import upsert_entity
+from server.memory.household_authorization import record_authorization_decision
+from server.settings import settings
+
+from server import db
+
+_AT = datetime(2026, 10, 8, 12, tzinfo=UTC)
+_CORRELATION_ID = UUID("44444444-4444-4444-4444-444444444444")
+
+
+@pytest.fixture
+async def audit_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
+    """Open a fresh temporary database with every migration applied."""
+    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "personal-memory-audit.db")
+    db._conn = None
+    await db.open_db()
+    await db.run_migrations()
+    yield
+    await db.close_db()
+    db._conn = None
+
+
+@pytest.mark.integration
+@pytest.mark.parametrize(
+    "action",
+    [
+        AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY,
+        AuthorizationAction.PROPOSE_PERSONAL_MEMORY,
+        AuthorizationAction.CONFIRM_PERSONAL_MEMORY,
+        AuthorizationAction.CORRECT_PERSONAL_MEMORY,
+        AuthorizationAction.FORGET_PERSONAL_MEMORY,
+    ],
+)
+async def test_each_new_action_is_recorded_with_its_value_and_a_cm1_policy_id(
+    audit_db: None, action: AuthorizationAction
+) -> None:
+    """The audit `action` column is free text: the new values need no migration."""
+    owner_id = await upsert_entity(name="Ada", type="person")
+    owner = ActivePersonContext(
+        person_id=owner_id,
+        display_name="Ada",
+        status=ActivePersonStatus.IDENTIFIED,
+        confidence=Confidence(score=1.0, basis=ConfidenceBasis.ASSERTED, calibrated=False),
+        role=HouseholdRole.OWNER,
+        evidence=(),
+        resolved_at=_AT,
+        assurance=IdentityAssurance.STRONG,
+    )
+    request = AuthorizationRequest(
+        actor=owner,
+        action=action,
+        target_person_id=owner_id,
+        visibility=frozenset({DataVisibility.PERSONAL}),
+        sensitivity=frozenset({DataSensitivity.MEDICAL}),
+        consent=ConsentStatus.GRANTED,
+        correlation_id=_CORRELATION_ID,
+        requested_at=_AT,
+    )
+    decision = evaluate_authorization(request)
+
+    await record_authorization_decision(request, decision)
+
+    cursor = await db.get_conn().execute(
+        "SELECT actor_entity_id, target_entity_id, action, data_categories, decision, policy_id "
+        "FROM authorization_audit_events"
+    )
+    rows = list(await cursor.fetchall())
+    await cursor.close()
+    assert len(rows) == 1
+    actor_id, target_id, stored_action, categories, stored_decision, policy_id = rows[0]
+    assert (actor_id, target_id) == (owner_id, owner_id)
+    assert stored_action == action.value
+    assert categories == "medical,personal"
+    assert stored_decision == AuthorizationStatus.ALLOWED.value
+    assert policy_id == "cm1.personal-memory.allowed"
diff --git a/tests/unit/test_personal_memory_policy.py b/tests/unit/test_personal_memory_policy.py
index 11a3dab..56c5d40 100644
--- a/tests/unit/test_personal_memory_policy.py
+++ b/tests/unit/test_personal_memory_policy.py
@@ -1,6 +1,9 @@
 """Unit tests for the personal-memory capabilities of the authorization policy (ADR 0019)."""

+from datetime import UTC, datetime
+from types import MappingProxyType
 from typing import TYPE_CHECKING, cast
+from uuid import UUID

 import pytest
 from server.cognition import authorization
@@ -8,12 +11,26 @@ from server.cognition.authorization import (
     ASSURANCE_RANK,
     HIGH_ASSURANCE_CATEGORIES,
     PERSONAL_MEMORY_CAPABILITIES,
+    AuthorizationRequest,
+    ConsentStatus,
     DataSensitivity,
     DataVisibility,
     PersonalMemoryCapability,
+    evaluate_authorization,
+)
+from server.cognition.identity import (
+    ActivePersonContext,
+    ActivePersonStatus,
+    HouseholdRole,
+    IdentityAssurance,
+)
+from server.cognition.models import (
+    AuthorizationAction,
+    AuthorizationDecision,
+    AuthorizationStatus,
+    Confidence,
+    ConfidenceBasis,
 )
-from server.cognition.identity import IdentityAssurance
-from server.cognition.models import AuthorizationAction

 if TYPE_CHECKING:
     from collections.abc import MutableMapping
@@ -158,3 +175,309 @@ def test_the_tables_are_read_only() -> None:
         ranks[IdentityAssurance.NONE] = 9
     with pytest.raises(TypeError):
         del capabilities[_READ]
+
+
+# --- evaluation (ADR 0019 §2, §3 and §5) -------------------------------------
+
+_REQUESTED_AT = datetime(2026, 10, 8, 12, tzinfo=UTC)
+_CORRELATION_ID = UUID("33333333-3333-3333-3333-333333333333")
+_OWNER_ID = 7
+_OTHER_ID = 8
+_NORMAL = frozenset({DataSensitivity.NORMAL})
+_MEDICAL = frozenset({DataSensitivity.MEDICAL})
+_SECURITY = frozenset({DataSensitivity.SECURITY})
+_NEW_ACTIONS = (_READ, _PROPOSE, _CONFIRM, _CORRECT, _FORGET)
+_NON_FORGET = (_READ, _PROPOSE, _CONFIRM, _CORRECT)
+_BASIC_ACTIONS = (_READ, _PROPOSE, _CORRECT)
+_STRONG_ACTIONS = (_CONFIRM, _FORGET)
+_ALL_CONSENTS = (
+    ConsentStatus.NOT_REQUIRED,
+    ConsentStatus.MISSING,
+    ConsentStatus.REVOKED,
+    ConsentStatus.GRANTED,
+)
+
+_ALLOWED = AuthorizationStatus.ALLOWED
+_DENIED = AuthorizationStatus.DENIED
+_ALLOWED_ID = "cm1.personal-memory.allowed"
+_OWNER_ONLY_ID = "cm1.personal-memory.owner-only"
+_OWN_DATA_ID = "cm1.personal-memory.own-data-only"
+_ASSURANCE_ID = "cm1.personal-memory.assurance-required"
+_CONSENT_ID = "cm1.personal-memory.consent-required"
+_GLOBAL_ASSURANCE_ID = "p0.5.assurance-required"
+_UNRESOLVED_ID = "p0.5.identity-unresolved"
+_DEFAULT_DENY_ID = "p0.5.default-deny"
+
+
+def _visibility_id(visibility: frozenset[DataVisibility]) -> str:
+    """Render a visibility set as a stable pytest id."""
+    return "+".join(sorted(item.value for item in visibility))
+
+
+def _actor(
+    *,
+    role: HouseholdRole = HouseholdRole.OWNER,
+    assurance: IdentityAssurance = IdentityAssurance.BASIC,
+    status: ActivePersonStatus = ActivePersonStatus.IDENTIFIED,
+    person_id: int | None = _OWNER_ID,
+) -> ActivePersonContext:
+    """Build one active person for a pure personal-memory case (no media, no database)."""
+    return ActivePersonContext(
+        person_id=person_id,
+        display_name="Ada" if person_id is not None else None,
+        status=status,
+        confidence=Confidence(
+            score=1.0 if person_id is not None else 0.0,
+            basis=ConfidenceBasis.ASSERTED,
+            calibrated=False,
+        ),
+        role=role,
+        evidence=(),
+        resolved_at=_REQUESTED_AT,
+        assurance=assurance,
+    )
+
+
+def _strong_actor_for(action: AuthorizationAction) -> ActivePersonContext:
+    """A hand-built strong owner (no evidence) who can exercise `action`."""
+    del action
+    return _actor(assurance=IdentityAssurance.STRONG)
+
+
+def _decide(
+    action: AuthorizationAction,
+    *,
+    actor: ActivePersonContext | None = None,
+    target: int | None = _OWNER_ID,
+    visibility: frozenset[DataVisibility] = _PERSONAL_ONLY,
+    sensitivity: frozenset[DataSensitivity] = _NORMAL,
+    consent: ConsentStatus = ConsentStatus.NOT_REQUIRED,
+) -> AuthorizationDecision:
+    """Evaluate the owner's own ordinary personal data unless a keyword overrides it."""
+    return evaluate_authorization(
+        AuthorizationRequest(
+            actor=actor if actor is not None else _actor(),
+            action=action,
+            target_person_id=target,
+            visibility=visibility,
+            sensitivity=sensitivity,
+            consent=consent,
+            correlation_id=_CORRELATION_ID,
+            requested_at=_REQUESTED_AT,
+        )
+    )
+
+
+def _assert_outcome(
+    decision: AuthorizationDecision, status: AuthorizationStatus, policy_id: str
+) -> None:
+    """Assert a decision's fully qualified policy id, then its status."""
+    assert decision.policy_id == policy_id
+    assert decision.decision is status
+
+
+_ASSURANCE_CASES = [
+    *((action, IdentityAssurance.STRONG, _ALLOWED_ID) for action in _NEW_ACTIONS),
+    *((action, IdentityAssurance.BASIC, _ALLOWED_ID) for action in _BASIC_ACTIONS),
+    *((action, IdentityAssurance.BASIC, _ASSURANCE_ID) for action in _STRONG_ACTIONS),
+    *((action, IdentityAssurance.NONE, _ASSURANCE_ID) for action in _NEW_ACTIONS),
+]
+
+
+@pytest.mark.parametrize("action, assurance, policy_id", _ASSURANCE_CASES)
+def test_assurance_is_compared_by_rank_against_each_actions_minimum(
+    action: AuthorizationAction, assurance: IdentityAssurance, policy_id: str
+) -> None:
+    """Read, propose and correct need `basic`; confirm and forget need `strong`; none never."""
+    decision = _decide(action, actor=_actor(assurance=assurance))
+
+    assert decision.policy_id == policy_id
+    assert decision.action is action
+
+
+@pytest.mark.parametrize("assurance", [IdentityAssurance.NONE, IdentityAssurance.BASIC])
+@pytest.mark.parametrize("action", _NEW_ACTIONS)
+def test_security_data_below_strong_is_stopped_by_the_existing_global_gate(
+    action: AuthorizationAction, assurance: IdentityAssurance
+) -> None:
+    decision = _decide(
+        action,
+        actor=_actor(assurance=assurance),
+        sensitivity=_SECURITY,
+        consent=ConsentStatus.GRANTED,
+    )
+
+    _assert_outcome(decision, _DENIED, _GLOBAL_ASSURANCE_ID)
+
+
+@pytest.mark.parametrize("action", _NON_FORGET)
+def test_sensitive_data_needs_granted_consent(action: AuthorizationAction) -> None:
+    """One example per outcome; the 127-subset matrix below covers every category."""
+    strong = _strong_actor_for(action)
+
+    for consent in (ConsentStatus.NOT_REQUIRED, ConsentStatus.MISSING, ConsentStatus.REVOKED):
+        _assert_outcome(
+            _decide(action, actor=strong, sensitivity=_MEDICAL, consent=consent),
+            _DENIED,
+            _CONSENT_ID,
+        )
+    granted = _decide(action, actor=strong, sensitivity=_MEDICAL, consent=ConsentStatus.GRANTED)
+    _assert_outcome(granted, _ALLOWED, _ALLOWED_ID)
+
+
+def test_forget_ignores_consent_even_when_it_was_revoked() -> None:
+    """Withdrawing consent is a reason to erase: it must never block erasure."""
+    outcomes = {
+        consent: _decide(
+            _FORGET,
+            actor=_strong_actor_for(_FORGET),
+            sensitivity=_SECURITY,
+            consent=consent,
+        )
+        for consent in _ALL_CONSENTS
+    }
+
+    for decision in outcomes.values():
+        _assert_outcome(decision, _ALLOWED, _ALLOWED_ID)
+    assert outcomes[ConsentStatus.REVOKED] == outcomes[ConsentStatus.GRANTED]
+
+
+@pytest.mark.parametrize("action", _NEW_ACTIONS)
+def test_private_sensitivity_behaves_like_normal(action: AuthorizationAction) -> None:
+    strong = _strong_actor_for(action)
+
+    private = _decide(action, actor=strong, sensitivity=frozenset({DataSensitivity.PRIVATE}))
+    normal = _decide(action, actor=strong)
+
+    _assert_outcome(private, _ALLOWED, _ALLOWED_ID)
+    assert (private.decision, private.policy_id) == (normal.decision, normal.policy_id)
+
+
+@pytest.mark.parametrize("role", [HouseholdRole.ADULT, HouseholdRole.CHILD, HouseholdRole.GUEST])
+@pytest.mark.parametrize("action", _NEW_ACTIONS)
+def test_only_the_owner_may_use_personal_memory_and_is_never_asked_to_confirm(
+    action: AuthorizationAction, role: HouseholdRole
+) -> None:
+    actor = _actor(role=role, assurance=IdentityAssurance.STRONG)
+
+    decision = _decide(action, actor=actor, consent=ConsentStatus.GRANTED)
+
+    _assert_outcome(decision, _DENIED, _OWNER_ONLY_ID)
+    assert decision.decision is not AuthorizationStatus.REQUIRES_CONFIRMATION
+
+
+def test_the_generic_security_gate_runs_before_the_owner_only_rule() -> None:
+    """An adult at basic asking for SECURITY data is stopped by the generic gate, not owner-only."""
+    adult = _actor(role=HouseholdRole.ADULT)
+
+    gate = _decide(_READ, actor=adult, sensitivity=_SECURITY, consent=ConsentStatus.GRANTED)
+    plain = _decide(_READ, actor=adult)
+
+    _assert_outcome(gate, _DENIED, _GLOBAL_ASSURANCE_ID)
+    _assert_outcome(plain, _DENIED, _OWNER_ONLY_ID)
+
+
+@pytest.mark.parametrize("action", _NEW_ACTIONS)
+def test_an_unresolved_actor_is_stopped_by_the_existing_identity_gate(
+    action: AuthorizationAction,
+) -> None:
+    probable = _actor(status=ActivePersonStatus.PROBABLE, assurance=IdentityAssurance.NONE)
+    unknown = _actor(
+        role=HouseholdRole.UNKNOWN,
+        status=ActivePersonStatus.UNKNOWN,
+        assurance=IdentityAssurance.NONE,
+        person_id=None,
+    )
+    unknown_role = _actor(role=HouseholdRole.UNKNOWN, assurance=IdentityAssurance.STRONG)
+
+    for actor in (probable, unknown, unknown_role):
+        _assert_outcome(_decide(action, actor=actor), _DENIED, _UNRESOLVED_ID)
+
+
+def test_forget_reaches_personal_private_and_temporary_data_but_not_household_data() -> None:
+    forgetting = _strong_actor_for(_FORGET)
+    private = frozenset({DataVisibility.PRIVATE})
+    temporary = frozenset({DataVisibility.TEMPORARY})
+    household = frozenset({DataVisibility.PERSONAL, DataVisibility.HOUSEHOLD})
+
+    _assert_outcome(_decide(_FORGET, actor=forgetting, visibility=private), _ALLOWED, _ALLOWED_ID)
+    _assert_outcome(_decide(_FORGET, actor=forgetting, visibility=temporary), _ALLOWED, _ALLOWED_ID)
+    _assert_outcome(_decide(_FORGET, actor=forgetting, visibility=household), _DENIED, _OWN_DATA_ID)
+    # The other four reach only {personal}: {private} is already too wide for them.
+    strong = _strong_actor_for(_READ)
+    _assert_outcome(_decide(_READ, actor=strong, visibility=private), _DENIED, _OWN_DATA_ID)
+
+
+def test_non_owner_with_foreign_data_low_assurance_and_no_consent_is_owner_only_first() -> None:
+    actor = _actor(role=HouseholdRole.ADULT, assurance=IdentityAssurance.NONE)
+
+    decision = _decide(
+        _READ,
+        actor=actor,
+        target=_OTHER_ID,
+        sensitivity=_MEDICAL,
+        consent=ConsentStatus.MISSING,
+    )
+
+    _assert_outcome(decision, _DENIED, _OWNER_ONLY_ID)
+
+
+def test_owner_with_foreign_data_and_no_assurance_is_own_data_only_before_assurance() -> None:
+    actor = _actor(assurance=IdentityAssurance.NONE)
+
+    _assert_outcome(_decide(_READ, actor=actor, target=_OTHER_ID), _DENIED, _OWN_DATA_ID)
+
+
+def test_owner_with_own_data_no_assurance_and_no_consent_is_assurance_before_consent() -> None:
+    actor = _actor(assurance=IdentityAssurance.NONE)
+
+    decision = _decide(_READ, actor=actor, sensitivity=_MEDICAL, consent=ConsentStatus.MISSING)
+
+    _assert_outcome(decision, _DENIED, _ASSURANCE_ID)
+
+
+def test_enough_assurance_with_missing_consent_is_consent_required() -> None:
+    decision = _decide(
+        _READ, sensitivity=frozenset({DataSensitivity.LOCATION}), consent=ConsentStatus.MISSING
+    )
+
+    _assert_outcome(decision, _DENIED, _CONSENT_ID)
+
+
+def test_an_action_missing_from_the_table_falls_back_to_the_default_deny(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    monkeypatch.setattr(authorization, "PERSONAL_MEMORY_CAPABILITIES", MappingProxyType({}))
+
+    for action in _NEW_ACTIONS:
+        _assert_outcome(_decide(action), _DENIED, _DEFAULT_DENY_ID)
+
+
+def test_removing_one_action_from_the_table_denies_only_that_action(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    reduced = {k: v for k, v in PERSONAL_MEMORY_CAPABILITIES.items() if k is not _FORGET}
+    monkeypatch.setattr(authorization, "PERSONAL_MEMORY_CAPABILITIES", MappingProxyType(reduced))
+
+    forget = _decide(_FORGET, actor=_strong_actor_for(_FORGET))
+
+    _assert_outcome(forget, _DENIED, _DEFAULT_DENY_ID)
+    _assert_outcome(_decide(_READ), _ALLOWED, _ALLOWED_ID)
+
+
+def test_decisions_carry_the_requested_action_and_only_safe_labels() -> None:
+    vocabulary = {item.value for item in DataVisibility} | {item.value for item in DataSensitivity}
+    cases = [
+        _decide(_READ),
+        _decide(_READ, target=_OTHER_ID),
+        _decide(_READ, actor=_actor(role=HouseholdRole.ADULT)),
+        _decide(_READ, actor=_actor(assurance=IdentityAssurance.NONE)),
+        _decide(_READ, sensitivity=_MEDICAL),
+    ]
+
+    for decision in cases:
+        assert decision.action is _READ
+        assert decision.data_categories <= vocabulary
+        assert "Ada" not in decision.reason
+        assert not any(char.isdigit() for char in decision.reason)
+        assert decision.policy_id.startswith(("cm1.personal-memory.", "p0.5."))
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_personal_memory_policy.py tests/integration/test_personal_memory_audit.py -q -p no:cacheprovider`
  Expected RED: of the 71 tests in the policy file, 47 fail with `assert 'p0.5.default-deny' ==
  'cm1.personal-memory.allowed'` (or `... 'cm1.personal-memory.consent-required'`); the 7 structural
  tests of Task 3 are already green and 17 cases hold only because the unmapped actions fall to the
  default deny. The 5 audit tests fail with `assert 'denied' == 'allowed'`.
- [ ] **Step 3: Implement.**

```diff
diff --git a/server/src/server/cognition/authorization.py b/server/src/server/cognition/authorization.py
index e62d28a..36ea82b 100644
--- a/server/src/server/cognition/authorization.py
+++ b/server/src/server/cognition/authorization.py
@@ -415,8 +415,83 @@ def _evaluate_physical_action_proposal(request: AuthorizationRequest) -> Authori
     )


-def _evaluate_resolved_request(request: AuthorizationRequest) -> AuthorizationDecision:
-    """Evaluate a request after the caller has established a trusted actor."""
+def _personal_memory_decision(
+    request: AuthorizationRequest, status: AuthorizationStatus, outcome: str, reason: str
+) -> AuthorizationDecision:
+    """Build a personal-memory decision whose reason never carries a protected value."""
+    return _decision(request, status, f"cm1.personal-memory.{outcome}", reason)
+
+
+def _is_own_data(request: AuthorizationRequest, capability: PersonalMemoryCapability) -> bool:
+    """Return whether the data is the actor's own and of a visibility the capability reaches."""
+    return (
+        # Defence in depth: a missing target never matches, even if an actor id were absent.
+        request.target_person_id is not None
+        and request.target_person_id == request.actor.person_id
+        and request.visibility <= capability.visibilities
+    )
+
+
+def _lacks_assurance(request: AuthorizationRequest, capability: PersonalMemoryCapability) -> bool:
+    """Return whether the actor's assurance ranks below the capability's minimum."""
+    return ASSURANCE_RANK[request.actor.assurance] < ASSURANCE_RANK[capability.min_assurance]
+
+
+def _lacks_consent(request: AuthorizationRequest, capability: PersonalMemoryCapability) -> bool:
+    """Return whether sensitive data is requested without granted consent."""
+    return (
+        capability.consent_applies
+        and _has_sensitive_data(request)
+        and request.consent is not ConsentStatus.GRANTED
+    )
+
+
+def _evaluate_personal_memory(
+    request: AuthorizationRequest, capability: PersonalMemoryCapability
+) -> AuthorizationDecision:
+    """Evaluate one personal-memory capability in the fixed order of ADR 0019 §5.
+
+    The generic gates (identity resolved; `security` data needs `strong`) have already run.
+    The result is never `REQUIRES_CONFIRMATION`.
+    """
+    if request.actor.role is not HouseholdRole.OWNER:
+        return _personal_memory_decision(
+            request,
+            AuthorizationStatus.DENIED,
+            "owner-only",
+            "Personal memory is reserved for the household owner.",
+        )
+    if not _is_own_data(request, capability):
+        return _personal_memory_decision(
+            request,
+            AuthorizationStatus.DENIED,
+            "own-data-only",
+            "Personal memory covers only the actor's own data.",
+        )
+    if _lacks_assurance(request, capability):
+        return _personal_memory_decision(
+            request,
+            AuthorizationStatus.DENIED,
+            "assurance-required",
+            "This personal memory request needs stronger identity assurance.",
+        )
+    if _lacks_consent(request, capability):
+        return _personal_memory_decision(
+            request,
+            AuthorizationStatus.DENIED,
+            "consent-required",
+            "Required consent is absent or revoked.",
+        )
+    return _personal_memory_decision(
+        request,
+        AuthorizationStatus.ALLOWED,
+        "allowed",
+        "Policy permits this request on the owner's own personal memory.",
+    )
+
+
+def _evaluate_legacy_request(request: AuthorizationRequest) -> AuthorizationDecision:
+    """Evaluate one of the pre-existing actions; anything unlisted is denied."""
     if request.action in {
         AuthorizationAction.READ_HOUSEHOLD_DATA,
         AuthorizationAction.EXECUTE_HOUSEHOLD_TOOL,
@@ -446,6 +521,18 @@ def _evaluate_resolved_request(request: AuthorizationRequest) -> AuthorizationDe
     )


+def _evaluate_resolved_request(request: AuthorizationRequest) -> AuthorizationDecision:
+    """Evaluate a request after the caller has established a trusted actor.
+
+    An action absent from `PERSONAL_MEMORY_CAPABILITIES` falls through to the legacy
+    evaluation, whose last branch is the default deny.
+    """
+    capability = PERSONAL_MEMORY_CAPABILITIES.get(request.action)
+    if capability is not None:
+        return _evaluate_personal_memory(request, capability)
+    return _evaluate_legacy_request(request)
+
+
 def evaluate_authorization(request: AuthorizationRequest) -> AuthorizationDecision:
     """Evaluate one request with a deterministic, local, fail-closed policy."""
     if request.action is AuthorizationAction.GENERAL_CONVERSATION:
```

- [ ] **Step 4: Run, lint, commit.** The two files above plus
  `tests/unit/test_authorization_characterization.py` pass (the old actions did not move); `ruff
  check`, `ruff format --check` over the touched paths; `uv run mypy server/src`; commit
  `feat(server): evaluate personal-memory requests (plan 0060)`.

---

## Task 5: The exhaustive matrix

**Files:**
- Test: `tests/unit/test_personal_memory_policy.py`

**Interfaces:**
- Consumes: the evaluator of Task 4.
- Produces: an **oracle written in the test with literal sets and literal policy ids** (it imports no
  table): 127 sensitivity subsets × 3 assurances × 4 consents × 5 actions for an identified owner on
  own data (7,620 cells, which also proves `forget` is consent-invariant and that nothing asks for
  confirmation), and 18 actors × 3 targets × 63 visibility subsets × 5 actions (17,010 cells) whose
  only allowed cells are an identified owner on own, reachable data.

- [ ] **Step 1: Write the matrix** — it is green on arrival because it restates Task 4's behaviour
  from an independent source:

```diff
diff --git a/tests/unit/test_personal_memory_policy.py b/tests/unit/test_personal_memory_policy.py
index 56c5d40..57f27e9 100644
--- a/tests/unit/test_personal_memory_policy.py
+++ b/tests/unit/test_personal_memory_policy.py
@@ -1,6 +1,8 @@
 """Unit tests for the personal-memory capabilities of the authorization policy (ADR 0019)."""

 from datetime import UTC, datetime
+from functools import cache
+from itertools import combinations, product
 from types import MappingProxyType
 from typing import TYPE_CHECKING, cast
 from uuid import UUID
@@ -23,6 +25,8 @@ from server.cognition.identity import (
     ActivePersonStatus,
     HouseholdRole,
     IdentityAssurance,
+    IdentityEvidence,
+    IdentityEvidenceSource,
 )
 from server.cognition.models import (
     AuthorizationAction,
@@ -220,6 +224,7 @@ def _actor(
     assurance: IdentityAssurance = IdentityAssurance.BASIC,
     status: ActivePersonStatus = ActivePersonStatus.IDENTIFIED,
     person_id: int | None = _OWNER_ID,
+    evidence: tuple[IdentityEvidence, ...] = (),
 ) -> ActivePersonContext:
     """Build one active person for a pure personal-memory case (no media, no database)."""
     return ActivePersonContext(
@@ -232,7 +237,7 @@ def _actor(
             calibrated=False,
         ),
         role=role,
-        evidence=(),
+        evidence=evidence,
         resolved_at=_REQUESTED_AT,
         assurance=assurance,
     )
@@ -481,3 +486,226 @@ def test_decisions_carry_the_requested_action_and_only_safe_labels() -> None:
         assert "Ada" not in decision.reason
         assert not any(char.isdigit() for char in decision.reason)
         assert decision.policy_id.startswith(("cm1.personal-memory.", "p0.5."))
+
+
+# --- exhaustive matrix against an oracle written from the ADR, not from the tables ------
+#
+# The oracle below deliberately imports no table from `authorization`: it restates ADR 0019
+# §2, §3 and §5 with literal values, so a wrong table row cannot agree with itself. Because
+# it only ever answers "allowed" or "denied", agreeing with it also proves that no cell asks
+# for confirmation, that raising assurance never turns an allow into a deny, that widening
+# the category set never turns a deny into an allow, and that withdrawing consent never
+# allows what granted consent denied.
+
+_ASSURANCE_VALUES = ("none", "basic", "strong")
+_ROLE_VALUES = ("owner", "adult", "child", "guest", "unknown")
+_VISIBILITY_VALUES = ("public", "household", "adults", "personal", "private", "temporary")
+_SENSITIVITY_VALUES = (
+    "normal",
+    "private",
+    "biometric",
+    "medical",
+    "location",
+    "child_data",
+    "security",
+)
+_CONSENT_VALUES = ("not_required", "granted", "missing", "revoked")
+_ACTION_VALUES = (
+    "read_personal_conversation_memory",
+    "propose_personal_memory",
+    "confirm_personal_memory",
+    "correct_personal_memory",
+    "forget_personal_memory",
+)
+_FORGET_VALUE = "forget_personal_memory"
+_ORACLE_RANK = {"none": 0, "basic": 1, "strong": 2}
+_ORACLE_MIN_RANK = {
+    "read_personal_conversation_memory": 1,
+    "propose_personal_memory": 1,
+    "confirm_personal_memory": 2,
+    "correct_personal_memory": 1,
+    "forget_personal_memory": 2,
+}
+_ORACLE_SENSITIVE = frozenset({"biometric", "medical", "location", "child_data", "security"})
+_ORACLE_PERSONAL = frozenset({"personal"})
+_ORACLE_VISIBILITIES = {
+    "read_personal_conversation_memory": _ORACLE_PERSONAL,
+    "propose_personal_memory": _ORACLE_PERSONAL,
+    "confirm_personal_memory": _ORACLE_PERSONAL,
+    "correct_personal_memory": _ORACLE_PERSONAL,
+    "forget_personal_memory": frozenset({"personal", "private", "temporary"}),
+}
+_MATRIX_ALLOWED = ("allowed", "cm1.personal-memory.allowed")
+
+
+def _subsets(values: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
+    """Return every non-empty subset of a literal value tuple, in a stable order."""
+    return tuple(
+        subset for size in range(1, len(values) + 1) for subset in combinations(values, size)
+    )
+
+
+_SENSITIVITY_SUBSETS = _subsets(_SENSITIVITY_VALUES)
+_VISIBILITY_SUBSETS = _subsets(_VISIBILITY_VALUES)
+
+
+def _face_evidence() -> IdentityEvidence:
+    """Build the one piece of evidence a face-identified owner carries (no PIN grant)."""
+    return IdentityEvidence(
+        evidence_id=UUID("55555555-5555-5555-5555-555555555555"),
+        source=IdentityEvidenceSource.FACE,
+        candidate_person_id=_OWNER_ID,
+        confidence=Confidence(score=0.95, basis=ConfidenceBasis.MEASURED, calibrated=True),
+        observed_at=_REQUESTED_AT,
+        reference="face-turn",
+    )
+
+
+@cache
+def _matrix_actor(
+    role: str, status: str, assurance: str, person_id: int | None
+) -> ActivePersonContext:
+    """Return one face-only actor for the matrices; unresolved actors carry no evidence."""
+    return _actor(
+        role=HouseholdRole(role),
+        status=ActivePersonStatus(status),
+        assurance=IdentityAssurance(assurance),
+        person_id=person_id,
+        evidence=(_face_evidence(),) if person_id is not None else (),
+    )
+
+
+@cache
+def _matrix_outcome(
+    action: str,
+    actor: tuple[str, str, str, int | None],
+    target: int | None,
+    visibility: tuple[str, ...],
+    sensitivity: tuple[str, ...],
+    consent: str,
+) -> tuple[str, str]:
+    """Evaluate one matrix case and return (status, policy id).
+
+    The request is built with `model_construct` to keep the sweeps fast; the inputs are
+    literal values, so there is nothing for validation to reject.
+    """
+    request = AuthorizationRequest.model_construct(
+        actor=_matrix_actor(*actor),
+        action=AuthorizationAction(action),
+        target_person_id=target,
+        visibility=frozenset(DataVisibility(item) for item in visibility),
+        sensitivity=frozenset(DataSensitivity(item) for item in sensitivity),
+        consent=ConsentStatus(consent),
+        correlation_id=_CORRELATION_ID,
+        requested_at=_REQUESTED_AT,
+    )
+    decision = evaluate_authorization(request)
+    return decision.decision.value, decision.policy_id
+
+
+def _owner_outcome(
+    action: str, assurance: str, sensitivity: tuple[str, ...], consent: str
+) -> tuple[str, str]:
+    """Evaluate the face-identified owner (person 7) on their own {personal} data."""
+    return _matrix_outcome(
+        action,
+        ("owner", "identified", assurance, _OWNER_ID),
+        _OWNER_ID,
+        ("personal",),
+        sensitivity,
+        consent,
+    )
+
+
+def _oracle(
+    action: str, assurance: str, sensitivity: tuple[str, ...], consent: str
+) -> tuple[str, str]:
+    """State the ADR's rule for a face-identified owner acting on their own personal data.
+
+    Forget's PIN-grant requirement is not modelled here yet.
+    """
+    rank = _ORACLE_RANK[assurance]
+    if "security" in sensitivity and rank < _ORACLE_RANK["strong"]:
+        return "denied", "p0.5.assurance-required"
+    if rank < _ORACLE_MIN_RANK[action]:
+        return "denied", "cm1.personal-memory.assurance-required"
+    needs_consent = action != _FORGET_VALUE and _ORACLE_SENSITIVE & set(sensitivity)
+    if needs_consent and consent != "granted":
+        return "denied", "cm1.personal-memory.consent-required"
+    return _MATRIX_ALLOWED
+
+
+def test_the_matrix_sizes_are_the_ones_the_adr_argues_over() -> None:
+    assert len(_SENSITIVITY_SUBSETS) == 127
+    assert len(_VISIBILITY_SUBSETS) == 63
+
+
+@pytest.mark.parametrize("assurance", _ASSURANCE_VALUES)
+@pytest.mark.parametrize("action", _ACTION_VALUES)
+def test_the_owner_matrix_agrees_with_the_oracle_in_every_cell(action: str, assurance: str) -> None:
+    """127 sensitivity sets x 4 consents per (action, assurance): 7 620 cells in all."""
+    mismatches = [
+        (sensitivity, consent, got, want)
+        for sensitivity, consent in product(_SENSITIVITY_SUBSETS, _CONSENT_VALUES)
+        if (got := _owner_outcome(action, assurance, sensitivity, consent))
+        != (want := _oracle(action, assurance, sensitivity, consent))
+    ]
+
+    assert not mismatches, mismatches[:3]
+    if action == _FORGET_VALUE:  # erasure never depends on consent, revoked or not
+        for sensitivity in _SENSITIVITY_SUBSETS:
+            outcomes = {_owner_outcome(action, assurance, sensitivity, c) for c in _CONSENT_VALUES}
+            assert len(outcomes) == 1, sensitivity
+
+
+def _gate_oracle(
+    action: str,
+    actor: tuple[str, str, str, int | None],
+    target: int | None,
+    visibility: tuple[str, ...],
+) -> bool:
+    """Allowed only for an identified owner on their own data of a reachable visibility.
+
+    Sensitivity is normal and consent granted in this sweep, so only the identity, target,
+    visibility and assurance gates can deny. Forget's PIN-grant rule is not modelled yet.
+    """
+    role, status, assurance, _ = actor
+    return (
+        role == "owner"
+        and status == "identified"
+        and target == _OWNER_ID
+        and set(visibility) <= _ORACLE_VISIBILITIES[action]
+        and _ORACLE_RANK[assurance] >= _ORACLE_MIN_RANK[action]
+    )
+
+
+def _all_actors() -> tuple[tuple[str, str, str, int | None], ...]:
+    """Return the 18 actors: 15 identified, a probable owner, an unknown and an ambiguous one."""
+    identified = tuple(
+        (role, "identified", assurance, _OWNER_ID)
+        for role in _ROLE_VALUES
+        for assurance in _ASSURANCE_VALUES
+    )
+    return (
+        *identified,
+        ("owner", "probable", "none", _OWNER_ID),
+        ("unknown", "unknown", "none", None),
+        ("unknown", "ambiguous", "none", None),
+    )
+
+
+@pytest.mark.parametrize("action", _ACTION_VALUES)
+def test_only_an_identified_owner_on_own_reachable_data_is_ever_allowed(action: str) -> None:
+    """18 actors x 3 targets (none, own, foreign) x 63 visibility sets: 3 402 cells per action."""
+    actors = _all_actors()
+    assert len(actors) == 18
+    mismatches = []
+    for actor, target, visibility in product(
+        actors, (None, _OWNER_ID, _OTHER_ID), _VISIBILITY_SUBSETS
+    ):
+        status, _ = _matrix_outcome(action, actor, target, visibility, ("normal",), "granted")
+        want = _gate_oracle(action, actor, target, visibility)
+        if (status == "allowed") != want or status == "requires_confirmation":
+            mismatches.append((actor, target, visibility, status))
+
+    assert not mismatches, mismatches[:3]
```

- [ ] **Step 2: Run it.** `uv run pytest tests/unit/test_personal_memory_policy.py -q -p no:cacheprovider`
  passes (21 new tests, about 1 s).
- [ ] **Step 3: Prove it bites (mutation).** Temporarily set `forget`'s `min_assurance` to
  `IdentityAssurance.BASIC` in the table. The rehearsal saw 4 failures: the Task 3 literal-table
  test, a rank case, `test_the_owner_matrix_agrees_with_the_oracle_in_every_cell[forget_personal_memory-basic]`
  and `test_only_an_identified_owner_on_own_reachable_data_is_ever_allowed[forget_personal_memory]`.
  Do the same with `confirm`: the same four kinds of test fail. Revert and confirm `git diff` is
  empty.
- [ ] **Step 4: Lint and commit.** `ruff check` and `ruff format --check` over the file; commit
  `test(server): exhaustive personal-memory policy matrix (plan 0060)`.

---

## Task 6: Evidence-carried grants and the two scopes

**Files:**
- Modify: `server/src/server/cognition/identity.py`, `identity_sessions.py`,
  `owner_authentication.py`, `authorization.py`, `server/src/server/schemas_auth.py`
- Test: new `tests/unit/test_personal_memory_grants.py`; modified `tests/unit/test_personal_memory_policy.py`,
  `test_identity_sessions.py`, `test_owner_authentication.py`, `test_biometric_admin_scope_callers.py`,
  `tests/integration/test_owner_unlock_endpoint.py` and `test_personal_memory_audit.py`

**Interfaces:**
- Consumes: the registry mechanics of Plan 0051 (a grant presented to the wrong operation is refused
  and kept; spending fails closed).
- Produces: `IdentityEvidence.grant_scope: str | None = None` and `grant_spent: bool = False`;
  `IdentitySessionRegistry.issue_for_person` records `grant_scope`; `consume_evidence` returns a copy
  with `grant_spent=True` (the stored and the peeked object are never mutated);
  `OwnerUnlockScope.PERSONAL_MEMORY_READ = "personal_memory_read"` and
  `PERSONAL_MEMORY_FORGET = "personal_memory_forget"`; the grant step of the evaluator
  (`cm1.personal-memory.grant-scope`) between assurance and consent: every `local_unlock` item must
  carry the capability's own scope, be spent, name the actor's own person and be unexpired
  (`item.expires_at > request.requested_at`); `forget` requires at least one, and a capability with
  no scope accepts none.

- [ ] **Step 1: Write the failing tests.** The headline cases use the **real** `OwnerRequestResolver`,
  `FusedIdentityResolver` and registry, faking only the person and role stores: a peeked forget grant
  is denied and the same grant spent by `resolve_actor` is allowed; grants for the other scopes cannot
  forget; read-by-default and administration grants cannot read personal memory; a forget token given
  to a read, protected-read or administration resolver is refused and **not** spent, and the reverse;
  a hand-built strong actor can read and confirm and is denied forget; `propose`, `confirm`
  and `correct` deny any `local_unlock` item of any scope; a spent forget grant for **another
  person** next to a face-and-voice owner, and an **expired** spent grant, are denied; a face-identified
  owner with a forget token present never consults the PIN, leaves the token spendable and is denied
  (`assurance-required`: a face alone is `basic`), and the same with a verified voice is denied
  `grant-scope`; a forget grant that expires between issue and use authorizes nothing; two attempts to
  spend one token yield the evidence once; the policy oracle gains the PIN dimension (15 PIN states:
  none, each of the five scopes spent or only peeked, and four other-person or expired rows); the
  table's scopes are exactly the two new `OwnerUnlockScope` members and the enum has exactly four
  members; the robot and `scripts/` never mention the new scope strings (the four string tests are
  green on arrival: prove them by adding a scope string to `robot/src/robot/__init__.py` and to
  `scripts/onboard.py` and watching the matching tests fail, then revert).
  Three existing tests change: the evidence field set pinned in `test_identity_sessions.py`, the scope
  enum pin in `test_owner_unlock_endpoint.py`, and the Task 4 and 5 expectations for `forget`.

```diff
diff --git a/tests/integration/test_owner_unlock_endpoint.py b/tests/integration/test_owner_unlock_endpoint.py
index c158ede..b9b0353 100644
--- a/tests/integration/test_owner_unlock_endpoint.py
+++ b/tests/integration/test_owner_unlock_endpoint.py
@@ -148,7 +148,12 @@ async def test_openapi_exposes_no_person_role_or_session_fields() -> None:
     assert set(unlock_request["properties"]) == {"pin", "scope"}
     assert set(unlock_response["properties"]) == {"token", "expires_at", "scope"}
     scope_schema = schemas["OwnerUnlockScope"]
-    assert scope_schema["enum"] == ["personal_protected_read", "biometric_admin"]
+    assert scope_schema["enum"] == [
+        "personal_protected_read",
+        "biometric_admin",
+        "personal_memory_read",
+        "personal_memory_forget",
+    ]
     assert "scope" not in unlock_request.get("required", [])  # additive: clients unchanged


@@ -338,6 +343,26 @@ async def test_an_unlock_can_ask_for_biometric_admin_and_the_response_echoes_it(
     assert response.json()["scope"] == "biometric_admin"


+@pytest.mark.integration
+@pytest.mark.parametrize(
+    "scope", [OwnerUnlockScope.PERSONAL_MEMORY_READ, OwnerUnlockScope.PERSONAL_MEMORY_FORGET]
+)
+async def test_an_unlock_can_ask_for_a_personal_memory_scope_and_the_response_echoes_it(
+    scope: OwnerUnlockScope, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    fake = _FakeService(result=_result().model_copy(update={"scope": scope}))
+    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: fake)
+
+    async with _loopback_client() as client:
+        response = await client.post(
+            "/auth/owner/unlock", json={"pin": "482173", "scope": scope.value}
+        )
+
+    assert response.status_code == 200
+    assert fake.received_scope is scope
+    assert response.json()["scope"] == scope.value
+
+
 @pytest.mark.integration
 @pytest.mark.parametrize("scope", ["root", "personal_protected_write", "", None, 3])
 async def test_an_unknown_scope_is_rejected_without_echoing_the_pin(
diff --git a/tests/integration/test_personal_memory_audit.py b/tests/integration/test_personal_memory_audit.py
index ff942c3..c340e2c 100644
--- a/tests/integration/test_personal_memory_audit.py
+++ b/tests/integration/test_personal_memory_audit.py
@@ -18,6 +18,8 @@ from server.cognition.identity import (
     ActivePersonStatus,
     HouseholdRole,
     IdentityAssurance,
+    IdentityEvidence,
+    IdentityEvidenceSource,
 )
 from server.cognition.models import (
     AuthorizationAction,
@@ -63,13 +65,24 @@ async def test_each_new_action_is_recorded_with_its_value_and_a_cm1_policy_id(
 ) -> None:
     """The audit `action` column is free text: the new values need no migration."""
     owner_id = await upsert_entity(name="Ada", type="person")
+    # Forget alone needs a PIN grant spent for it (ADR 0019 §4); the others need none.
+    grant = IdentityEvidence(
+        evidence_id=UUID("55555555-5555-5555-5555-555555555555"),
+        source=IdentityEvidenceSource.LOCAL_UNLOCK,
+        candidate_person_id=owner_id,
+        confidence=Confidence(score=1.0, basis=ConfidenceBasis.ASSERTED, calibrated=True),
+        observed_at=_AT,
+        reference="session-selection",
+        grant_scope="personal_memory_forget",
+        grant_spent=True,
+    )
     owner = ActivePersonContext(
         person_id=owner_id,
         display_name="Ada",
         status=ActivePersonStatus.IDENTIFIED,
         confidence=Confidence(score=1.0, basis=ConfidenceBasis.ASSERTED, calibrated=False),
         role=HouseholdRole.OWNER,
-        evidence=(),
+        evidence=(grant,) if action is AuthorizationAction.FORGET_PERSONAL_MEMORY else (),
         resolved_at=_AT,
         assurance=IdentityAssurance.STRONG,
     )
diff --git a/tests/unit/test_biometric_admin_scope_callers.py b/tests/unit/test_biometric_admin_scope_callers.py
index 911f877..06b37ee 100644
--- a/tests/unit/test_biometric_admin_scope_callers.py
+++ b/tests/unit/test_biometric_admin_scope_callers.py
@@ -39,3 +39,21 @@ def test_the_robot_never_asks_for_the_administration_scope() -> None:
     sources = (_ROOT / "robot" / "src" / "robot").rglob("*.py")

     assert not [path.name for path in sources if "biometric_admin" in path.read_text("utf-8")]
+
+
+@pytest.mark.unit
+@pytest.mark.parametrize("scope", ["personal_memory_read", "personal_memory_forget"])
+def test_the_robot_never_asks_for_a_personal_memory_scope(scope: str) -> None:
+    """The robot is a generic audio client: it neither knows nor spends memory grants."""
+    sources = (_ROOT / "robot" / "src" / "robot").rglob("*.py")
+
+    assert not [path.name for path in sources if scope in path.read_text("utf-8")]
+
+
+@pytest.mark.unit
+@pytest.mark.parametrize("scope", ["personal_memory_read", "personal_memory_forget"])
+def test_no_script_asks_for_a_personal_memory_scope_yet(scope: str) -> None:
+    """Nothing is wired (ADR 0019 §6): the scopes exist in the policy and the unlock enum only."""
+    sources = (_ROOT / "scripts").glob("*.py")
+
+    assert not [path.name for path in sources if scope in path.read_text("utf-8")]
diff --git a/tests/unit/test_identity_sessions.py b/tests/unit/test_identity_sessions.py
index 434b4ee..ae9a3f9 100644
--- a/tests/unit/test_identity_sessions.py
+++ b/tests/unit/test_identity_sessions.py
@@ -66,6 +66,8 @@ def test_registry_uses_an_opaque_token_and_retains_safe_evidence_only() -> None:
         "observed_at",
         "reference",
         "expires_at",
+        "grant_scope",
+        "grant_spent",
     }


@@ -254,3 +256,40 @@ def test_a_scoped_token_cannot_be_spent_by_a_caller_that_names_no_scope() -> Non
     assert registry.consume_evidence(token) is None
     assert registry.evidence_for(token, scope="read") is not None  # refused, not spent
     assert registry.consume_evidence(token, scope="read") is not None
+
+
+# --- Plan 0060: the evidence carries the scope of its grant and whether it was spent ----------
+
+
+def test_issued_evidence_carries_its_scope_and_is_unspent_until_consumed() -> None:
+    now = [_NOW]
+    registry = _scoped_registry(now)
+    token = registry.issue_for_person(
+        _person(42), source=IdentityEvidenceSource.LOCAL_UNLOCK, scope="read"
+    )
+
+    peeked = registry.evidence_for(token, scope="read")
+    assert peeked is not None
+    assert (peeked.grant_scope, peeked.grant_spent) == ("read", False)
+
+    spent = registry.consume_evidence(token, scope="read")
+    assert spent is not None
+    assert (spent.grant_scope, spent.grant_spent) == ("read", True)
+    assert spent.evidence_id == peeked.evidence_id
+    assert peeked.grant_spent is False  # the object peeked earlier is never mutated
+
+
+def test_a_grant_issued_without_a_scope_carries_none_and_a_selection_is_not_a_grant() -> None:
+    now = [_NOW]
+    registry = _scoped_registry(now)
+    unscoped = registry.issue_for_person(_person(42), source=IdentityEvidenceSource.LOCAL_UNLOCK)
+    selected = registry.select_person(42)
+    assert selected is not None
+
+    unscoped_evidence = registry.consume_evidence(unscoped)
+    selection_evidence = registry.evidence_for(selected)
+
+    assert unscoped_evidence is not None
+    assert (unscoped_evidence.grant_scope, unscoped_evidence.grant_spent) == (None, True)
+    assert selection_evidence is not None
+    assert (selection_evidence.grant_scope, selection_evidence.grant_spent) == (None, False)
diff --git a/tests/unit/test_owner_authentication.py b/tests/unit/test_owner_authentication.py
index ea01a51..5c1d017 100644
--- a/tests/unit/test_owner_authentication.py
+++ b/tests/unit/test_owner_authentication.py
@@ -446,3 +446,16 @@ async def test_a_scope_mismatch_is_logged_as_a_closed_reason_and_never_the_token
     joined = "\n".join(record.getMessage() for record in caplog.records)
     assert "scope_mismatch" in joined
     assert unlock.token not in joined
+
+
+# --- Plan 0060: personal-memory scopes (ADR 0019 §4) ----------------------------------------
+
+
+@pytest.mark.unit
+async def test_the_service_issues_a_grant_for_each_personal_memory_scope() -> None:
+    service = _service(credential=_credential())
+
+    for scope in (OwnerUnlockScope.PERSONAL_MEMORY_READ, OwnerUnlockScope.PERSONAL_MEMORY_FORGET):
+        unlock = await service.unlock(_PIN, scope)
+        assert unlock is not None
+        assert unlock.scope is scope
diff --git a/tests/unit/test_personal_memory_grants.py b/tests/unit/test_personal_memory_grants.py
new file mode 100644
index 0000000..9ce75d5
--- /dev/null
+++ b/tests/unit/test_personal_memory_grants.py
@@ -0,0 +1,355 @@
+"""A PIN grant authorizes only the operation it was issued for (ADR 0019 §4).
+
+These tests run the real `OwnerRequestResolver`, `FusedIdentityResolver`, registry and
+policy together; only the person and role stores, the face resolver and the speaker are
+doubles. The policy sees the grant through the actor's evidence: its scope and whether this
+request spent it.
+"""
+
+from datetime import UTC, datetime, timedelta
+from typing import TYPE_CHECKING, cast
+from uuid import UUID
+
+import pytest
+from server.cognition.authorization import (
+    AuthorizationRequest,
+    ConsentStatus,
+    DataSensitivity,
+    DataVisibility,
+    evaluate_authorization,
+)
+from server.cognition.face_authentication import FaceAuthenticationVerdict
+from server.cognition.identity import (
+    ActivePersonContext,
+    ActivePersonStatus,
+    HouseholdRole,
+    IdentityAssurance,
+    IdentityEvidence,
+    IdentityEvidenceSource,
+    PersonRecord,
+    resolve_active_person,
+)
+from server.cognition.identity_fusion import FusedIdentityResolver
+from server.cognition.identity_sessions import IdentitySessionRegistry
+from server.cognition.models import (
+    AuthorizationAction,
+    AuthorizationDecision,
+    AuthorizationStatus,
+    CognitiveEvent,
+    Confidence,
+    ConfidenceBasis,
+)
+from server.cognition.owner_authentication import OwnerRequestResolver, OwnerUnlockScope
+from server.cognition.response_plan import TextTurnPayload
+from server.cognition.speaker_authentication import SpeakerVerdict
+
+if TYPE_CHECKING:
+    from collections.abc import Callable
+
+    from server.cognition.face_authentication import FaceRequestResolver
+    from server.cognition.speaker_authentication import SpeakerRequestResolver
+
+pytestmark = pytest.mark.unit
+
+_T0 = datetime(2026, 10, 8, 12, tzinfo=UTC)
+_OWNER_ID = 7
+_OWNER = PersonRecord(person_id=_OWNER_ID, display_name="Ada", entity_type="person")
+_READ = AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY
+_PROPOSE = AuthorizationAction.PROPOSE_PERSONAL_MEMORY
+_CONFIRM = AuthorizationAction.CONFIRM_PERSONAL_MEMORY
+_CORRECT = AuthorizationAction.CORRECT_PERSONAL_MEMORY
+_FORGET = AuthorizationAction.FORGET_PERSONAL_MEMORY
+_ALL_ACTIONS = (_READ, _PROPOSE, _CONFIRM, _CORRECT, _FORGET)
+_OWN_ACTION = {
+    OwnerUnlockScope.PERSONAL_MEMORY_READ: _READ,
+    OwnerUnlockScope.PERSONAL_MEMORY_FORGET: _FORGET,
+}
+_ALL_SCOPES = tuple(OwnerUnlockScope)
+_GRANT_SCOPE_ID = "cm1.personal-memory.grant-scope"
+_ALLOWED_ID = "cm1.personal-memory.allowed"
+_MEDICAL = frozenset({DataSensitivity.MEDICAL})
+
+
+def _event() -> CognitiveEvent[TextTurnPayload]:
+    return CognitiveEvent(
+        event_id=UUID("99999999-9999-9999-9999-999999999999"),
+        schema_version=1,
+        event_type="text.turn",
+        occurred_at=_T0,
+        recorded_at=_T0,
+        source="web.chat",
+        correlation_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
+        causation_id=None,
+        subject_id=None,
+        payload=TextTurnPayload(message="canary", conversation_id="canary-scope"),
+    )
+
+
+class _Rig:
+    """One registry on a movable clock, one issued token, and resolvers built for it."""
+
+    def __init__(self, issued: OwnerUnlockScope) -> None:
+        self.now = _T0
+        self.registry = IdentitySessionRegistry(
+            lookup_person=lambda _pid: None, clock=lambda: self.now, ttl=timedelta(seconds=60)
+        )
+        self.issued = issued
+        self.token = self.registry.issue_for_person(
+            _OWNER, source=IdentityEvidenceSource.LOCAL_UNLOCK, scope=issued.value
+        )
+
+    def resolver(self, asked: OwnerUnlockScope) -> OwnerRequestResolver:
+        """Build the resolver a branch for the `asked` operation would use."""
+
+        async def read_role(_person_id: int) -> HouseholdRole:
+            return HouseholdRole.OWNER
+
+        async def read_person(_person_id: int) -> PersonRecord | None:
+            return _OWNER
+
+        return OwnerRequestResolver(
+            token=self.token,
+            registry=self.registry,
+            read_role=read_role,
+            read_person=read_person,
+            clock=lambda: self.now,
+            scope=asked,
+        )
+
+    def fused(
+        self,
+        asked: OwnerUnlockScope,
+        *,
+        face: "_FakeFace | None" = None,
+        speaker_factory: "_SpeakerFactory | None" = None,
+    ) -> FusedIdentityResolver:
+        """The production composition; with no face and no voice the PIN is the only path."""
+        return FusedIdentityResolver(
+            pin=self.resolver(asked),
+            # The fakes stand in for resolvers that need a database and models; the fusion
+            # only uses `resolve_actor`, `last_verdict` and `resolve_consent`.
+            face=cast("FaceRequestResolver | None", face),
+            speaker_factory=cast("Callable[[int], SpeakerRequestResolver] | None", speaker_factory),
+            clock=lambda: self.now,
+        )
+
+    def is_spendable(self) -> bool:
+        """Whether the token is still in the registry, unspent."""
+        return self.registry.evidence_for(self.token) is not None
+
+
+def _lookup(person_id: int) -> PersonRecord | None:
+    return _OWNER if person_id == _OWNER_ID else None
+
+
+def _evidence(source: IdentityEvidenceSource) -> IdentityEvidence:
+    return IdentityEvidence(
+        evidence_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
+        source=source,
+        candidate_person_id=_OWNER_ID,
+        confidence=Confidence(score=0.95, basis=ConfidenceBasis.MEASURED, calibrated=True),
+        observed_at=_T0,
+        reference="turn",
+    )
+
+
+def _owner_from(*sources: IdentityEvidenceSource) -> ActivePersonContext:
+    """Resolve a real actor from the given evidence sources for the owner."""
+    return resolve_active_person(
+        evidence=tuple(_evidence(source) for source in sources),
+        lookup_person=_lookup,
+        lookup_role=lambda _person_id: HouseholdRole.OWNER,
+        clock=lambda: _T0,
+    )
+
+
+class _FakeFace:
+    """Stands in for the face resolver: it always identifies the owner."""
+
+    last_verdict = FaceAuthenticationVerdict.IDENTIFIED
+
+    async def resolve_actor(self, _event: object) -> ActivePersonContext:
+        return _owner_from(IdentityEvidenceSource.FACE)
+
+    async def resolve_consent(self, _event: object, _actor: object) -> ConsentStatus:
+        return ConsentStatus.GRANTED
+
+
+class _FakeSpeaker:
+    """Stands in for the speaker resolver: it verifies the owner's voice."""
+
+    last_verdict = SpeakerVerdict.VERIFIED
+
+    async def resolve_actor(self, _event: object) -> ActivePersonContext:
+        return _owner_from(IdentityEvidenceSource.VOICE)
+
+
+class _SpeakerFactory:
+    def __call__(self, _owner_person_id: int) -> _FakeSpeaker:
+        return _FakeSpeaker()
+
+
+def _decide(
+    actor: ActivePersonContext,
+    action: AuthorizationAction,
+    *,
+    sensitivity: frozenset[DataSensitivity] = frozenset({DataSensitivity.NORMAL}),
+    consent: ConsentStatus = ConsentStatus.NOT_REQUIRED,
+) -> AuthorizationDecision:
+    return evaluate_authorization(
+        AuthorizationRequest(
+            actor=actor,
+            action=action,
+            target_person_id=_OWNER_ID,
+            visibility=frozenset({DataVisibility.PERSONAL}),
+            sensitivity=sensitivity,
+            consent=consent,
+            correlation_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
+            requested_at=_T0,
+        )
+    )
+
+
+def _outcome(decision: AuthorizationDecision) -> tuple[AuthorizationStatus, str]:
+    return decision.decision, decision.policy_id
+
+
+async def test_a_forget_grant_forgets_only_after_this_request_spent_it() -> None:
+    rig = _Rig(OwnerUnlockScope.PERSONAL_MEMORY_FORGET)
+    fused = rig.fused(OwnerUnlockScope.PERSONAL_MEMORY_FORGET)
+    event = _event()
+
+    peeked = await fused.peek_actor(event)
+    assert [item.grant_spent for item in peeked.evidence] == [False]
+    assert _outcome(_decide(peeked, _FORGET)) == (AuthorizationStatus.DENIED, _GRANT_SCOPE_ID)
+    assert rig.is_spendable()
+
+    actor = await fused.resolve_actor(event)
+    consent = await fused.resolve_consent(event, actor)
+    assert [item.grant_spent for item in actor.evidence] == [True]
+    after = _decide(actor, _FORGET, sensitivity=_MEDICAL, consent=consent)
+    assert _outcome(after) == (AuthorizationStatus.ALLOWED, _ALLOWED_ID)
+    assert not rig.is_spendable()
+
+
+@pytest.mark.parametrize("issued", _ALL_SCOPES)
+async def test_a_spent_grant_authorizes_only_the_operation_it_was_issued_for(
+    issued: OwnerUnlockScope,
+) -> None:
+    """After the right resolver spends it, exactly (read, read scope) and (forget, forget scope)."""
+    rig = _Rig(issued)
+    fused = rig.fused(issued)
+    event = _event()
+    actor = await fused.resolve_actor(event)
+    consent = await fused.resolve_consent(event, actor)
+
+    for action in _ALL_ACTIONS:
+        decision = _decide(actor, action, sensitivity=_MEDICAL, consent=consent)
+        if _OWN_ACTION.get(issued) is action:
+            assert _outcome(decision) == (AuthorizationStatus.ALLOWED, _ALLOWED_ID)
+        else:
+            assert _outcome(decision) == (AuthorizationStatus.DENIED, _GRANT_SCOPE_ID)
+
+
+@pytest.mark.parametrize(
+    "issued, asked",
+    [(i, a) for i in _ALL_SCOPES for a in _ALL_SCOPES if i is not a],
+    ids=lambda scope: scope.value,
+)
+async def test_a_grant_is_refused_by_every_other_scope_and_not_spent(
+    issued: OwnerUnlockScope, asked: OwnerUnlockScope
+) -> None:
+    rig = _Rig(issued)
+
+    attempt_resolver = rig.resolver(asked)
+    attempt = await attempt_resolver.resolve_actor(_event())
+
+    assert attempt.status is ActivePersonStatus.UNKNOWN
+    assert attempt_resolver.consumed is False
+    assert rig.is_spendable()
+    assert _decide(attempt, _READ).policy_id == "p0.5.identity-unresolved"
+    own = await rig.resolver(issued).resolve_actor(_event())
+    again = await rig.resolver(issued).resolve_actor(_event())
+    assert own.status is ActivePersonStatus.IDENTIFIED  # still spendable ...
+    assert again.status is ActivePersonStatus.UNKNOWN  # ... exactly once
+
+
+@pytest.mark.parametrize("scope", _ALL_SCOPES)
+async def test_the_actor_evidence_and_the_granted_scope_name_the_grant(
+    scope: OwnerUnlockScope,
+) -> None:
+    rig = _Rig(scope)
+    resolver = rig.resolver(scope)
+    event = _event()
+
+    peeked = await resolver.peek_actor(event)
+    assert resolver.scope == frozenset()
+    spent = await resolver.resolve_actor(event)
+
+    assert [(e.grant_scope, e.grant_spent) for e in peeked.evidence] == [(scope.value, False)]
+    assert [(e.grant_scope, e.grant_spent) for e in spent.evidence] == [(scope.value, True)]
+    expected = {scope.value}
+    if scope is OwnerUnlockScope.PERSONAL_PROTECTED_READ:
+        expected.add("child_data")  # only the child-data read names the data it unlocks
+    assert resolver.scope == frozenset(expected)
+
+
+async def test_a_face_identified_owner_does_not_consult_a_present_forget_token() -> None:
+    """ADR 0016 §5: the face resolved first, so the PIN is not used and nothing is forgotten."""
+    rig = _Rig(OwnerUnlockScope.PERSONAL_MEMORY_FORGET)
+    fused = rig.fused(OwnerUnlockScope.PERSONAL_MEMORY_FORGET, face=_FakeFace())
+
+    actor = await fused.resolve_actor(_event())
+
+    assert actor.assurance is IdentityAssurance.BASIC
+    assert fused.consumed is False
+    assert rig.is_spendable()
+    # At `basic` the assurance rule answers first; the grant is never even reached.
+    assert _decide(actor, _FORGET).policy_id == "cm1.personal-memory.assurance-required"
+    later = await rig.fused(OwnerUnlockScope.PERSONAL_MEMORY_FORGET).resolve_actor(_event())
+    assert _decide(later, _FORGET).decision is AuthorizationStatus.ALLOWED
+
+
+async def test_a_face_and_voice_owner_with_a_present_forget_token_still_cannot_forget() -> None:
+    rig = _Rig(OwnerUnlockScope.PERSONAL_MEMORY_FORGET)
+    fused = rig.fused(
+        OwnerUnlockScope.PERSONAL_MEMORY_FORGET,
+        face=_FakeFace(),
+        speaker_factory=_SpeakerFactory(),
+    )
+
+    actor = await fused.resolve_actor(_event())
+
+    assert actor.assurance is IdentityAssurance.STRONG
+    assert fused.consumed is False
+    assert rig.is_spendable()
+    assert _outcome(_decide(actor, _FORGET)) == (AuthorizationStatus.DENIED, _GRANT_SCOPE_ID)
+    assert _decide(actor, _READ).decision is AuthorizationStatus.ALLOWED
+    assert _decide(actor, _CONFIRM).decision is AuthorizationStatus.ALLOWED
+    later = await rig.fused(OwnerUnlockScope.PERSONAL_MEMORY_FORGET).resolve_actor(_event())
+    assert _decide(later, _FORGET).decision is AuthorizationStatus.ALLOWED
+
+
+async def test_a_grant_that_expires_between_issue_and_use_authorizes_nothing() -> None:
+    rig = _Rig(OwnerUnlockScope.PERSONAL_MEMORY_FORGET)
+    resolver = rig.resolver(OwnerUnlockScope.PERSONAL_MEMORY_FORGET)
+
+    rig.now = _T0 + timedelta(seconds=61)
+    actor = await resolver.resolve_actor(_event())
+
+    assert actor.status is ActivePersonStatus.UNKNOWN
+    assert resolver.consumed is False
+    assert not rig.is_spendable()
+    assert _decide(actor, _FORGET).policy_id == "p0.5.identity-unresolved"
+
+
+def test_two_attempts_to_spend_one_grant_yield_the_evidence_exactly_once() -> None:
+    rig = _Rig(OwnerUnlockScope.PERSONAL_MEMORY_FORGET)
+    scope = OwnerUnlockScope.PERSONAL_MEMORY_FORGET.value
+
+    first = rig.registry.consume_evidence(rig.token, scope=scope)
+    second = rig.registry.consume_evidence(rig.token, scope=scope)
+
+    assert first is not None
+    assert first.grant_spent is True
+    assert second is None
diff --git a/tests/unit/test_personal_memory_policy.py b/tests/unit/test_personal_memory_policy.py
index 57f27e9..7451e9c 100644
--- a/tests/unit/test_personal_memory_policy.py
+++ b/tests/unit/test_personal_memory_policy.py
@@ -1,6 +1,6 @@
 """Unit tests for the personal-memory capabilities of the authorization policy (ADR 0019)."""

-from datetime import UTC, datetime
+from datetime import UTC, datetime, timedelta
 from functools import cache
 from itertools import combinations, product
 from types import MappingProxyType
@@ -35,6 +35,7 @@ from server.cognition.models import (
     Confidence,
     ConfidenceBasis,
 )
+from server.cognition.owner_authentication import OwnerUnlockScope

 if TYPE_CHECKING:
     from collections.abc import MutableMapping
@@ -244,9 +245,8 @@ def _actor(


 def _strong_actor_for(action: AuthorizationAction) -> ActivePersonContext:
-    """A hand-built strong owner (no evidence) who can exercise `action`."""
-    del action
-    return _actor(assurance=IdentityAssurance.STRONG)
+    """A strong owner who can exercise `action`: a spent forget grant, else face and voice."""
+    return _pin_actor(_FORGET_SCOPE) if action is _FORGET else _face_voice_actor()


 def _decide(
@@ -294,7 +294,13 @@ def test_assurance_is_compared_by_rank_against_each_actions_minimum(
     action: AuthorizationAction, assurance: IdentityAssurance, policy_id: str
 ) -> None:
     """Read, propose and correct need `basic`; confirm and forget need `strong`; none never."""
-    decision = _decide(action, actor=_actor(assurance=assurance))
+    actor = (
+        _strong_actor_for(action)
+        if assurance is IdentityAssurance.STRONG
+        else _actor(assurance=assurance)
+    )
+
+    decision = _decide(action, actor=actor)

     assert decision.policy_id == policy_id
     assert decision.action is action
@@ -488,14 +494,183 @@ def test_decisions_carry_the_requested_action_and_only_safe_labels() -> None:
         assert decision.policy_id.startswith(("cm1.personal-memory.", "p0.5."))


+# --- grants carried by the evidence (ADR 0019 §4) -----------------------------
+
+_READ_SCOPE = "personal_memory_read"
+_FORGET_SCOPE = "personal_memory_forget"
+_GRANT_SCOPE_ID = "cm1.personal-memory.grant-scope"
+# Every scope string a grant could carry: the four real ones, a stranger and "none issued".
+_ANY_GRANT_SCOPE = (
+    "personal_protected_read",
+    "biometric_admin",
+    _READ_SCOPE,
+    _FORGET_SCOPE,
+    "anything",
+    None,
+)
+
+
+def _pin_evidence(
+    *, scope: str | None, spent: bool = True, kind: str = "owner"
+) -> IdentityEvidence:
+    """Build the evidence an owner PIN grant leaves.
+
+    `kind` is `owner` (a fresh grant for the owner), `other_person` (a grant for someone
+    else) or `expired` (a grant whose lifetime ended before the request).
+    """
+    return IdentityEvidence(
+        evidence_id=UUID("66666666-6666-6666-6666-666666666666"),
+        source=IdentityEvidenceSource.LOCAL_UNLOCK,
+        candidate_person_id=_OTHER_ID if kind == "other_person" else _OWNER_ID,
+        confidence=Confidence(score=1.0, basis=ConfidenceBasis.ASSERTED, calibrated=True),
+        observed_at=_REQUESTED_AT - timedelta(seconds=120),
+        expires_at=_REQUESTED_AT - timedelta(seconds=60)
+        if kind == "expired"
+        else _REQUESTED_AT + timedelta(seconds=60),
+        reference="session-selection",
+        grant_scope=scope,
+        grant_spent=spent,
+    )
+
+
+def _voice_evidence() -> IdentityEvidence:
+    """Build the voice evidence that corroborates the owner's face."""
+    return IdentityEvidence(
+        evidence_id=UUID("77777777-7777-7777-7777-777777777777"),
+        source=IdentityEvidenceSource.VOICE,
+        candidate_person_id=_OWNER_ID,
+        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
+        observed_at=_REQUESTED_AT,
+        reference="in-turn-speaker-evidence",
+    )
+
+
+def _pin_actor(
+    scope: str | None, *, spent: bool = True, kind: str = "owner"
+) -> ActivePersonContext:
+    """A strong owner identified by one PIN grant of `scope`, spent or only peeked."""
+    return _actor(
+        assurance=IdentityAssurance.STRONG,
+        evidence=(_pin_evidence(scope=scope, spent=spent, kind=kind),),
+    )
+
+
+def _face_voice_actor() -> ActivePersonContext:
+    """A hand-built strong owner whose evidence is a face and a voice, with no PIN item."""
+    return _actor(
+        assurance=IdentityAssurance.STRONG, evidence=(_face_evidence(), _voice_evidence())
+    )
+
+
+def test_a_grant_counts_only_for_its_own_operation_and_only_once_spent() -> None:
+    """Read and forget each accept one scope; every other scope, and a peek, is refused."""
+    for action, own in ((_READ, _READ_SCOPE), (_FORGET, _FORGET_SCOPE)):
+        for scope in _ANY_GRANT_SCOPE:
+            decision = _decide(action, actor=_pin_actor(scope))
+            if scope == own:
+                _assert_outcome(decision, _ALLOWED, _ALLOWED_ID)
+            else:
+                _assert_outcome(decision, _DENIED, _GRANT_SCOPE_ID)
+        peeked = _decide(action, actor=_pin_actor(own, spent=False))
+        _assert_outcome(peeked, _DENIED, _GRANT_SCOPE_ID)
+
+
+def test_propose_confirm_and_correct_have_no_pin_route() -> None:
+    """Any PIN item denies them, whatever its scope: a spent read grant is the example."""
+    for action in (_PROPOSE, _CONFIRM, _CORRECT):
+        _assert_outcome(_decide(action, actor=_pin_actor(_READ_SCOPE)), _DENIED, _GRANT_SCOPE_ID)
+
+
+def test_a_hand_built_strong_actor_reads_and_confirms_but_cannot_forget() -> None:
+    both = _face_voice_actor()
+
+    _assert_outcome(_decide(_READ, actor=both), _ALLOWED, _ALLOWED_ID)
+    _assert_outcome(_decide(_CONFIRM, actor=both), _ALLOWED, _ALLOWED_ID)
+    _assert_outcome(_decide(_FORGET, actor=both), _DENIED, _GRANT_SCOPE_ID)
+
+
+def test_every_pin_item_must_carry_the_right_scope_and_be_spent() -> None:
+    right = _pin_evidence(scope=_FORGET_SCOPE)
+    wrong = right.model_copy(
+        update={
+            "evidence_id": UUID("88888888-8888-8888-8888-888888888888"),
+            "grant_scope": _READ_SCOPE,
+        }
+    )
+    mixed = _actor(assurance=IdentityAssurance.STRONG, evidence=(right, wrong))
+    face_and_grant = _actor(assurance=IdentityAssurance.STRONG, evidence=(_face_evidence(), right))
+
+    _assert_outcome(_decide(_FORGET, actor=mixed), _DENIED, _GRANT_SCOPE_ID)
+    _assert_outcome(_decide(_FORGET, actor=face_and_grant), _ALLOWED, _ALLOWED_ID)
+
+
+def test_a_grant_for_another_person_next_to_a_strong_owner_authorizes_nothing() -> None:
+    """A spent forget grant of someone else must not ride on the owner's face and voice."""
+    foreign = _pin_evidence(scope=_FORGET_SCOPE, kind="other_person")
+    owner = _actor(
+        assurance=IdentityAssurance.STRONG,
+        evidence=(_face_evidence(), _voice_evidence(), foreign),
+    )
+
+    _assert_outcome(_decide(_FORGET, actor=owner), _DENIED, _GRANT_SCOPE_ID)
+
+
+def test_an_expired_grant_authorizes_nothing_even_when_marked_spent() -> None:
+    expired = _pin_actor(_FORGET_SCOPE, kind="expired")
+
+    _assert_outcome(_decide(_FORGET, actor=expired), _DENIED, _GRANT_SCOPE_ID)
+
+
+def test_a_grant_is_judged_after_assurance_and_before_consent() -> None:
+    wrong_scope_no_consent = _decide(
+        _READ, actor=_pin_actor(_FORGET_SCOPE), sensitivity=_MEDICAL, consent=ConsentStatus.MISSING
+    )
+    low_assurance_wrong_scope = _decide(
+        _FORGET,
+        actor=_actor(
+            assurance=IdentityAssurance.BASIC, evidence=(_pin_evidence(scope=_READ_SCOPE),)
+        ),
+    )
+
+    _assert_outcome(wrong_scope_no_consent, _DENIED, _GRANT_SCOPE_ID)
+    _assert_outcome(low_assurance_wrong_scope, _DENIED, _ASSURANCE_ID)
+
+
+def test_a_manual_selection_is_not_a_pin_grant() -> None:
+    """Only `local_unlock` evidence triggers the grant rules; a manual one is ignored."""
+    manual = _pin_evidence(scope=None).model_copy(update={"source": IdentityEvidenceSource.MANUAL})
+    actor = _actor(assurance=IdentityAssurance.BASIC, evidence=(manual,))
+
+    _assert_outcome(_decide(_READ, actor=actor), _ALLOWED, _ALLOWED_ID)
+
+
+def test_the_unlock_scope_enum_and_the_table_scopes_agree() -> None:
+    table_scopes = {
+        capability.unlock_scope
+        for capability in PERSONAL_MEMORY_CAPABILITIES.values()
+        if capability.unlock_scope is not None
+    }
+
+    assert [scope.value for scope in OwnerUnlockScope] == [
+        "personal_protected_read",
+        "biometric_admin",
+        "personal_memory_read",
+        "personal_memory_forget",
+    ]
+    assert table_scopes == {
+        OwnerUnlockScope.PERSONAL_MEMORY_READ.value,
+        OwnerUnlockScope.PERSONAL_MEMORY_FORGET.value,
+    }
+
+
 # --- exhaustive matrix against an oracle written from the ADR, not from the tables ------
 #
 # The oracle below deliberately imports no table from `authorization`: it restates ADR 0019
-# §2, §3 and §5 with literal values, so a wrong table row cannot agree with itself. Because
+# §2, §3, §4 and §5 with literal values, so a wrong table row cannot agree with itself. Because
 # it only ever answers "allowed" or "denied", agreeing with it also proves that no cell asks
 # for confirmation, that raising assurance never turns an allow into a deny, that widening
-# the category set never turns a deny into an allow, and that withdrawing consent never
-# allows what granted consent denied.
+# the category set never turns a deny into an allow, that withdrawing consent never allows
+# what granted consent denied, and that a peeked grant is never better than a spent one.

 _ASSURANCE_VALUES = ("none", "basic", "strong")
 _ROLE_VALUES = ("owner", "adult", "child", "guest", "unknown")
@@ -535,8 +710,34 @@ _ORACLE_VISIBILITIES = {
     "correct_personal_memory": _ORACLE_PERSONAL,
     "forget_personal_memory": frozenset({"personal", "private", "temporary"}),
 }
+_ORACLE_UNLOCK_SCOPE = {
+    "read_personal_conversation_memory": "personal_memory_read",
+    "forget_personal_memory": "personal_memory_forget",
+}
 _MATRIX_ALLOWED = ("allowed", "cm1.personal-memory.allowed")

+# A PIN item as (scope it carries, spent?, kind); None means the actor holds only a face item.
+type Pin = tuple[str | None, bool, str] | None
+_FORGET_PIN: Pin = ("personal_memory_forget", True, "owner")
+_PIN_SCOPES = (
+    "personal_protected_read",
+    "biometric_admin",
+    "personal_memory_read",
+    "personal_memory_forget",
+    None,
+)
+# Every PIN state the matrix visits: none; each scope spent or only peeked; and a spent grant
+# of the two real scopes that belongs to another person or has expired.
+_PIN_STATES: tuple[Pin, ...] = (
+    None,
+    *((scope, spent, "owner") for scope in _PIN_SCOPES for spent in (True, False)),
+    *(
+        (scope, True, kind)
+        for scope in ("personal_memory_read", "personal_memory_forget")
+        for kind in ("other_person", "expired")
+    ),
+)
+

 def _subsets(values: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
     """Return every non-empty subset of a literal value tuple, in a stable order."""
@@ -561,17 +762,33 @@ def _face_evidence() -> IdentityEvidence:
     )


+def _best_pin(action: str) -> Pin:
+    """The grant state that lets the owner exercise `action`: only forget needs a PIN grant."""
+    return _FORGET_PIN if action == _FORGET_VALUE else None
+
+
 @cache
 def _matrix_actor(
-    role: str, status: str, assurance: str, person_id: int | None
+    role: str, status: str, assurance: str, person_id: int | None, pin: Pin
 ) -> ActivePersonContext:
-    """Return one face-only actor for the matrices; unresolved actors carry no evidence."""
+    """Return one actor for the matrices.
+
+    A resolved actor carries either one PIN item (when `pin` is given) or one face item;
+    an unresolved actor carries no evidence. A legitimate PIN item names the owner and is
+    still fresh at the request time.
+    """
+    if person_id is None:
+        evidence: tuple[IdentityEvidence, ...] = ()
+    elif pin is None:
+        evidence = (_face_evidence(),)
+    else:
+        evidence = (_pin_evidence(scope=pin[0], spent=pin[1], kind=pin[2]),)
     return _actor(
         role=HouseholdRole(role),
         status=ActivePersonStatus(status),
         assurance=IdentityAssurance(assurance),
         person_id=person_id,
-        evidence=(_face_evidence(),) if person_id is not None else (),
+        evidence=evidence,
     )


@@ -583,6 +800,7 @@ def _matrix_outcome(
     visibility: tuple[str, ...],
     sensitivity: tuple[str, ...],
     consent: str,
+    pin: Pin,
 ) -> tuple[str, str]:
     """Evaluate one matrix case and return (status, policy id).

@@ -590,7 +808,7 @@ def _matrix_outcome(
     literal values, so there is nothing for validation to reject.
     """
     request = AuthorizationRequest.model_construct(
-        actor=_matrix_actor(*actor),
+        actor=_matrix_actor(*actor, pin),
         action=AuthorizationAction(action),
         target_person_id=target,
         visibility=frozenset(DataVisibility(item) for item in visibility),
@@ -604,9 +822,9 @@ def _matrix_outcome(


 def _owner_outcome(
-    action: str, assurance: str, sensitivity: tuple[str, ...], consent: str
+    action: str, assurance: str, sensitivity: tuple[str, ...], consent: str, pin: Pin
 ) -> tuple[str, str]:
-    """Evaluate the face-identified owner (person 7) on their own {personal} data."""
+    """Evaluate the identified owner (person 7) on their own {personal} data."""
     return _matrix_outcome(
         action,
         ("owner", "identified", assurance, _OWNER_ID),
@@ -614,21 +832,34 @@ def _owner_outcome(
         ("personal",),
         sensitivity,
         consent,
+        pin,
     )


-def _oracle(
-    action: str, assurance: str, sensitivity: tuple[str, ...], consent: str
-) -> tuple[str, str]:
-    """State the ADR's rule for a face-identified owner acting on their own personal data.
+def _grant_is_valid(action: str, pin: Pin) -> bool:
+    """ADR 0019 §4: forget needs a spent forget grant; read accepts only a spent read grant.

-    Forget's PIN-grant requirement is not modelled here yet.
+    A grant must also name the owner and still be fresh; propose, confirm and correct accept
+    no PIN item at all.
     """
+    if pin is None:
+        return action != _FORGET_VALUE
+    scope, spent, kind = pin
+    wanted = _ORACLE_UNLOCK_SCOPE.get(action)
+    return wanted is not None and spent and scope == wanted and kind == "owner"
+
+
+def _oracle(
+    action: str, assurance: str, sensitivity: tuple[str, ...], consent: str, pin: Pin
+) -> tuple[str, str]:
+    """State the ADR's rule for an identified owner acting on their own personal data."""
     rank = _ORACLE_RANK[assurance]
     if "security" in sensitivity and rank < _ORACLE_RANK["strong"]:
         return "denied", "p0.5.assurance-required"
     if rank < _ORACLE_MIN_RANK[action]:
         return "denied", "cm1.personal-memory.assurance-required"
+    if not _grant_is_valid(action, pin):
+        return "denied", "cm1.personal-memory.grant-scope"
     needs_consent = action != _FORGET_VALUE and _ORACLE_SENSITIVE & set(sensitivity)
     if needs_consent and consent != "granted":
         return "denied", "cm1.personal-memory.consent-required"
@@ -643,19 +874,20 @@ def test_the_matrix_sizes_are_the_ones_the_adr_argues_over() -> None:
 @pytest.mark.parametrize("assurance", _ASSURANCE_VALUES)
 @pytest.mark.parametrize("action", _ACTION_VALUES)
 def test_the_owner_matrix_agrees_with_the_oracle_in_every_cell(action: str, assurance: str) -> None:
-    """127 sensitivity sets x 4 consents per (action, assurance): 7 620 cells in all."""
+    """127 sensitivity sets x 4 consents x 15 PIN states per (action, assurance)."""
     mismatches = [
-        (sensitivity, consent, got, want)
-        for sensitivity, consent in product(_SENSITIVITY_SUBSETS, _CONSENT_VALUES)
-        if (got := _owner_outcome(action, assurance, sensitivity, consent))
-        != (want := _oracle(action, assurance, sensitivity, consent))
+        (sensitivity, consent, pin, got, want)
+        for sensitivity, consent, pin in product(_SENSITIVITY_SUBSETS, _CONSENT_VALUES, _PIN_STATES)
+        if (got := _owner_outcome(action, assurance, sensitivity, consent, pin))
+        != (want := _oracle(action, assurance, sensitivity, consent, pin))
     ]

     assert not mismatches, mismatches[:3]
     if action == _FORGET_VALUE:  # erasure never depends on consent, revoked or not
-        for sensitivity in _SENSITIVITY_SUBSETS:
-            outcomes = {_owner_outcome(action, assurance, sensitivity, c) for c in _CONSENT_VALUES}
-            assert len(outcomes) == 1, sensitivity
+        for sensitivity, pin in product(_SENSITIVITY_SUBSETS, _PIN_STATES):
+            granted = _owner_outcome(action, assurance, sensitivity, "granted", pin)
+            for consent in _CONSENT_VALUES:
+                assert _owner_outcome(action, assurance, sensitivity, consent, pin) == granted


 def _gate_oracle(
@@ -666,8 +898,9 @@ def _gate_oracle(
 ) -> bool:
     """Allowed only for an identified owner on their own data of a reachable visibility.

-    Sensitivity is normal and consent granted in this sweep, so only the identity, target,
-    visibility and assurance gates can deny. Forget's PIN-grant rule is not modelled yet.
+    Sensitivity is normal and consent granted in this sweep, and every actor holds the grant
+    state its action needs (`_best_pin`), so only the identity, target, visibility and
+    assurance gates can deny.
     """
     role, status, assurance, _ = actor
     return (
@@ -703,9 +936,27 @@ def test_only_an_identified_owner_on_own_reachable_data_is_ever_allowed(action:
     for actor, target, visibility in product(
         actors, (None, _OWNER_ID, _OTHER_ID), _VISIBILITY_SUBSETS
     ):
-        status, _ = _matrix_outcome(action, actor, target, visibility, ("normal",), "granted")
+        status, _ = _matrix_outcome(
+            action, actor, target, visibility, ("normal",), "granted", _best_pin(action)
+        )
         want = _gate_oracle(action, actor, target, visibility)
         if (status == "allowed") != want or status == "requires_confirmation":
             mismatches.append((actor, target, visibility, status))

     assert not mismatches, mismatches[:3]
+
+
+def test_forget_is_never_allowed_to_any_actor_without_a_spent_forget_grant() -> None:
+    """18 actors x 3 targets x 63 visibility sets, face-only evidence: not one forget."""
+    allowed = [
+        (actor, target, visibility)
+        for actor, target, visibility in product(
+            _all_actors(), (None, _OWNER_ID, _OTHER_ID), _VISIBILITY_SUBSETS
+        )
+        if _matrix_outcome(_FORGET_VALUE, actor, target, visibility, ("normal",), "granted", None)[
+            0
+        ]
+        == "allowed"
+    ]
+
+    assert not allowed, allowed[:3]
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_personal_memory_policy.py tests/unit/test_personal_memory_grants.py tests/unit/test_identity_sessions.py tests/unit/test_owner_authentication.py tests/unit/test_biometric_admin_scope_callers.py tests/integration/test_owner_unlock_endpoint.py tests/integration/test_personal_memory_audit.py -q -p no:cacheprovider`
  Expected RED: 31 of the 102 tests of the policy file fail with `assert 'cm1.personal-memory.allowed'
  == 'cm1.personal-memory.grant-scope'` (with only the base grant rule and before the other-person and
  expiry check, five tests still failed for that reason: the two readable ones and three matrix
  cells); the grants, owner-authentication and unlock-endpoint files fail at
  collection with `AttributeError: type object 'OwnerUnlockScope' has no attribute
  'PERSONAL_MEMORY_READ'`; others with `AttributeError: 'IdentityEvidence' object has no attribute
  'grant_scope'` and `ValidationError ... grant_scope Extra inputs are not permitted`.
- [ ] **Step 3: Implement.**

```diff
diff --git a/server/src/server/cognition/authorization.py b/server/src/server/cognition/authorization.py
index 36ea82b..2093113 100644
--- a/server/src/server/cognition/authorization.py
+++ b/server/src/server/cognition/authorization.py
@@ -15,6 +15,8 @@ from server.cognition.identity import (
     ActivePersonStatus,
     HouseholdRole,
     IdentityAssurance,
+    IdentityEvidence,
+    IdentityEvidenceSource,
 )
 from server.cognition.models import (
     AuthorizationAction,
@@ -437,6 +439,39 @@ def _lacks_assurance(request: AuthorizationRequest, capability: PersonalMemoryCa
     return ASSURANCE_RANK[request.actor.assurance] < ASSURANCE_RANK[capability.min_assurance]


+def _is_invalid_grant(
+    item: IdentityEvidence, request: AuthorizationRequest, capability: PersonalMemoryCapability
+) -> bool:
+    """Return whether one `local_unlock` item cannot authorize this request.
+
+    It must carry the capability's own scope, have been spent by this request, name the
+    acting person and still be fresh at request time (ADR 0019 §4).
+    """
+    return (
+        capability.unlock_scope is None
+        or item.grant_scope != capability.unlock_scope
+        or not item.grant_spent
+        or item.candidate_person_id != request.actor.person_id
+        or (item.expires_at is not None and item.expires_at <= request.requested_at)
+    )
+
+
+def _has_invalid_grant(request: AuthorizationRequest, capability: PersonalMemoryCapability) -> bool:
+    """Return whether an owner PIN grant is missing where required or does not count.
+
+    Every `local_unlock` item must be valid for this capability; a capability with no scope
+    accepts no PIN grant at all.
+    """
+    grants = [
+        item
+        for item in request.actor.evidence
+        if item.source is IdentityEvidenceSource.LOCAL_UNLOCK
+    ]
+    if capability.requires_unlock and not grants:
+        return True
+    return any(_is_invalid_grant(item, request, capability) for item in grants)
+
+
 def _lacks_consent(request: AuthorizationRequest, capability: PersonalMemoryCapability) -> bool:
     """Return whether sensitive data is requested without granted consent."""
     return (
@@ -475,6 +510,13 @@ def _evaluate_personal_memory(
             "assurance-required",
             "This personal memory request needs stronger identity assurance.",
         )
+    if _has_invalid_grant(request, capability):
+        return _personal_memory_decision(
+            request,
+            AuthorizationStatus.DENIED,
+            "grant-scope",
+            "An owner unlock spent for exactly this operation is required.",
+        )
     if _lacks_consent(request, capability):
         return _personal_memory_decision(
             request,
diff --git a/server/src/server/cognition/identity.py b/server/src/server/cognition/identity.py
index c1edbb8..8f3c9d3 100644
--- a/server/src/server/cognition/identity.py
+++ b/server/src/server/cognition/identity.py
@@ -91,7 +91,14 @@ class PersonRecord:


 class IdentityEvidence(_BaseModel):
-    """Immutable, safe evidence supporting an identity candidate."""
+    """Immutable, safe evidence supporting an identity candidate.
+
+    Attributes:
+        grant_scope: For a `local_unlock` item, the operation its owner PIN grant was
+            issued for (ADR 0019 §4); `None` for any other source or an unscoped grant.
+        grant_spent: Whether this request spent the grant. A peeked grant names its owner
+            but is not spent; only a spent grant can authorize an operation.
+    """

     model_config = _ConfigDict(frozen=True, extra="forbid")

@@ -102,6 +109,8 @@ class IdentityEvidence(_BaseModel):
     observed_at: _StrictDatetime
     reference: str
     expires_at: _StrictDatetime | None = None
+    grant_scope: str | None = None
+    grant_spent: bool = False

     _validate_observed_at = _field_validator("observed_at")(require_aware_utc)
     _validate_expires_at = _field_validator("expires_at")(normalize_optional_aware_utc)
diff --git a/server/src/server/cognition/identity_sessions.py b/server/src/server/cognition/identity_sessions.py
index 2f6a2c5..345276d 100644
--- a/server/src/server/cognition/identity_sessions.py
+++ b/server/src/server/cognition/identity_sessions.py
@@ -147,6 +147,7 @@ class IdentitySessionRegistry:
             observed_at=observed_at,
             expires_at=observed_at + self._ttl,
             reference=_SELECTION_REFERENCE,
+            grant_scope=scope,
         )
         token = _uuid4().hex
         self._evidence_by_token[token] = evidence
@@ -166,9 +167,10 @@ class IdentitySessionRegistry:
                 never burns it.

         Returns:
-            The evidence if the token was present, within ``scope`` and unexpired, else
-            ``None``. A token that is within ``scope`` is removed either way — a second
-            call with the same token always returns ``None``.
+            The evidence, marked ``grant_spent``, if the token was present, within
+            ``scope`` and unexpired, else ``None``. A token that is within ``scope`` is
+            removed either way — a second call with the same token always returns
+            ``None``. The stored item is never mutated: only the returned copy is spent.
         """
         # Spending fails closed: the asked scope must equal the recorded one, so a token
         # bound to an operation is never redeemed by a caller that names none.
@@ -180,7 +182,7 @@ class IdentitySessionRegistry:
             return None
         if evidence.expires_at is not None and evidence.expires_at <= self._clock():
             return None
-        return evidence
+        return evidence.model_copy(update={"grant_spent": True})


 # Compatibility for the implementation name used before Plan 0002 review.
diff --git a/server/src/server/cognition/owner_authentication.py b/server/src/server/cognition/owner_authentication.py
index 36e7c79..0741b50 100644
--- a/server/src/server/cognition/owner_authentication.py
+++ b/server/src/server/cognition/owner_authentication.py
@@ -85,10 +85,16 @@ class OwnerUnlockScope(StrEnum):
         PERSONAL_PROTECTED_READ: One protected read of the owner's confirmed child data
             (the default, so every existing client is unchanged).
         BIOMETRIC_ADMIN: Enrolling or revoking the owner's face or voice.
+        PERSONAL_MEMORY_READ: Reading the owner's own personal conversation memory
+            (ADR 0019). It does not unlock child data and the child-data grant does not
+            unlock it.
+        PERSONAL_MEMORY_FORGET: One erasure of the owner's own personal memory (ADR 0019).
     """

     PERSONAL_PROTECTED_READ = "personal_protected_read"
     BIOMETRIC_ADMIN = "biometric_admin"
+    PERSONAL_MEMORY_READ = "personal_memory_read"
+    PERSONAL_MEMORY_FORGET = "personal_memory_forget"


 class OwnerUnlockResult(BaseModel):
diff --git a/server/src/server/schemas_auth.py b/server/src/server/schemas_auth.py
index 8a3769f..b291cc9 100644
--- a/server/src/server/schemas_auth.py
+++ b/server/src/server/schemas_auth.py
@@ -51,7 +51,9 @@ class OwnerUnlockRequest(BaseModel):
         Field(
             description=(
                 "The one operation the grant may authorize: `personal_protected_read` "
-                "(the default) or `biometric_admin` (face or voice enrolment and revocation)."
+                "(the default), `biometric_admin` (face or voice enrolment and revocation), "
+                "`personal_memory_read` (read the owner's own conversation memory) or "
+                "`personal_memory_forget` (one erasure of the owner's own memory)."
             )
         ),
     ] = OwnerUnlockScope.PERSONAL_PROTECTED_READ
```

- [ ] **Step 4: Run, lint, commit.** The same command passes, plus the characterization test and the
  rest of `tests/unit/test_identity_fusion.py`; `ruff check` and `ruff format --check` over the
  touched paths; `uv run mypy server/src robot/src`; commit
  `feat(server): bind personal-memory grants to their scope (plan 0060)`. Note that a real `unlock`
  costs about 2.5 s of scrypt; the new tests build grants from the registry directly.

---

## Task 7: Guards and invariants

**Files:**
- Test: `tests/unit/test_architecture_guards.py`, new `tests/unit/test_identity_assurance_invariants.py`

**Interfaces:**
- Consumes: the AST-walk-plus-self-test pattern of the existing guards.
- Produces: six guards with one shared self-test, and an invariant sweep with a voice test and
  its own self-test (10 tests in all). In `server/src`: (1) the five new action names and
  value strings appear only in `cognition/models.py` and `cognition/authorization.py`, including
  as a string constant (`AuthorizationAction["FORGET_PERSONAL_MEMORY"]`, `getattr(...)`); (2)
  `PROPOSE_MEMORY`, `COMMIT_MEMORY`, `DELETE_HOUSEHOLD_DATA` and `EXPORT_HOUSEHOLD_DATA` (members and
  value strings) appear only in those two files (the ADR does not retire them: CM-3 decides); (3) the
  member names of the two new scopes appear only in `owner_authentication.py`, and their exact string
  values only in `owner_authentication.py` and `authorization.py`; (4) `select_person` has no call;
  (5) `IdentityEvidenceSource.MANUAL` is referenced only in the five modules that reference it today
  (`characters/__init__.py`, `cognition/identity.py`, `cognition/identity_sessions.py`,
  `memory/consolidation.py`, `text_turn.py`) and `issue_for_person` is never called with it;
  (6) `grant_spent` and `grant_scope` are read and written only in `cognition/identity.py`,
  `cognition/identity_sessions.py` and `cognition/authorization.py`. A
  self-test proves a synthetic offender trips each guard and a synthetic home module and a docstring do not.
  The sweep runs the 63 non-empty subsets of the six evidence sources through the real
  `resolve_active_person` and asserts that `strong` implies a `local_unlock` item or a face and a
  voice, that identified-at-`basic` implies a manual, local-unlock or face item, that a non-identified
  result carries `none`, and that an identified one never does.

- [ ] **Step 1: Write the guards and the sweep:**

```diff
diff --git a/tests/unit/test_architecture_guards.py b/tests/unit/test_architecture_guards.py
index cebb0e5..ac23b51 100644
--- a/tests/unit/test_architecture_guards.py
+++ b/tests/unit/test_architecture_guards.py
@@ -121,3 +121,195 @@ def test_the_aware_utc_check_is_defined_once() -> None:
     ]

     assert copies == ["cognition/models.py"]
+
+
+# --- Plan 0060: personal-memory capabilities are policy only (ADR 0019 §6) ---------------
+
+_NEW_ACTION_NAMES = frozenset(
+    {
+        "READ_PERSONAL_CONVERSATION_MEMORY",
+        "PROPOSE_PERSONAL_MEMORY",
+        "CONFIRM_PERSONAL_MEMORY",
+        "CORRECT_PERSONAL_MEMORY",
+        "FORGET_PERSONAL_MEMORY",
+        "read_personal_conversation_memory",
+        "propose_personal_memory",
+        "confirm_personal_memory",
+        "correct_personal_memory",
+        "forget_personal_memory",
+    }
+)
+# CM-3 decides what happens to these four; until then only the model and the policy know them.
+_LEGACY_MEMORY_ACTION_NAMES = frozenset(
+    {
+        "PROPOSE_MEMORY",
+        "COMMIT_MEMORY",
+        "DELETE_HOUSEHOLD_DATA",
+        "EXPORT_HOUSEHOLD_DATA",
+        "propose_memory",
+        "commit_memory",
+        "delete_household_data",
+        "export_household_data",
+    }
+)
+_ACTION_HOMES = frozenset({"cognition/models.py", "cognition/authorization.py"})
+_MEMORY_SCOPE_MEMBER_NAMES = frozenset({"PERSONAL_MEMORY_READ", "PERSONAL_MEMORY_FORGET"})
+_MEMORY_SCOPE_VALUES = frozenset({"personal_memory_read", "personal_memory_forget"})
+# Only the enum names its members. The policy table repeats the plain strings because
+# importing the enum there would be an import cycle (a drift test pins them together).
+_SCOPE_MEMBER_HOMES = frozenset({"cognition/owner_authentication.py"})
+_SCOPE_VALUE_HOMES = frozenset({"cognition/owner_authentication.py", "cognition/authorization.py"})
+# `manual` evidence counts as `basic`; these are the modules that reference it today (grep on
+# 2026-10-08). A new one must be a decision, not an accident.
+_MANUAL_HOMES = frozenset(
+    {
+        "characters/__init__.py",
+        "cognition/identity.py",
+        "cognition/identity_sessions.py",
+        "memory/consolidation.py",
+        "text_turn.py",
+    }
+)
+_GRANT_FIELD_NAMES = frozenset({"grant_spent", "grant_scope"})
+_GRANT_FIELD_HOMES = frozenset(
+    {"cognition/identity.py", "cognition/identity_sessions.py", "cognition/authorization.py"}
+)
+
+
+def _outside(sources: Mapping[str, str], homes: frozenset[str], names: frozenset[str]) -> list[str]:
+    """Modules, besides `homes`, that reference any of `names`.
+
+    A reference is an attribute access, a bare name or a keyword argument equal to a name, or
+    a string constant equal to one (so `Enum["NAME"]` and `getattr(Enum, "NAME")` count).
+    Prose inside a longer string is not a reference.
+    """
+    found = set()
+    for module, text in sources.items():
+        for node in ast.walk(ast.parse(text)):
+            if (
+                (isinstance(node, ast.Attribute) and node.attr in names)
+                or (isinstance(node, ast.Name) and node.id in names)
+                or (isinstance(node, ast.keyword) and node.arg in names)
+                or (isinstance(node, ast.Constant) and node.value in names)
+            ):
+                found.add(module)
+    return sorted(found - homes)
+
+
+def _calls(sources: Mapping[str, str], method: str) -> list[str]:
+    """Modules that call `method` (a definition is not a call)."""
+    return [
+        name
+        for name, text in sources.items()
+        if any(
+            isinstance(node, ast.Call)
+            and (
+                (isinstance(node.func, ast.Attribute) and node.func.attr == method)
+                or (isinstance(node.func, ast.Name) and node.func.id == method)
+            )
+            for node in ast.walk(ast.parse(text))
+        )
+    ]
+
+
+def _issued_as_manual(sources: Mapping[str, str]) -> list[str]:
+    """Modules that call `issue_for_person` with a `...MANUAL` source."""
+    return [
+        name
+        for name, text in sources.items()
+        if any(
+            isinstance(node, ast.Call)
+            and isinstance(node.func, ast.Attribute)
+            and node.func.attr == "issue_for_person"
+            and any(
+                keyword.arg == "source"
+                and any(
+                    isinstance(inner, ast.Attribute) and inner.attr == "MANUAL"
+                    for inner in ast.walk(keyword.value)
+                )
+                for keyword in node.keywords
+            )
+            for node in ast.walk(ast.parse(text))
+        )
+    ]
+
+
+@pytest.mark.unit
+def test_the_personal_memory_actions_exist_only_in_the_model_and_the_policy() -> None:
+    """Nothing is wired: no route, store or prompt names a personal-memory action yet."""
+    assert _outside(_sources(), _ACTION_HOMES, _NEW_ACTION_NAMES) == []
+
+
+@pytest.mark.unit
+def test_the_legacy_memory_actions_are_used_only_by_the_model_and_the_policy() -> None:
+    """Nobody else consumes `propose_memory`, `commit_memory`, delete or export (verified)."""
+    assert _outside(_sources(), _ACTION_HOMES, _LEGACY_MEMORY_ACTION_NAMES) == []
+
+
+@pytest.mark.unit
+def test_the_personal_memory_unlock_scopes_have_no_consumer_yet() -> None:
+    sources = _sources()
+
+    assert _outside(sources, _SCOPE_MEMBER_HOMES, _MEMORY_SCOPE_MEMBER_NAMES) == []
+    assert _outside(sources, _SCOPE_VALUE_HOMES, _MEMORY_SCOPE_VALUES) == []
+
+
+@pytest.mark.unit
+def test_nothing_in_the_server_selects_a_person_by_manual_session() -> None:
+    """`select_person` mints `manual` evidence, which counts as `basic`; it has no caller."""
+    assert _calls(_sources(), "select_person") == []
+
+
+@pytest.mark.unit
+def test_manual_evidence_is_referenced_only_where_it_is_today_and_never_issued_as_a_grant() -> None:
+    sources = _sources()
+
+    assert _outside(sources, _MANUAL_HOMES, frozenset({"MANUAL"})) == []
+    assert _issued_as_manual(sources) == []
+
+
+@pytest.mark.unit
+def test_the_grant_fields_are_read_and_written_only_by_the_identity_and_policy_modules() -> None:
+    assert _outside(_sources(), _GRANT_FIELD_HOMES, _GRANT_FIELD_NAMES) == []
+
+
+@pytest.mark.unit
+def test_the_personal_memory_guards_detect_a_violation() -> None:
+    """Each guard flags a synthetic offender and spares a synthetic home."""
+    leak = {
+        "routers/leak.py": (
+            "from server.cognition.models import AuthorizationAction\n"
+            "a = AuthorizationAction.FORGET_PERSONAL_MEMORY\n"
+            "b = AuthorizationAction.COMMIT_MEMORY\n"
+            "c = OwnerUnlockScope.PERSONAL_MEMORY_FORGET\n"
+            'd = "read_personal_conversation_memory"\n'
+            'e = "delete_household_data"\n'
+            'f = "personal_memory_read"\n'
+            "g = registry.select_person(7)\n"
+            "h = IdentityEvidenceSource.MANUAL\n"
+            "i = registry.issue_for_person(person, source=IdentityEvidenceSource.MANUAL)\n"
+            'j = evidence.model_copy(update={"grant_spent": True})\n'
+            'k = Evidence(grant_scope="personal_memory_forget")\n'
+        ),
+        "routers/subscript.py": 'x = AuthorizationAction["FORGET_PERSONAL_MEMORY"]\n',
+        "routers/getattr.py": 'x = getattr(AuthorizationAction, "FORGET_PERSONAL_MEMORY")\n',
+        "routers/scope_getattr.py": 'x = getattr(OwnerUnlockScope, "PERSONAL_MEMORY_READ")\n',
+        "cognition/authorization.py": "x = AuthorizationAction.FORGET_PERSONAL_MEMORY\ny = 1\n",
+        "prose.py": '"""Forgetting uses forget_personal_memory in prose, which is not a reference."""\n',
+    }
+
+    assert _outside(leak, _ACTION_HOMES, _NEW_ACTION_NAMES) == [
+        "routers/getattr.py",
+        "routers/leak.py",
+        "routers/subscript.py",
+    ]
+    assert _outside(leak, _ACTION_HOMES, _LEGACY_MEMORY_ACTION_NAMES) == ["routers/leak.py"]
+    assert _outside(leak, _SCOPE_MEMBER_HOMES, _MEMORY_SCOPE_MEMBER_NAMES) == [
+        "routers/leak.py",
+        "routers/scope_getattr.py",
+    ]
+    assert _outside(leak, _SCOPE_VALUE_HOMES, _MEMORY_SCOPE_VALUES) == ["routers/leak.py"]
+    assert _outside(leak, _MANUAL_HOMES, frozenset({"MANUAL"})) == ["routers/leak.py"]
+    assert _outside(leak, _GRANT_FIELD_HOMES, _GRANT_FIELD_NAMES) == ["routers/leak.py"]
+    assert _calls(leak, "select_person") == ["routers/leak.py"]
+    assert _issued_as_manual(leak) == ["routers/leak.py"]
diff --git a/tests/unit/test_identity_assurance_invariants.py b/tests/unit/test_identity_assurance_invariants.py
new file mode 100644
index 0000000..d6cac44
--- /dev/null
+++ b/tests/unit/test_identity_assurance_invariants.py
@@ -0,0 +1,151 @@
+"""Invariants of identity fusion that the personal-memory policy leans on (ADR 0019 §3).
+
+The policy compares assurance by rank and trusts `strong` to mean "face and voice agreeing,
+or an owner unlock". These tests sweep every combination of evidence sources for one person
+through the real `resolve_active_person` and check that no combination breaks that meaning.
+"""
+
+from datetime import UTC, datetime
+from itertools import combinations
+from uuid import UUID
+
+import pytest
+from server.cognition.identity import (
+    ActivePersonStatus,
+    HouseholdRole,
+    IdentityAssurance,
+    IdentityEvidence,
+    IdentityEvidenceSource,
+    PersonRecord,
+    resolve_active_person,
+)
+from server.cognition.models import Confidence, ConfidenceBasis
+
+pytestmark = pytest.mark.unit
+
+_NOW = datetime(2026, 10, 8, 12, tzinfo=UTC)
+_PERSON = PersonRecord(person_id=42, display_name="Ada", entity_type="person")
+_SOURCES = (
+    IdentityEvidenceSource.SESSION,
+    IdentityEvidenceSource.MANUAL,
+    IdentityEvidenceSource.FACE,
+    IdentityEvidenceSource.VOICE,
+    IdentityEvidenceSource.CONTEXT,
+    IdentityEvidenceSource.LOCAL_UNLOCK,
+)
+_BASIC_SOURCES = frozenset(
+    {
+        IdentityEvidenceSource.MANUAL,
+        IdentityEvidenceSource.LOCAL_UNLOCK,
+        IdentityEvidenceSource.FACE,
+    }
+)
+_FACE_AND_VOICE = frozenset({IdentityEvidenceSource.FACE, IdentityEvidenceSource.VOICE})
+
+
+def _subsets() -> tuple[frozenset[IdentityEvidenceSource], ...]:
+    """Every non-empty subset of the six evidence sources (63)."""
+    return tuple(
+        frozenset(subset)
+        for size in range(1, len(_SOURCES) + 1)
+        for subset in combinations(_SOURCES, size)
+    )
+
+
+def _evidence(source: IdentityEvidenceSource) -> IdentityEvidence:
+    return IdentityEvidence(
+        evidence_id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
+        source=source,
+        candidate_person_id=_PERSON.person_id,
+        confidence=Confidence(score=1.0, basis=ConfidenceBasis.ASSERTED, calibrated=True),
+        observed_at=_NOW,
+        reference="canary",
+    )
+
+
+def _resolve(
+    sources: frozenset[IdentityEvidenceSource],
+) -> tuple[ActivePersonStatus, IdentityAssurance]:
+    context = resolve_active_person(
+        evidence=tuple(_evidence(source) for source in _SOURCES if source in sources),
+        lookup_person=lambda person_id: _PERSON if person_id == _PERSON.person_id else None,
+        lookup_role=lambda _person_id: HouseholdRole.OWNER,
+        clock=lambda: _NOW,
+    )
+    return context.status, context.assurance
+
+
+def _violations(
+    sources: frozenset[IdentityEvidenceSource],
+    status: ActivePersonStatus,
+    assurance: IdentityAssurance,
+) -> list[str]:
+    """Name every invariant that (sources, status, assurance) breaks."""
+    broken = []
+    if assurance is IdentityAssurance.STRONG and not (
+        IdentityEvidenceSource.LOCAL_UNLOCK in sources or sources >= _FACE_AND_VOICE
+    ):
+        broken.append("strong without an unlock or face and voice")
+    if (
+        status is ActivePersonStatus.IDENTIFIED
+        and assurance is IdentityAssurance.BASIC
+        and not sources & _BASIC_SOURCES
+    ):
+        broken.append("basic without a manual, unlock or face source")
+    if status is not ActivePersonStatus.IDENTIFIED and assurance is not IdentityAssurance.NONE:
+        broken.append("assurance on a result that did not identify")
+    if status is ActivePersonStatus.IDENTIFIED and assurance is IdentityAssurance.NONE:
+        broken.append("identified without any assurance")
+    return broken
+
+
+def test_no_combination_of_sources_breaks_the_assurance_invariants() -> None:
+    """63 source sets for one person: strong, basic and none each mean what the ADR says."""
+    subsets = _subsets()
+    assert len(subsets) == 63
+
+    broken = {
+        tuple(sorted(source.value for source in sources)): problems
+        for sources in subsets
+        if (problems := _violations(sources, *_resolve(sources)))
+    }
+
+    assert broken == {}
+
+
+def test_a_voice_never_identifies_and_never_lifts_a_session_selection() -> None:
+    assert _resolve(frozenset({IdentityEvidenceSource.VOICE})) == (
+        ActivePersonStatus.PROBABLE,
+        IdentityAssurance.NONE,
+    )
+    assert _resolve(frozenset({IdentityEvidenceSource.SESSION, IdentityEvidenceSource.VOICE})) == (
+        ActivePersonStatus.PROBABLE,
+        IdentityAssurance.NONE,
+    )
+    assert _resolve(frozenset({IdentityEvidenceSource.CONTEXT})) == (
+        ActivePersonStatus.UNKNOWN,
+        IdentityAssurance.NONE,
+    )
+
+
+def test_the_invariant_check_detects_a_violation() -> None:
+    """A green sweep means something: synthetic bad results are flagged, good ones are not."""
+    identified = ActivePersonStatus.IDENTIFIED
+    strong, basic, none = (
+        IdentityAssurance.STRONG,
+        IdentityAssurance.BASIC,
+        IdentityAssurance.NONE,
+    )
+
+    assert _violations(frozenset({IdentityEvidenceSource.FACE}), identified, strong)
+    assert _violations(frozenset({IdentityEvidenceSource.VOICE}), identified, basic)
+    assert _violations(
+        frozenset({IdentityEvidenceSource.SESSION}), ActivePersonStatus.PROBABLE, basic
+    )
+    assert _violations(frozenset({IdentityEvidenceSource.FACE}), identified, none)
+    assert not _violations(frozenset({IdentityEvidenceSource.LOCAL_UNLOCK}), identified, strong)
+    assert not _violations(_FACE_AND_VOICE, identified, strong)
+    assert not _violations(frozenset({IdentityEvidenceSource.FACE}), identified, basic)
+    assert not _violations(
+        frozenset({IdentityEvidenceSource.SESSION}), ActivePersonStatus.PROBABLE, none
+    )
```

- [ ] **Step 2: Run them.**
  `uv run pytest tests/unit/test_architecture_guards.py tests/unit/test_identity_assurance_invariants.py -q -p no:cacheprovider`
  passes (10 new tests): the surface really has no consumer today. They are green on arrival.
- [ ] **Step 3: Prove they bite (mutation).** In a throwaway file under `server/src/server/` reference
  a new action only through `getattr(AuthorizationAction, "FORGET_PERSONAL_MEMORY")`: the new-actions
  guard fails. Then reference a legacy memory action, a scope member, a scope value,
  `select_person(7)`, a MANUAL-sourced `issue_for_person` and `grant_spent`: five guards fail. Then
  make `_assurance_for` return `STRONG` for any trusted source: the sweep fails naming 16 source sets.
  Revert all and confirm `git diff` is empty.
- [ ] **Step 4: Lint and commit.** `ruff check` and `ruff format --check` over both files; commit
  `test(server): guard the personal-memory policy boundary (plan 0060)`.

---

## Task 8: Real runtime acceptance

Pipec runs this; you record outcomes only. Nothing consumes the new capabilities, so there is no
spoken turn to try. With `just run-server` running and the PIN typed by Pipec at his own terminal (it
is never written down or logged):

- [ ] **Step 1:** an unlock with `scope: "personal_memory_read"` returns 200 and echoes the scope.
- [ ] **Step 2:** an unlock with `scope: "personal_memory_forget"` returns 200 and echoes the scope.
- [ ] **Step 3:** an unlock with an unknown scope returns 422 and the body does not contain the PIN.
- [ ] **Step 4:** an unlock with no scope still returns the default `personal_protected_read`, and a
  normal voice turn (and a "mis hijos" question when the owner is identified) behaves as before.

Record the four outcomes in `docs/evals/0060-personal-memory-capabilities-acceptance.md` and index it
in `docs/evals/README.md`.

---

## Task 9: Documentation truth

- [ ] **Step 1:** ADR 0019 `Status` to `Accepted` with the date and the measurement (gate, test
  counts); `docs/adr/README.md` row to `Accepted`; ADR 0015 status line gains "decision 1's scope set
  extended by [0019]" and ADR 0016 "§3 refined by [0019]" (one sentence each, no other edit).
- [ ] **Step 2:** `docs/architecture/identity-and-access.md`: the scope paragraph that says the set "has
  two members" (now four, with the meaning of each), the assurance paragraph (a capability may declare
  a minimum above the category floor) and the role matrix rows for the five capabilities.
- [ ] **Step 3:** `docs/architecture/current-state.md` capability matrix: the "Scoped owner grants" row
  and the rows that list the scopes gain the two new ones; a new row "Personal-memory capabilities:
  defined as policy, not connected". `docs/runbooks/operator-manual.md`: the places that list the unlock
  scopes.
- [ ] **Step 4:** regenerate the Archify diagram (`docs/architecture/diagrams/current-state.{json,html}`)
  with validate then deliver, as the project requires after an architecture-document edit.
- [ ] **Step 5:** roadmap CM-1 rows, the memory map row and header, `docs/architecture/README.md`,
  `docs/plans/README.md` (move this plan to `CLOSED`, `NOW` empty, next free number 0061),
  `docs/plans/open/README.md` and `docs/plans/completed/README.md` (add the closure entry); move this
  plan to `docs/plans/completed/` and repoint **every** `plans/open/0060-…` link to `completed/`:
  ADR 0019 (three places), the roadmap (two), the memory map, the plan indexes and
  `docs/architecture/README.md`.
- [ ] **Step 6:** update the local, git-excluded `docs/roadmap/tabla-tareas.md` (never commit it).
- [ ] **Step 7:** `uv run python scripts/check_reserved_terms.py`, a relative-link check over the edited
  documents, `uv run ruff format --check .` (CI formats the Python blocks of the markdown) and
  `git diff --check`.

---

## Non-goals

Each exclusion has an owner.

- Any store, writer, route, spoken confirmation or controller branch for the five capabilities: CM-3
  (candidates, the single writer, the confirmation dialogue) and the plan that wires each one.
- Retrieval of personal memory into the prompt and its relevance filter: CM-5.
- The real reach of forgetting (facts, relations, episodes, embeddings, summaries, caches): CM-6.
- Identity in generic turns, so a `forget` is reachable when the owner's face matches: the CM-2 ADR
  that revises ADR 0016 §5.
- A shorter lifetime for the forget grant and a `personal_memory_confirm` scope: the plan that wires
  those capabilities.
- Retiring `PROPOSE_MEMORY` and `COMMIT_MEMORY`: CM-3.
- The family profile (an adult's own memory, household memory by consent) and the permissive
  `READ_HOUSEHOLD_DATA` rule for `personal` visibility: a family-profile ADR.
- A real consent record: unplanned (a consent-store plan, needed before the family profile).
  Speaker binding of the grant: ADR 0015 decision 2, staged behind later evidence. Liveness and
  replay defence: unplanned follow-ups of PC-4.
- Changing the V4 reader, the robot, the audit schema or any setting.

## Verification

```text
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

- Explicit-path ruff over every touched file (`just lint` skips `scripts/`, the hook does not).
- The CI command with coverage:
  `uv run pytest -m "not slow and not hardware and not eval" --cov=server/src --cov=robot/src --cov-report=term --cov-fail-under=80`.
- `just gate` last; record the test count (rehearsal: +174 under the CI filter).
- `git diff --stat main -- robot` must be empty; `git diff --stat main -- server/src` must list only
  the six production files of *Permitted files*.

## Completion criteria

- Task 1: the 23 characterization tests pass on the unchanged code and bite under mutation.
- Task 2: the enum snapshot lists the five actions; the characterization is unchanged.
- Task 3: the capability table, the rank and the drift tests exist and pass.
- Task 4: the evaluator returns the fixed-order decisions with `cm1.personal-memory.*` ids, never
  `requires_confirmation`, and the audit table stores the new action names.
- Task 5: the oracle matrix passes and fails under the `forget` minimum mutation.
- Task 6: a read, default or administration grant cannot forget, a peeked grant authorizes nothing, a
  face-and-voice owner cannot forget, a grant for another person or an expired one never counts,
  `confirm` is reachable only through face and voice, the unlock endpoint accepts and echoes the two
  new scopes, OpenAPI lists four.
- Task 7: the six guards and the invariant sweep pass and bite under mutation.
- Task 8: Pipec's four unlock outcomes are recorded.
- Task 9: ADR 0019 is `Accepted`, the matrices and the diagram are current, the plan is under
  `completed/`, `git diff --stat main -- robot` is empty and `just gate` is green.

## Real runtime acceptance

Task 8 only: the unlock endpoint with the new scopes, by Pipec. No spoken-turn acceptance applies
because nothing consumes the capabilities.

## Rollback

Revert the squash-merged PR as one unit. The only wire change is two additive enum values on the
unlock endpoint; there is no migration, no new dependency and no setting, and the robot is untouched.
Existing audit rows are unaffected (the action column is free text).

## Execution record

(Empty until the plan is executed.)

## Closure

(Empty until the plan is closed.)
