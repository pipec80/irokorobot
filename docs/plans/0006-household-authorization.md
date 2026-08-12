# Plan 0006 — Household authorization design

## Status

Approved design for P0.5. It does not itself authorize code, schema changes, a
role bootstrap run, or public API changes. The first executable implementation
is [Plan 0007](0007-household-authorization-foundation.md): P0.5-A establishes
the deterministic policy, local role/audit records, explicit local owner
bootstrap, and controller enforcement without retrieving v4 household data.

A later P0.5-B plan must be written just in time after Plan 0007 has completion
evidence. It may own only a policy-gated v4 reader/tool cutover, not a redesign
of this approved policy or a public administration API.

## Purpose

Implement a local deterministic authorization boundary for household data and
tools. The policy determines whether a resolved actor may perform a named action
on a classified resource before retrieval, tool execution, consolidation, or
LLM context assembly. It makes missing policy, missing role, and uncertainty
safe outcomes rather than accidental permission.

Identity, confidence, `conversation_id`, face matching, voice matching, a
manual active-person selection, and historical `owner_name` are never grants of
authorization.

## Authority and prerequisites

- [`identity-and-access.md`](../architecture/identity-and-access.md) defines
  roles, visibility/sensitivity categories, decision order, safe uncertainty,
  biometric consent, and the initial role matrix.
- [`0004-local-first-cognitive-policy.md`](../adr/0004-local-first-cognitive-policy.md)
  requires local authority, explicit uncertainty, and no hidden cloud fallback.
- [`0005-small-typed-cognitive-controller.md`](../adr/0005-small-typed-cognitive-controller.md)
  requires one typed controller with policy before deterministic tools and
  memory retrieval.
- [`memory-and-world-state.md`](../architecture/memory-and-world-state.md)
  requires filtering before retrieval and makes visibility/sensitivity
  classifications distinct from access decisions.
- [Plan 0002](0002-active-person-context.md) supplies active-person evidence;
  [Plan 0003's design](0003-typed-controller-and-deterministic-tools-design.md)
  supplies controller/tool seams; [Plan 0004](0004-relational-memory-v4-design-and-migration.md)
  supplies v4 visibility/sensitivity metadata. None may be reimplemented here.

## Approved policy model

### 1. Explicit authorization request and decision

P0.5 introduces immutable typed requests evaluated by an ordinary local Python
policy service. The request carries only the minimum decision inputs:

- active actor entity ID or null and P0.2 identity status;
- resolved household role or `unknown`;
- stable action name;
- target subject/resource IDs when applicable;
- v4 visibility and sensitivity categories;
- requested data categories and turn/correlation scope;
- applicable consent/confirmation state; and
- aware UTC evaluation time.

The result extends the Plan 0001 `AuthorizationDecision` vocabulary without
weakening it: `allowed`, `denied`, or `requires_confirmation`, a stable policy
ID, safe reason, evaluated timestamp, and bounded scope/expiry. It contains no
protected memory value, raw biometric, conversation text, embedding, or model
prompt.

No request and no matching policy rule are denial/confirmation outcomes; they
are never implicit `allowed`.

### 2. Roles and explicit bootstrap

The first policy recognizes exactly `owner`, `adult`, `child`, `guest`, and
`unknown`. Role assignments are local SQLite records with integer person IDs,
role, grant/revoke lifecycle, grantor entity ID where applicable, safe reason,
and timestamps. They are distinct from v4 relations and facts.

The initial `owner` is established only through an explicit local administrative
operation that names an existing person `entity_id`, records an audit event,
and requires deliberate operator confirmation. It has no public HTTP endpoint,
does not infer an owner from `owner_name`/a name/face/voice, and cannot be run by
an LLM. P1 unified onboarding reuses this service rather than inventing a
separate role-writing path.

### 3. Stable actions and default matrix

The implementation has a small, typed action registry, not arbitrary strings
constructed by prompts. Initial actions cover general conversation, retrieval
by visibility/sensitivity class, deterministic tools, proposed memory changes,
role administration, biometric enrollment, export/delete, physical-action
proposal, and cloud-escalation consideration.

The policy starts from this local fail-closed baseline:

| Capability | Owner | Adult | Child | Guest/unknown |
|---|---:|---:|---:|---:|
| General conversation without protected data | allowed | allowed | allowed | allowed, bounded |
| Public household fact | allowed | allowed | requires confirmation/policy | denied |
| Own normal profile | allowed | allowed | allowed when subject matches | denied |
| Another person's private memory | policy/confirmation | policy/confirmation | denied | denied |
| Child, medical, location, security, or biometric data | explicit policy/consent | explicit policy/consent | denied by default | denied |
| Propose memory candidate | allowed | requires confirmation | requires confirmation | denied |
| Commit confirmed memory, roles, export, or deletion | explicit owner policy | denied by default | denied | denied |
| Biometric enrollment or cloud escalation of sensitive data | owner + subject consent + explicit policy | denied by default | denied | denied |
| Physical action | explicit policy + body safety | explicit policy + body safety | denied by default | denied |

`requires_confirmation` is not data access. The system asks a safe question or
returns a safe limitation before any protected read/tool call. A later
confirmation flow must bind the exact actor, action, target, categories, and
short expiry; it must not become a reusable session permission.

### 4. Enforcement order and scope

The policy boundary is enforced in the shared cognitive/text-turn and
controller seams before:

1. relational/literal/semantic memory retrieval;
2. deterministic tools that could disclose household or personal data;
3. onboarding, consolidation, or any durable memory mutation;
4. model context assembly and generation claims; and
5. cloud escalation or an action proposal.

The P0.3 pure date/age tools remain local and can answer only non-protected
inputs. Family counts, profiles, current perception, and protected memory use
require a P0.5 decision and must otherwise yield `unauthorized` without
revealing whether data exists. Public conversation retains a local response
path, but it receives no protected context.

Every permitted retrieval returns only the minimum classified fields. The LLM
may express a permitted result, but cannot ask for broader data, override a
denial, grant a role, execute a tool, write memory, or command an actuator.

### 5. Local audit and retention boundary

Each nontrivial policy evaluation records a local, append-only audit event with
safe actor/target IDs when available, action, categories, policy ID, result,
safe reason, decision time, correlation ID, and confirmation reference. It does
not store prompt text, response text, raw media, face/voice templates, or a
copy of protected values.

Audit retention is separate from autobiographical memory, semantic memory,
world state, and telemetry. A denied request may be audited while its protected
data remains unread. P0.5 provides the event boundary; long-term retention,
export, deletion, and lifecycle work may require later P2 policy.

## Questions and decisions log

| ID | Question | Alternatives considered | Decision | Why |
|---|---|---|---|---|
| D05-01 | What constitutes permission? | Identity confidence; `conversation_id`; local policy decision. | Explicit local policy decision. | Identity and confidence answer different questions; a high-confidence speaker can still be forbidden. |
| D05-02 | What is the default without policy or role? | Allow for usability; infer from owner metadata; deny/require confirmation. | Deny or require confirmation. | Protected data must not be retrieved by accident, and unknown is a valid outcome. |
| D05-03 | How is the first owner established? | First self-introduction; configured name; automatic face match; explicit local assignment by entity ID. | Explicit local assignment by integer entity ID. | It is auditable, reversible, does not confuse a name or biometric evidence with authority, and reuses the entity identity model. |
| D05-04 | Where are roles stored? | Environment names; entity attributes; dedicated local role records. | Dedicated local role records with lifecycle. | Roles are authorization state, not profile facts; assignment/revocation needs provenance and auditability. |
| D05-05 | When is policy evaluated? | After retrieval/prompt filtering; before each protected boundary; only before actions. | Before every protected retrieval/tool/write/context boundary. | Filtering after the LLM sees data is not access control. |
| D05-06 | What does `requires_confirmation` permit? | Retrieve then ask; broad session unlock; no access until exact scoped confirmation. | No access until exact scoped confirmation. | The response must not reveal protected facts or turn one confirmation into a master grant. |
| D05-07 | Are roles alone enough? | Role-only matrix; visibility/sensitivity only; role plus action/resource/consent. | Role plus action, target, visibility, sensitivity, consent, and scope. | An adult/owner label cannot by itself decide every personal, child, biometric, medical, location, or security request. |
| D05-08 | How is a denial recorded? | Log full request/content; do not log; safe structured local audit. | Safe structured local audit. | It supports review without duplicating sensitive conversation, memory, or biometric material. |
| D05-09 | Can the LLM participate in policy? | Let model decide; model suggests; deterministic policy only. | Deterministic policy only. | Policy must be reproducible, testable, offline, and resistant to prompt influence. |
| D05-10 | Does P0.5 expose an admin API/UI? | Public route; web admin; no public endpoint yet. | No public endpoint/UI. | A trustworthy authenticated operator channel is not defined yet; P1 onboarding will consume the local service after this boundary exists. |

## Explicit non-goals

- Implement P0.2/P0.3/P0.4, P1 onboarding, P2 lifecycle/cloud, P3 robotics,
  or any production authorization code at this stage.
- Infer identity, role, consent, or owner from a conversation, name, face,
  voice, session, device, confidence score, or LLM output.
- Add cloud calls, public admin APIs, login/accounts, web UI, new dependencies,
  biometric storage/processing, robot commands, or audio contract changes.
- Let an audit record, a classification, or a policy result bypass local body
  safety, sensitive-data consent, or later retention/deletion requirements.
- Filter an already retrieved model prompt or claim that a denied/unknown fact
  exists unless explicit policy permits that disclosure.

## Implementation status

Plans P0.2, P0.3, and P0.4 are complete and their current seams were
revalidated at main commit `3b01b58`. Plan 0007 freezes the migration 5,
request/decision contracts, role-assignment operation, policy/action registry,
audit schema, exact file scope, and RED/GREEN coverage for P0.5-A.

Any change to the policy matrix, bootstrap trust boundary, audit content, or
the later v4 runtime cutover requires a documented decision before
implementation.
