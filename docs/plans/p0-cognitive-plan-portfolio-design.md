# P0 cognitive plan portfolio design

## Status

Approved design for the P0 planning portfolio. It authorizes documentation
work only; it does not authorize production implementation.

## Goal

Create a versioned, reviewable sequence of small plans that moves Iroko from
the completed cognitive vocabulary (Plan 0001) to trustworthy identity,
deterministic orchestration, relational memory, and household authorization.

## Architectural basis

The canonical order comes from
[`cognitive-roadmap.md`](../roadmap/cognitive-roadmap.md): P0.2 active person
context, P0.3 deterministic controller and tools, P0.4 relational memory, and
P0.5 household authorization. Plan 0001 is complete and provides the immutable
domain vocabulary these phases consume.

The target remains one small, explicit, typed Python controller. Development
subagents may help execute a bounded runbook, but no plan may introduce a
production multi-agent runtime, cognitive framework, autonomous loop, or
plugin ecosystem.

## Documentation roles

| Location | Role | Authority |
|---|---|---|
| `docs/plans/*-design.md` | Approved design decisions and trade-offs. | Explains why a portfolio or plan exists. |
| `docs/plans/` | Canonical implementation plans. | Defines scope, contracts, permitted files, non-goals, tests, and readiness. |
| `docs/superpowers/plans/` | Local operational TDD runbooks. | Helps execution but cannot be a repository dependency. |

`docs/plans/` is authoritative for implementation. A Superpowers runbook must
name its canonical plan and may never add a dependency, persistence change,
endpoint, provider, cloud call, hardware capability, or architectural decision
that its canonical plan does not explicitly permit.

## Portfolio

| Canonical plan | Roadmap phase | Current status | Purpose |
|---|---|---|---|
| [`0002-active-person-context.md`](0002-active-person-context.md) | P0.2 | Complete | Conservatively resolved the active-person boundary and isolated working context across identity boundaries. |
| [`0002a-local-first-provider-quarantine.md`](0002a-local-first-provider-quarantine.md) | P0 foundation | Complete | Enforced Ollama-only runtime paths before adding new controller behavior. |
| [`0002b-biometric-enrollment-quarantine.md`](0002b-biometric-enrollment-quarantine.md) | P0-S1 | Complete | Quarantined HTTP and conversational public face enrollment until P0.5 policy exists. |
| [`0002c-desktop-security-and-drift.md`](0002c-desktop-security-and-drift.md) | P0-S2 | Complete | Aligned desktop exposure defaults and active guidance after P0-S1. |
| [`0003-typed-controller-and-deterministic-tools.md`](0003-typed-controller-and-deterministic-tools.md) | P0.3 | Complete | Added the bounded `/chat` controller seam and deterministic current-date and strict-ISO-age tools only. |
| [`0004-relational-memory-v4-design-and-migration.md`](0004-relational-memory-v4-design-and-migration.md) | P0.4 design | Complete | Records the additive migration decision, registry semantics, and safe compatibility boundary. |
| [`0005-relational-memory-v4-implementation.md`](0005-relational-memory-v4-implementation.md) | P0.4 foundation | Complete | Added v4 schema/repositories and an explicit dry-run-first local migration, without runtime cutover before P0.5. |
| [`0006-household-authorization.md`](0006-household-authorization.md) | P0.5 design | Approved | Defines the complete deterministic authorization boundary and its trust decisions. |
| [`0007-household-authorization-foundation.md`](0007-household-authorization-foundation.md) | P0.5-A | Complete (pending merge) | Adds fail-closed policy, local roles/audit/bootstrap, and controller enforcement without v4 runtime retrieval. |

Plans 0002, 0002a, 0002b, 0002c, 0003, the Plan 0004 design, and Plan 0005 are
complete with recorded tests and quality gates. Plan 0007 passed its local
P0.5-A gates on 2026-08-12 and awaits PR merge evidence. P0.5-B and later
plans remain Draft and are revalidated just in time before becoming executable.

## Plan boundaries

### Plan 0002 — Active-person context

This plan introduces typed `IdentityEvidence` and `ActivePersonContext` using
existing SQLite integer entity IDs. It starts with session and explicit manual
evidence; it does not add speaker recognition, diarization, biometric
enrollment, or biometric storage. It removes owner-by-default behavior at the
cognitive boundary, represents `identified`, `probable`, `unknown`, and
`ambiguous`, expires stale evidence, and isolates working history for unknown
or conflicting people.

### Plan 0002a — Local-first provider quarantine

This foundation plan removes direct cloud-provider runtime paths and makes the
existing Ollama adapter the sole LLM and consolidation route. It does not add a
cloud escape hatch: a privacy-filtered escalation gateway remains P2 work.

### Plan 0003 — Typed controller and deterministic tools

This plan introduces one explicit controller seam around one existing text
path, preserving the public audio and server/robot contracts. It provides
ordinary typed Python tool contracts and deterministic operations for current
date and age calculation. Relationship lookup and protected retrieval remain
limited to interfaces or safe outcomes until relational memory and household
authorization have their own approved plans.

### Plan 0004 — Relational-memory design and migration

This plan makes no schema migration. It records the data decision required by
P0.4: entity-ID relationships, predicate cardinality, validity intervals,
provenance, verification state, visibility, sensitivity, compatibility with
current string-valued facts, rollback, and acceptance data cases. It is complete
after revalidation; Plan 0005 now owns its bounded storage/migration execution.

### Plan 0005 — Relational-memory implementation

This plan implements only the approved Plan 0004 storage/migration foundation.
It preserves existing integer IDs and data, makes age derived from ISO
`birth_date`, gives relationships entity-ID targets, and tests migration,
inverse relation, cardinality, temporal validity, provenance, and compatibility
behavior. A later P0.5-gated plan, not Plan 0005, owns runtime reads/writes and
family tools.

### Plan 0006 / Plan 0007 — Household authorization

Plan 0006 records the approved local deterministic policy for `owner`, `adult`,
`child`, `guest`, and `unknown`. It evaluates actor, action, data category,
visibility, sensitivity, consent, and turn scope before protected retrieval or
tool execution. A missing decision denies or requests confirmation; no policy
decision is delegated to an LLM. Plan 0007 implements P0.5-A only: typed
fail-closed policy, local role/audit storage and owner bootstrap, then policy
enforcement before protected controller delegation. A later P0.5-B plan owns
any v4 retrieval or family-tool cutover.

## Common constraints

- Preserve local-first, open-source-compatible operation and the existing
  server/robot and WAV/API contracts.
- Keep SQLite and sqlite-vec as the persistence baseline.
- Keep entity and fact references as SQLite integers; reserve UUIDs for
  envelopes, events, observations, and correlations.
- Treat `unknown`, `ambiguous`, `contradictory`, and `unauthorized` as valid
  results.
- Resolve identity and authorization before protected retrieval or model
  context.
- Use Python 3.12 typing, Google-style public docstrings, explicit exceptions,
  logging instead of `print()`, `pathlib.Path`, and current FastAPI/Pydantic
  conventions where applicable.
- Do not add dependencies, cloud calls, hardware control, or future-phase code
  unless a reviewed canonical plan explicitly requires them.
- Use local feature branches in the primary checkout. Do not create Git
  worktrees by default for this repository.

## Execution protocol

Each canonical plan must list its complete required reading, exact permitted
file scope, explicit non-goals, acceptance tests, and final verification. A
matching Superpowers runbook, when a plan is ready to execute, uses:

1. observed failing tests before implementation;
2. the smallest implementation that turns them green;
3. focused lint, format, type, and test checks;
4. a review of file scope, contracts, privacy, and type safety; and
5. final `just lint`, `just typecheck`, and `just test` before completion.

`superpowers:subagent-driven-development` is the preferred execution method;
`superpowers:executing-plans` is the sequential fallback. Both are temporary
development techniques and do not change Iroko's production architecture.

## Non-goals

- Do not create detailed executable plans for P1, P2, or P3 yet.
- Do not implement any P0 production code as part of this portfolio design.
- Do not rely on ignored `docs/local/` documents or chat history.
- Do not change accepted ADRs silently.

## Review criteria

The portfolio is ready for canonical plan drafting when the sequence has no
dependency cycle, every phase has one clear outcome, and relational schema work
is separated from its decision. P0.2 is complete; any later candidate remains
`Draft` until its dependencies and current tree are revalidated for promotion.
