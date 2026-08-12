# Plan 0003 — Typed controller and deterministic tools

## Status

**Draft — not executable.** This plan implements only the approved
[P0.3 design](0003-typed-controller-and-deterministic-tools-design.md). It may
be promoted to `Ready` only after Plans 0002, 0002a, 0002b, and 0002c are
Complete, the P0.2 code, local-provider boundary, and P0-S hardening outcomes
are re-read, and this document is revised with its exact current file scope and
tests. The companion
[execution runbook](0003-typed-controller-and-deterministic-tools-execution.md)
is also Draft and does not authorize implementation.

## Objective

Pilot one small typed `CognitiveController` behind existing `/chat`, preserving
its public JSON contract. Add deterministic, local, testable current-date and
age calculation tools; make all not-yet-founded relationship, profile, memory,
perception, and permission requests return safe typed outcomes instead of using
legacy shortcuts or LLM inference.

## Required authority when becoming Ready

1. `AGENTS.md` and all applicable `.codex/rules/`.
2. [ADR-0005](../adr/0005-small-typed-cognitive-controller.md) and
   [ADR-0004](../adr/0004-local-first-cognitive-policy.md).
3. [`cognitive-architecture.md`](../architecture/cognitive-architecture.md)
   and [`cognitive-contracts.md`](../architecture/cognitive-contracts.md).
4. [Plan 0002](0002-active-person-context.md), its approved design, and its
   recorded completion evidence.
5. [Plan 0002a](0002a-local-first-provider-quarantine.md) and its recorded
   local-only validation evidence.
6. [P0-S hardening design](p0-s-hardening-design.md), completed Plan 0002b,
   and completed Plan 0002c.
7. [P0.3 design decisions](0003-typed-controller-and-deterministic-tools-design.md)
   and its execution runbook.
8. The then-current chat router/schema tests, text-turn service, cognition
   package, local LLM boundary, and Plan 0001 models.

## Locked outcomes

- One explicit typed Python controller, not an agent framework, plugin runtime,
  event bus, behavior tree, autonomous loop, or production multi-agent system.
- Only `POST /chat` pilots the controller. `/transcribe`, streaming, vision,
  robot, audio, and their public contracts remain untouched in this phase.
- Typed event, information need, tool result, and response-plan contracts are
  immutable and independently unit-testable with no I/O.
- `get_current_date` and `calculate_age(ISO birth_date, on_date)` are the only
  active deterministic tools. Age is computed, never persisted.
- Date/age routing is a documented narrow deterministic classifier, not broad
  NLU or model tool selection.
- Relationship/profile/memory/perception requests use `unknown`; protected
  operations use `unauthorized` before P0.4/P0.5. Identity is not permission.
- The LLM receives a bounded response plan for wording only. It cannot select a
  tool, calculate an age, turn an uncertain outcome into fact, grant access,
  mutate memory, use cloud, or command hardware.

## Provisional implementation slices

These are future TDD tasks. Exact filenames, public/internal contracts, and
focused commands are frozen only in the Ready revision after a current-tree
review.

### Slice 1 — Controller and response contracts

- [ ] Write RED tests for strict immutable text-event, information-need,
  tool-result, claim, and response-plan value objects, reusing Plan 0001
  `KnowledgeStatus` and `Confidence` rather than duplicating enums.
- [ ] Implement the minimal pure contracts and controller constructor with
  injected clock/tool/generation seams; no HTTP, SQLite, model, or hardware I/O
  in construction/validation.
- [ ] Run focused GREEN and review all types/docstrings/serialization.

### Slice 2 — Pure deterministic calendar tools

- [ ] Write RED tests for current-date injection, ISO date validation, completed
  calendar years, birthday boundary, leap-day handling, future birth date, and
  invalid/missing data -> explicit `unknown`.
- [ ] Implement only `get_current_date` and `calculate_age` as ordinary Python
  functions with typed inputs/results.
- [ ] Run focused GREEN. Verify no model call, persistence, locale guess, or
  mutable `age` record occurs.

### Slice 3 — Bounded intent and response validation

- [ ] Write RED tests for supported current-date and explicit-ISO-age forms,
  generic conversation fallback, unsupported relationship/profile request ->
  `unknown`, and protected request -> `unauthorized`.
- [ ] Implement a closed deterministic classifier and response-plan validator.
  The validator preserves `unknown`/`unauthorized` and rejects unbacked
  factual claims from tool output.
- [ ] Run focused GREEN; confirm no broad NLU, prompt-driven routing, or LLM
  decision path appears.

### Slice 4 — `/chat` pilot adapter

- [ ] Update endpoint tests first to prove exact request/response JSON, error
  validation, duration field, and local fallback remain unchanged while the
  validated message becomes one typed controller event.
- [ ] Wire only the chat adapter to the controller and existing local wording
  boundary. Do not migrate voice, streaming, vision, robot, or shared audio
  paths.
- [ ] Run focused GREEN, including no automatic persistent-memory/protected-data
  retrieval beyond the completed P0.2/P0.5 boundaries.

### Slice 5 — Verification and handoff

- [ ] Run focused controller/tool/chat tests, then `just lint`,
  `just typecheck`, and `just test`.
- [ ] Review `git diff --check` and exact permitted scope; confirm no dependency,
  cloud, DB schema, permission-policy, biometric, action, or audio-contract
  change.
- [ ] Record observed RED/GREEN evidence and change this plan to `Complete`
  only after all gates pass. P0.4/P0.5 remain Draft unless separately promoted.

## TDD execution protocol

When Ready, use `superpowers:subagent-driven-development` (preferred) or
`superpowers:executing-plans` (sequential fallback). Each task records an
observed RED failure, the smallest GREEN implementation, focused checks, and a
scope/type/privacy review. Workers use local feature branches in the primary
checkout, preserve unrelated work, and never commit directly to `main`.

Development subagents are temporary workflow helpers only; Iroko remains one
small sequential controller in production.

## Stop conditions and promotion gate

Stop and create a new decision/plan if implementation needs general NLU,
framework/runtime adoption, database/schema work, legacy relationship queries,
permission policy, cloud, biometrics, physical actions, or an audio/robot
contract change. Promote only after Plan 0002 is complete, current code is
re-read, exact scope/test commands are approved, and a matching detailed TDD
runbook is committed.
