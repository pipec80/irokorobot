# 0019 — Authorize personal memory by named capability, assurance and grant scope

- **Status:** Proposed (2026-10-08) — becomes Accepted when
  [Plan 0060](../plans/open/0060-cm1-personal-memory-capabilities.md) closes; until then nothing
  in `server/src` follows it
- **Date:** 2026-10-08
- **Builds on:** [ADR 0009](0009-locked-posture-and-scoped-capabilities.md),
  [ADR 0015](0015-owner-grant-scope-and-speaker-binding.md),
  [ADR 0016](0016-face-and-voice-identity-fusion.md)
- **Refines:** ADR 0015 decision 1 (the closed scope set gains `personal_memory_read` and
  `personal_memory_forget`; `personal_protected_read` keeps meaning one read of confirmed
  `child_data`) and ADR 0016 §3 (a capability may declare a minimum assurance above the category
  floor, and biometric, medical and location data raise it to `strong` for these capabilities).
  Nothing is superseded.
- **Implemented by:** [Plan 0060](../plans/open/0060-cm1-personal-memory-capabilities.md)

## Context

[Plan 0051](../plans/completed/0051-scoped-owner-grants.md) bound every owner grant to one named
operation and ended with "CM-1 stays open for the memory capabilities". The
[conversational-memory map](../roadmap/conversational-memory-delivery-map.md) names the minimum
capabilities: `read_personal_conversation_memory`, `propose_personal_memory`,
`confirm_personal_memory`, `correct_personal_memory` and `forget_personal_memory`. At drafting
(2026-10-08) none of them exists in code. What exists is coarser:

- `READ_HOUSEHOLD_DATA` and `EXECUTE_HOUSEHOLD_TOOL` read household data;
- `PROPOSE_MEMORY` lets an owner through whatever the data class (except `SECURITY`, which the
  generic assurance rule denies first), and `COMMIT_MEMORY` and `DELETE_HOUSEHOLD_DATA` are
  owner-only administration with no notion of whose data, which sensitivity, or how strongly the
  owner was identified (`cognition/authorization.py`).

**What the code serves.** `PolicyGatedV4Reader` serves **household data only**: all ten predicates
of `memory/predicate_registry.py` carry visibility `household`, every v4 writer stores that
default, and the reader withholds a row stored under another label. Its one live read is
`child_of` ("mis hijos"). No production path reads personal or conversational memory with an
`AuthorizationAction`: the turn memory is gated by `MANUAL` identity evidence, which no production
code produces, so it logs "Turn memory: skipped". There is therefore **nothing to connect** to the
new capabilities, and this ADR connects nothing.

**Facts the design has to respect.**

1. The policy is a pure function of a request. The routers build one request-wide owner resolver
   with the default read scope before the intent is classified (`chat.py`, `transcribe.py`), and a
   spent PIN grant yields `strong` assurance and granted consent (`identity.py::_assurance_for`,
   `OwnerRequestResolver.resolve_consent`). A future forget branch that reused that resolver would
   receive an actor with `strong` and granted consent produced by a **read** grant, against ADR 0009
   ("a read grant is not permission to modify memory"). Today the spent flag is visible to the
   policy only through `consent`, and a peeked (unspent) grant yields the same actor as a spent
   one.
2. `IdentityAssurance` is a `str` enum. `basic < none < strong` holds alphabetically; comparing the
   members with `<` or `>=` is wrong for `none`.
3. `strong` is reachable by a face and a verified voice of the same person (only where
   `SPEAKER_AUTHENTICATION_ENABLED` is on and the owner's voice is enrolled; it defaults to off) or
   by a PIN grant. When the owner's face identifies the turn, a presented PIN is not consulted
   (ADR 0016 §5). Face and voice are both replayable (ADR 0016 §9: a photograph; six of eight
   replay probes accepted), the PIN is not.
4. `ActivePersonContext.evidence` is the tuple of items the resolvers received, and `assurance` is
   computed from it by the resolvers. The policy trusts contexts the resolvers build.
5. `PROPOSE_MEMORY` returns `requires_confirmation` for adults and children, and
   `READ_HOUSEHOLD_DATA` already allows an owner (and any role except unknown) to read their own
   `personal`/`normal` data. Both are pinned today and are not the model for what follows.

## Decision

### 1. Five new closed actions; the old ones do not change

`AuthorizationAction` gains `read_personal_conversation_memory`, `propose_personal_memory`,
`confirm_personal_memory`, `correct_personal_memory` and `forget_personal_memory`, with the names
the memory map uses. The eleven existing actions keep their exact decisions (a characterization
guard pins them over a fixed grid). `PROPOSE_MEMORY` and `COMMIT_MEMORY` stay as they are and the
plan that introduces the single writer (CM-3) decides whether to retire them; **no new code may
use them, or `DELETE_HOUSEHOLD_DATA` or `EXPORT_HOUSEHOLD_DATA`, for personal memory** (an
architecture guard pins it). Personal-visibility data is authorized through the five new actions
only. `READ_HOUSEHOLD_DATA` with `personal` visibility is pre-existing behaviour, pinned and not to
be used for personal memory; the family-profile ADR revisits it.

### 2. Owner only, own data only

A personal-memory capability is evaluated only for an identified owner acting on data that is
**the owner's own**: `target_person_id` equal to the actor's person id (a missing target never
matches) and a visibility inside the capability's set: `personal` for read, propose, confirm and
correct; `personal`, `private` or `temporary` for forget, because erasure must reach whatever a
writer can store under the owner's name. Adults, children, guests and unknown actors are denied;
for these five actions the answer is `denied`, never `requires_confirmation`. Family-profile rules
(an adult's own memory, household memory by consent) are later work and need their own ADR.

### 3. Assurance, consent and grant are declared per capability

| Capability | Minimum assurance | Consent for sensitive categories | PIN route |
|---|---|---|---|
| `read_personal_conversation_memory` | `basic` | required | a spent `personal_memory_read` grant counts; any other PIN grant does not |
| `propose_personal_memory` | `basic` | required | none: only non-PIN evidence (face, face and voice) counts |
| `confirm_personal_memory` | `strong` | required | none, as above: only face and a verified voice reach `strong` here |
| `correct_personal_memory` | `basic` | required | none, as above |
| `forget_personal_memory` | `strong` | **not applied** | **required**: a spent `personal_memory_forget` grant; face and voice alone never suffice |

- The assurance of an actor is compared by an explicit rank (`none` 0, `basic` 1, `strong` 2),
  never by `<`. The existing rule that `SECURITY` data needs `strong` (ADR 0016 §3,
  `HIGH_ASSURANCE_CATEGORIES`) runs first, for every action, and keeps its `p0.5.assurance-required`
  id; there is no per-category assurance table. The sensitive set that requires consent is the
  existing one (`biometric`, `medical`, `location`, `child_data`, `security`); a drift test fails
  when a `DataSensitivity` member is classified in neither place.
- **Biometric, medical and location data raise the minimum to `strong` for every personal-memory
  capability** (Pipec, 2026-10-09), through one constant, `PERSONAL_MEMORY_STRONG_CATEGORIES`. The
  face resolver grants consent to any identified owner, so without this a photograph of the owner
  would reach health, location and biometric memory at `basic`. `child_data` stays at the
  capability's minimum, because ADR 0016 §1 already accepts the owner's face for the child read.
  The constant does not touch `HIGH_ASSURANCE_CATEGORIES`, so the eleven old actions do not move.
  Consequences: such data is read through a verified voice or a spent `personal_memory_read` grant,
  and `propose` and `correct` reach it only through face and a verified voice (they have no PIN
  route).
- "Consent required" means `ConsentStatus.granted` strictly: `not_required`, `missing` and
  `revoked` all deny on a sensitive category. Today the resolvers produce only `granted` or
  `not_required`.
- `confirm` is `strong` because it is the commit point that turns a proposal into the owner's
  truth: with the face alone, a photograph or a second person speaking beside the owner (the face
  is in frame, the voice is not checked) could have their words attributed to the owner's memory.
  The voice of the same person is what separates the owner's utterance from the bystander's.
  `propose` and `correct` stay at `basic` because neither establishes truth on its own: a proposal
  is only a candidate until confirmed, and a correction must supersede and keep the prior version
  (wiring obligation 5).
- `forget` is `strong` because deleting is not undone. `strong` narrows replay but does not close it
  (ADR 0016 §9), so `forget` also requires the one factor a photograph or a recording cannot supply,
  a spent forget grant; the wiring plan must add a fresh explicit confirmation turn
  (`identity-and-access.md`: "require stronger identity and explicit confirmation"). It is exempt
  from the consent rule because withdrawing consent is a reason to erase: a revoked or missing
  consent must never block erasure.

### 4. The scope and the spent state travel in the evidence

`IdentityEvidence` gains two additive fields: `grant_scope: str | None` (the operation a
`local_unlock` item was issued for) and `grant_spent: bool` (set only when the registry redeems the
token). The registry records the scope on issue, returns the stored item unchanged to a peek, and
returns a copy with `grant_spent` true when it consumes the token. The policy reads the
`local_unlock` items of `actor.evidence`: every such item must carry the scope in the capability's
PIN column, be spent, name the actor's own person and be unexpired, otherwise the request is denied with `cm1.personal-memory.grant-scope`;
for `forget` at least one such item must exist. A request carries no caller-supplied scope, so there
is no step a wiring bug can forget, and a peeked grant cannot authorize.

`OwnerUnlockScope` gains `personal_memory_read` and `personal_memory_forget`. A new scope is needed
for reads because `personal_protected_read` is the **default** scope that `/chat` and `/transcribe`
spend, and ADR 0009 and ADR 0015 define it as one read of confirmed `child_data`; widening it would
let a default-scope token read every personal category, `security` included. Read and administration
grants are refused for the new scopes and the new scopes are refused for them, each unspent, by the
Plan 0051 mechanics. `POST /auth/owner/unlock` accepts the new values; the change is additive and
the robot never asks for them. ADR 0016 §6 (the PIN is an optional `strong` factor) is not changed.

### 5. Fixed evaluation order and vocabulary

After the generic checks (general conversation; identity unresolved; `security` below `strong`,
which keep their `p0.5.*` ids) the order is: owner only, own data only, assurance, grant scope,
consent. Each outcome carries a `cm1.personal-memory.*` policy id (`owner-only`, `own-data-only`,
`assurance-required`, `grant-scope`, `consent-required`, `allowed`) and never a protected value; the
two vocabularies (`p0.5.*` generic, `cm1.*` for these actions) coexist on purpose. The audit row
records the action, the categories and the id, not the grant scope. The capability table lives in
`authorization.py` as a public read-only mapping over frozen dataclasses (a security table should not
be mutable); a separate module would need the request types that `evaluate_authorization` also
needs.

### 6. Nothing is wired, and the wiring obligations are written down

This ADR adds policy only. It does not store, read, confirm, correct or delete anything, does not
touch the V4 reader, and adds no route. Architecture guards pin that the new action names, the old
memory actions and the two new scopes have no consumer outside the policy and the scope
definitions, and that `select_person` (the only producer of `manual` evidence) has no caller.
Whoever wires a capability must:

1. use the consuming resolver (`resolve_actor`), never `peek_actor`, built with the capability's own
   scope (the fused resolver fixes its PIN resolver at construction, so a second one per scope). For
   `forget` only the confirmed-execution turn (obligation 6) calls it: the turn that asks "are you
   sure?" must not gate on a `forget` decision, because a peeked grant is always denied;
2. classify `visibility`, `sensitivity` and `target_person_id` from the intent before any retrieval,
   never from retrieved rows, or the policy id becomes an existence oracle;
3. write the audit row before the side effect and deny when the audit write fails;
4. keep the spoken denial a single generic text (ADR 0016 §8);
5. make `correct` supersede and keep the prior version, never overwrite or delete (a `basic`
   `correct` that overwrites would be an erasure that bypasses the `forget` gate);
6. wire `forget` only after CM-3's confirmation step exists, spend the grant at the confirmed
   execution and not at actor resolution, and decide a shorter lifetime for it. Single use protects a
   request, not an erasure: the resolver hands the same spent actor to every later evaluation in the
   request, so evaluate `forget` at most once per spent grant, name exactly one erasure target set in
   the confirmed turn, and require a fresh grant for a second one;
7. leave the confirmation dialogue to CM-3, retrieval to CM-5 and the real reach of forgetting to
   CM-6.

## Alternatives considered

- **Reuse `PROPOSE_MEMORY`, `COMMIT_MEMORY` and `DELETE_HOUSEHOLD_DATA`.** Rejected: they know
  neither the owner's own data nor sensitivity nor assurance, and `DELETE_HOUSEHOLD_DATA` names the
  household, not the person.
- **`strong` for every capability.** Rejected: `strong` costs a verified voice (optional, off by
  default) or a PIN on every turn; routine confirmation would become unusable. `forget` alone is
  irreversible.
- **Let `personal_protected_read` authorize the new read.** Rejected: it widens an accepted scope
  from `child_data` to everything personal (decision 4).
- **A caller-supplied `grant_scope` on the request.** Rejected: it moves the binding from the token
  to the caller's discipline, which ADR 0015 rejected, and a peeked grant would look like a spent
  one. The evidence the resolver already produces carries both facts.
- **State the grant rule only in the plan that wires a branch.** Rejected: the policy is where a
  missing rule becomes an authorization hole, and the rule is testable now with no wiring.
- **Require consent for `forget` as for the others.** Rejected: it lets a revoked consent block the
  erasure the person asked for.
- **Face and voice at `strong` suffice for `forget`.** Rejected: both are replayable (ADR 0016 §9)
  and the action cannot be undone.
- **A per-category assurance table, or adding the categories to `HIGH_ASSURANCE_CATEGORIES`.**
  Rejected: the table would copy the sensitive set, and the global set would also change the eleven
  old actions. One constant read only by the personal-memory evaluator says the same thing.
- **Leave `biometric`, `medical` and `location` at `basic` plus consent.** Rejected by Pipec
  (2026-10-09): the face grants consent automatically, so a photograph would reach them.
- **A separate policy module.** Rejected: an import cycle with the request types for no change of
  behaviour; one responsibility.
- **Leave both new scopes to the plan that wires the first consumer.** Rejected by Pipec
  (2026-10-08) for `forget`: the policy names the scope, so the closed scope set gains it in the same
  plan and the rule "a read grant cannot forget" is testable now. The read scope follows the same
  reasoning.

## Consequences

### Positive

- The five capabilities of the map exist as closed, audited actions with declared assurance, consent
  and grant, and every cell of the rule is a table row a test iterates.
- A read grant cannot authorize a forget, a default-scope grant cannot read personal memory, and a
  peeked grant authorizes nothing; all three fail closed and are pinned before any caller exists.
- Old actions, the V4 reader, the robot and the schemas other than the unlock scope enum are
  untouched; `IdentityEvidence` gains two defaulted fields.

### Negative

- **A photograph still reads, proposes and corrects `normal`, `private` and `child_data` personal
  memory.** At `basic` the face is enough for these, and the face resolver grants consent to any
  identified owner (there is no consent record), so the consent column is vacuous on the face path
  today. Health, location and biometric memory are held at `strong` (decision 3).
- **Proposals and corrections at `basic` are a new accepted risk.** ADR 0016 §9 accepted that a
  photograph opens ordinary private data for reads; `propose` and `correct` at `basic` let it also
  write a candidate or a superseding version, and a second person talking beside the owner can have
  their words proposed (the face is in frame, the voice is not checked). Neither becomes the owner's
  truth without `confirm`, which is `strong`, and `correct` never destroys the prior version.
  Attribution of an utterance to its speaker belongs to CM-2 and CM-3.
- **`confirm` is reachable only through face and a verified voice.** It has no PIN route, so it is
  unavailable where speaker authentication is off or the owner's voice is not enrolled (the default
  today). A plan that wires it may add a `personal_memory_confirm` scope if that proves too costly.
- **`forget` is not reachable on a turn whose owner face matched**, because the PIN is not consulted
  then (ADR 0016 §5). It is reachable on `/chat` without a frame, or with face authentication off.
  Fixing it belongs to the CM-2 ADR that revises §5.
- **`forget` extends the bearer limit to an irreversible action.** The grant proves the PIN, not
  the speaker (ADR 0008, ADR 0015), binds neither a target nor an utterance and lives 300 s. It is
  mitigated by single use, the confirmation step and a shorter lifetime (wiring obligation 6), not
  removed.
- **Consent is not a real record yet.** A face-identified owner already counts as `granted`; the
  consent rule bites only when a consent store exists.
- `propose`, `confirm` and `correct` have no PIN route: with no face match they are unavailable until
  a plan that wires them declares a scope.
- **Confirmation by a second factor is a wiring concern too:** the wiring plan for `confirm` must
  still ask the owner explicitly (CM-3); `strong` only says who may confirm.
- The audit row cannot tell visibility `private` from sensitivity `private` (both reach the same
  label set). Pre-existing; noted, not fixed here.
- The unlock scope enum and its OpenAPI schema gain two values that nothing spends yet.

## Test consequences

A characterization test pins the decisions of the eleven old actions over a fixed grid before any
change. The enum snapshot in `tests/unit/test_cognitive_models.py` and the scope enum pin in
`tests/integration/test_owner_unlock_endpoint.py` change. An exhaustive matrix over role, assurance,
visibility, sensitivity, consent and PIN evidence is compared with an oracle written in the test.
Drift tests tie the table and `PERSONAL_MEMORY_STRONG_CATEGORIES` to `DataSensitivity`,
`HIGH_ASSURANCE_CATEGORIES`, the sensitive set and `OwnerUnlockScope`; a named test pins that a
photograph-level (`basic`) owner is denied biometric, medical and location memory. Real-resolver tests prove that a peeked forget grant is denied and a spent one
allowed. Architecture guards pin the no-consumer rules, and an invariant test over
`resolve_active_person` pins that `strong` implies a `local_unlock` item or a face and a voice.

## Docs to update when this ADR is Accepted

The ADR index row; the status lines of ADR 0015 (decision 1's scope set extended by this ADR) and
ADR 0016 (§3 refined by this ADR); `docs/architecture/identity-and-access.md` (the scope paragraph
that says "two members", the role matrix, the assurance paragraph); the capability matrix of
`docs/architecture/current-state.md` and its Archify diagram; the CM-1 rows of the roadmap and the
memory map; the plan index entries (the plan moves to `completed/`, so every `plans/open/0060`
link in these documents is repointed). The `OwnerUnlockScope` docstring changes in code with the
plan.

## Review

Revisit when the CM-2 ADR revises ADR 0016 §5, when CM-3 introduces the writer, when a consent
store or an enrolled voice is the normal case, when the family profile is planned, or if any real
caller needs a PIN for `propose`, `confirm` or `correct`.

## Follow-up

- [Plan 0060](../plans/open/0060-cm1-personal-memory-capabilities.md) — implements this ADR (Draft).
- CM-2 — an ADR on identity in generic turns that revises ADR 0016 §5.
- CM-3, CM-5, CM-6 — writer and confirmation, retrieval, and the real reach of forgetting.
