# Plan 0007 — Household authorization foundation

## Status

**Complete — merged to `main` as `960f160` through PR #42 on 2026-08-12.**
The feature branch validation commit was `3821be2`. This P0.5-A slice follows
P0.2, P0.3, and the P0.4 relational-memory v4 foundation merged as `3b01b58`
(PR #40).

The approved [Plan 0006 design](0006-household-authorization.md) remains the
authority for the complete P0.5 policy. A later P0.5-B plan may connect this
verified boundary to v4 retrieval and deterministic family tools only after a
fresh review of this implementation.

## Objective

Create one local deterministic authorization service that evaluates a resolved
actor, a closed action, classified data, and consent/confirmation state before
any protected branch can reach legacy generation, a future v4 reader, a tool,
or a durable write. Persist household-role assignments and safe policy audit
events in additive SQLite migration 5. Provide a deliberate local-only owner
bootstrap command; do not create an HTTP administration path.

## Required reading

1. `AGENTS.md` and the applicable repository rules.
2. [ADR-0004](../adr/0004-local-first-cognitive-policy.md) and
   [ADR-0005](../adr/0005-small-typed-cognitive-controller.md).
3. [Identity and access](../architecture/identity-and-access.md),
   [cognitive contracts](../architecture/cognitive-contracts.md), and
   [memory and world state](../architecture/memory-and-world-state.md).
4. The approved [Plan 0006 design](0006-household-authorization.md).
5. Completed Plans 0002, 0003, 0004, and 0005, including Plan 0005's explicit
   prohibition on v4 runtime cutover before policy exists.
6. Current `cognition/models.py`, `cognition/identity.py`,
   `cognition/controller.py`, `routers/chat.py`, `text_turn.py`, `db.py`,
   the migration registry, `memory/relational_v4.py`, and their direct tests.

## Locked contracts and invariants

### Typed policy vocabulary

Add immutable, closed values for:

- actions: `general_conversation`, `read_household_data`,
  `execute_household_tool`, `propose_memory`, `commit_memory`,
  `manage_household_role`, `enroll_biometric`, `export_household_data`,
  `delete_household_data`, `consider_cloud_escalation`, and
  `propose_physical_action`;
- visibility: `public`, `household`, `adults`, `personal`, `private`,
  and `temporary`;
- sensitivity: `normal`, `private`, `biometric`, `medical`,
  `location`, `child_data`, and `security`; and
- consent state: `not_required`, `granted`, `missing`, and `revoked`.

`AuthorizationRequest` is an immutable value in the cognition layer. It
contains the resolved `ActivePersonContext`, one closed action, target person
ID when relevant, visibility/sensitivity sets, consent state, correlation ID,
and an aware UTC request time. It contains no prompt text, fact value,
embedding, image, audio, or raw biometric payload.

`AuthorizationDecision` remains immutable and is extended only with the
bounded correlation scope and optional aware expiry needed to audit and bind a
decision to one request. It must not contain a protected value. Existing
statuses retain their exact meanings: `allowed`, `denied`, and
`requires_confirmation`.

`HouseholdRole` remains an identity-context label, not a permission grant.
Move/re-export it only if required to keep typed contracts acyclic and
backward-compatible for current imports.

### Default policy

The policy is ordinary pure Python with no database, FastAPI, LLM, provider,
or hardware import. It has a closed first matrix:

| Request | Owner | Adult | Child | Guest / unknown |
|---|---:|---:|---:|---:|
| General conversation without protected context | allowed | allowed | allowed | allowed |
| Public household data | allowed | allowed | requires confirmation | denied |
| Own normal personal data | allowed | allowed | allowed only for own subject | denied |
| Household/adults/personal/private read or family tool | explicit policy | explicit policy | denied | denied |
| Child, medical, location, security, or biometric data | consent + explicit policy | consent + explicit policy | denied | denied |
| Propose memory candidate | allowed | requires confirmation | requires confirmation | denied |
| Commit memory, manage role, export, delete | explicit owner policy | denied | denied | denied |
| Biometric enrollment or sensitive-cloud consideration | owner + subject consent | denied | denied | denied |
| Physical-action proposal | explicit policy; body safety remains required | explicit policy; body safety remains required | denied | denied |

Unknown, ambiguous, expired, or role-less actors never receive a protected
`allowed` decision. A missing rule is `denied`; `requires_confirmation`
grants no retrieval, tool call, write, or prompt context. P0.5-A implements no
confirmation issuer or session unlock.

### Role persistence and local bootstrap

Migration 5 adds only:

- `household_role_assignments`: integer person ID, closed role, grantor person
  ID nullable only for the initial local bootstrap, safe reason, granted/revoked
  lifecycle timestamps, and at most one active role per person; and
- `authorization_audit_events`: append-only application records with safe
  actor/target IDs, action, classifications, decision, policy ID, safe reason,
  correlation ID, evaluated timestamp, and optional bounded expiry.

Both tables use foreign keys to existing `entities` IDs and contain neither
conversation/prompt/response text nor raw media, embeddings, or protected data
values. Migration 5 is additive and idempotent; it must not rewrite legacy
facts, v4 rows, biometrics, or entity attributes.

Provide `scripts/manage_household_roles.py` as a local-only operator command.
Its initial-owner subcommand requires an existing `person` entity ID plus a
deliberate matching confirmation argument. It refuses a second active owner,
does not infer identity from a name/face/voice/session/environment flag, and
writes a safe audit record. The script has no HTTP server, model, cloud, or
audio dependency. Role assignment/revocation API use remains internal; public
administration and P1 onboarding are explicitly deferred.

### Runtime enforcement in the P0.3 controller

Inject the policy evaluator and audit writer into `CognitiveController`.
`/chat` composes it with the safe unknown actor because public requests do not
carry trusted identity. For any classified protected household branch, the
controller must evaluate and record the decision **before** legacy delegation.

- denied or confirmation-required paths return a fixed non-disclosing
  `unauthorized` response plan and never call legacy generation;
- an allowed internal policy result still returns `unknown` in P0.5-A because
  v4 reads and family tools are not connected yet; and
- generic public conversation keeps the existing local fallback and receives
  no protected context.

The legacy `text_turn.py` v3 memory/context path stays untouched. P0.5-A does
not pass a role-bearing actor to it, does not read v4 data, and does not alter
the `/chat` or `/transcribe` public schemas.

## Exact permitted file scope

| Path | Change |
|---|---|
| `server/src/server/db.py` | Register additive migration 5 only. |
| `server/src/server/memory/migration_005_household_authorization.sql` | Create role/audit tables and indexes only. |
| `server/src/server/cognition/models.py` | Add or extend immutable authorization vocabulary and decision scope. |
| `server/src/server/cognition/identity.py` | Preserve/re-export role vocabulary and optionally accept a caller-provided role lookup; no identity inference. |
| `server/src/server/cognition/authorization.py` | Create pure request, policy matrix, and decision evaluator. |
| `server/src/server/memory/household_authorization.py` | Create typed role and append-only audit repositories. |
| `server/src/server/cognition/controller.py` | Inject and enforce the policy/audit seam before protected delegation. |
| `server/src/server/routers/chat.py` | Compose only unknown actor, default policy, and local audit collaborator without changing HTTP schemas. |
| `server/src/server/cognition/__init__.py` | Export only the new public cognitive values needed by existing code/tests. |
| `scripts/manage_household_roles.py` | Add the explicit local owner-bootstrap operator command. |
| `tests/unit/test_cognitive_models.py` | Update authorization-contract validation/immutability coverage. |
| `tests/unit/test_active_person_identity.py` | Cover optional explicit role lookup without granting authorization. |
| `tests/unit/test_household_authorization_policy.py` | Add table-driven pure policy matrix, unknown/ambiguous, consent, and fail-closed tests. |
| `tests/unit/test_cognitive_controller.py` | Prove policy-before-delegate and no-leak behavior with fakes. |
| `tests/integration/test_household_authorization_schema.py` | Cover migration 5, foreign keys, active-role lifecycle, audit minimum fields, and legacy/v4 preservation. |
| `tests/integration/test_household_authorization_runtime.py` | Cover local bootstrap, audit persistence, public unknown denial, and unchanged `/chat` schema. |
| `tests/integration/test_memory_v4_schema.py` | Update fresh-schema version expectation to 5 while retaining v4 compatibility coverage. |
| Architecture/roadmap/plan documents named in this plan | Record completion evidence only after final gates. |

No other file is permitted. In particular, do not modify `text_turn.py`, v3
memory modules, `relational_v4.py`, legacy migration code, prompts, providers,
vision, face enrollment, onboarding, robot code, audio code, public schemas,
or environment variables. No dependency is authorized.

## TDD slices

### Slice 1 — Pure typed request and fail-closed policy

1. Write RED unit tests for frozen values, aware timestamps, invalid category
   rejection, missing policy denial, unknown/ambiguous actor denial, subject
   matching, child/biometric/medical/location/security denial, consent, and
   `requires_confirmation` never becoming `allowed`.
2. Implement the smallest pure contract and policy evaluator.
3. Run `uv run pytest tests/unit/test_cognitive_models.py tests/unit/test_household_authorization_policy.py -v` GREEN.

### Slice 2 — Additive role/audit storage and local bootstrap

1. Write RED integration tests against a fresh real SQLite database for schema
   version 5, foreign keys, one active role, revocation history, append-only
   audit writes, no protected text columns, and unchanged legacy/v4 fixtures.
2. Add migration registration, repository operations, and local bootstrap CLI.
3. Test an existing person can be made the one initial owner only with the exact
   confirmation; invalid/non-person/second-owner commands fail without a role
   or audit mutation.
4. Run focused schema/runtime suites GREEN. Do not run it against a household
   database during this PR.

### Slice 3 — Controller policy boundary

1. Write RED controller tests that prove decision evaluation and safe audit occur
   before protected legacy delegation; denied and confirmation-required requests
   never invoke the delegate or expose a data value; an allowed internal request
   remains `unknown` until P0.5-B; generic unknown conversation retains legacy
   fallback.
2. Inject small policy/audit collaborators and compose a safe unknown actor in
   `/chat`.
3. Run controller plus chat integration tests GREEN, preserving the exact public
   JSON response contract.

### Slice 4 — Final review and handoff

1. Re-run P0.2/P0.3/P0.4 tests affected by models/migrations.
2. Run `just lint`, `just typecheck`, `just test`, `just audit`,
   `just check`, and `git diff --check`.
3. Review every changed path for a public admin route, owner/name inference,
   protected data in audit, v4 runtime import, dependency, prompt, provider,
   audio, or robot drift.
4. Update completion evidence only with actual outputs. Then open a small PR;
   merge only after GitHub CI is green and return to `main`.

## Acceptance criteria

- A policy decision is reproducible offline from typed inputs; no model or
  database call determines allow/deny.
- Unknown, ambiguous, and role-less identity never authorize protected read,
  tool, write, biometric, cloud, or physical-action requests.
- `requires_confirmation` cannot cause a protected read or broad session grant.
- Initial owner bootstrap is explicit, local, entity-ID based, auditable,
  idempotently safe, and not publicly reachable.
- Audit records identify decisions without storing protected content or raw
  biometric material.
- The P0.3 protected branch is evaluated/audited before legacy delegation and
  reveals no protected fact; public `/chat` remains schema-compatible.
- v3/v4 runtime retrieval and writes, onboarding, biometrics, cloud, hardware,
  and audio behavior are unchanged.

## Implementation evidence

- **Observed RED:** importing the new role service failed before it existed;
  the pure-policy tests then demonstrated that unknown/ambiguous general
  conversation was incorrectly denied before the public-conversation rule was
  ordered ahead of protected access checks, and a generic action could carry
  protected categories. The additive schema suite also initially failed because
  no internal non-owner role assignment service existed.
- **Focused GREEN:** 94 P0.2–P0.5 tests passed, covering immutable contracts,
  explicit role lookup without authorization, deterministic policy, additive
  migration 5, owner bootstrap, role lifecycle, safe audit persistence,
  controller-before-legacy ordering, and unchanged `/chat` responses.
- **Migration evidence:** a fresh temporary SQLite database applied migrations
  1–5; `PRAGMA foreign_key_check` was clean; legacy facts and v4 tables stayed
  intact. Audit records hold only IDs, closed categories/actions, decision,
  safe reason, correlation, and aware timestamps—never prompt, response,
  media, embedding, or fact values.
- **Final local gates:** `just lint`, `just typecheck`, `just test`, `just
  audit`, and `just check` passed. The full suite passed **546 tests**.
  GitHub CI passed (title, quality/security, automated tests, and CodeQL), and
  PR #42 was squash-merged as `960f160`.
- **Not exercised:** the owner-bootstrap command was verified only with
  `--help`; it was never run against a household database. No real model,
  camera, microphone, LAN server, biometric enrollment, cloud path, or
  hardware was exercised.

The next step remains a freshly revalidated P0.5-B plan for policy-gated v4
retrieval and deterministic family tools. It must not make an `allowed`
decision reusable across requests, and it must not expose protected data to
legacy v3 prompt construction.

## Rollback

Code rollback restores the prior controller composition; no legacy or v4 data
is modified. Migration 5 is additive: a logical rollback revokes active role
assignments and retains audit evidence; destructive table removal or automatic
reverse migration is out of scope. The bootstrap CLI is never run against a
real household database as part of automated verification.

## Stop conditions

Stop and create a new ADR/plan if implementation needs login/accounts, a public
admin API/UI, an authentication provider, a new global ID strategy, destructive
migration, generic policy language interpreted by an LLM, public biometric
enrollment, actual family v4 retrieval/tools, confirmation-session persistence,
cloud processing, motor commands, or any audio/server-robot contract change.
