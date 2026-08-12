# Plan 0003 — Typed controller and deterministic tools

## Status

**Complete.** Implemented on `feat/p03-typed-controller` at `5954a90` after
the P0-S2 baseline `5f1971c` on `main`.
Plans 0002, 0002a, 0002b, and 0002c are Complete. The P0.2 identity boundary,
Ollama-only provider boundary, P0-S hardening results, current chat adapter,
`CognitiveEvent` contract, and chat/text-turn tests were re-read. The companion
[execution runbook](0003-typed-controller-and-deterministic-tools-execution.md)
is Ready with this canonical plan and authorizes exactly the scope below.

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
- Relationship/profile/memory/perception requests use `unknown`; clearly private
  household operations use `unauthorized` before P0.4/P0.5. Identity is not
  permission.
- The two deterministic branches produce fixed, evidence-backed Spanish text in
  P0.3 and do not invoke the LLM. Generic conversation delegates to the current
  local text turn. No branch lets an LLM select a tool, calculate an age, turn
  uncertainty into fact, grant access, mutate memory, use cloud, or command
  hardware.
- P0.3 deliberately has no `ToolRegistry`: two closed static functions do not
  justify a registry abstraction. A future plan may introduce one only when
  more real tools need shared registration, metadata, or dispatch.

## Revalidated implementation scope

| Path | Change |
|---|---|
| `server/src/server/cognition/response_plan.py` | Create immutable P0.3 payload, need, tool-result, claim, and response-plan values. |
| `server/src/server/cognition/calendar_tools.py` | Create pure strict-ISO date and age helpers. |
| `server/src/server/cognition/controller.py` | Create one injected, sequential controller. |
| `server/src/server/cognition/__init__.py` | Export the new cognition contracts only. |
| `server/src/server/routers/chat.py` | Adapt its existing validated request into a fresh cognitive event and map the plan back to unchanged JSON. |
| `tests/unit/test_response_plan.py` | Add immutable-contract and response-validation tests. |
| `tests/unit/test_calendar_tools.py` | Add pure date and age boundary tests. |
| `tests/unit/test_cognitive_controller.py` | Add branch ordering, no-delegate, and fallback-delegation tests with fakes. |
| `tests/integration/test_chat_endpoint.py` | Preserve `/chat` schema and verify observable deterministic behavior. |
| `docs/architecture/current-state.md`, `docs/roadmap/cognitive-roadmap.md`, `docs/plans/README.md`, `docs/plans/p0-cognitive-plan-portfolio-design.md`, this plan, and its runbook | Record readiness now and completion evidence only after the implementation gates pass. |

`text_turn.py`, schemas, memory/SQLite, vision, robot, audio, prompts, and
provider code are explicitly outside this plan. No dependency is authorized.

## Ready TDD slices

### Slice 1 — Controller and response contracts

- [x] Write RED unit tests in `tests/unit/test_response_plan.py` for strict,
  frozen `TextTurnPayload`, `InformationNeed`, `ToolResult`, `ResponseClaim`,
  and `ResponsePlan` values. Reuse Plan 0001 `KnowledgeStatus` and
  `Confidence`; reject a known claim without a known deterministic tool result.
- [x] Create `response_plan.py` with those values and no I/O. Its event payload
  must satisfy the existing `CognitiveEvent[PayloadT: BaseModel]` bound.
- [x] Run `uv run pytest tests/unit/test_response_plan.py -v` GREEN and review
  JSON serialization, immutability, and no duplicated status enum.

### Slice 2 — Pure deterministic calendar tools

- [x] Write RED unit tests in `tests/unit/test_calendar_tools.py` for injected
  current date, strict ISO parsing, completed calendar years, birthday boundary,
  leap-day handling, future dates, and invalid/missing input -> `unknown`.
- [x] Create `calendar_tools.py` with only `get_current_date()` and
  `calculate_age()`, with explicit `date` injection in the core and no model,
  persistence, locale guess, or mutable age record.
- [x] Run `uv run pytest tests/unit/test_calendar_tools.py -v` GREEN.

### Slice 3 — Bounded intent and response validation

- [x] Write RED tests in `tests/unit/test_cognitive_controller.py` for direct
  current-date and explicit-ISO-age forms, generic delegate fallback, relation
  and profile requests -> `unknown`, and clearly protected household requests ->
  `unauthorized`. Fakes must prove deterministic/protected paths never call the
  legacy delegate.
- [x] Create `controller.py` with an injected clock and legacy text-turn
  delegate. Use a closed classifier and deterministic response-plan validation;
  no broad NLU, prompt routing, memory read, or LLM decision path is allowed.
- [x] Run `uv run pytest tests/unit/test_cognitive_controller.py -v` GREEN.

### Slice 4 — `/chat` pilot adapter

- [x] Extend `tests/integration/test_chat_endpoint.py` RED to prove the exact
  request/response JSON, validation errors, duration, and safe generic fallback
  remain unchanged while the request becomes a fresh typed event.
- [x] Wire only `routers/chat.py` to construct a fresh event and adapt a
  `ResponsePlan`. Do not migrate voice, streaming, vision, robot, shared audio,
  schemas, or `text_turn.py`.
- [x] Run `uv run pytest tests/integration/test_chat_endpoint.py -v` GREEN,
  including public-unknown isolation and no automatic persistent-memory or
  protected-data retrieval.

### Slice 5 — Verification and handoff

- [x] Run the three new unit suites and chat integration suite, then `just lint`,
  `just typecheck`, `just test`, and `just audit`.
- [x] Review `git diff --check` and exact permitted scope; confirm no dependency,
  cloud, DB schema, permission-policy, biometric, action, or audio-contract
  change.
- [x] Record observed RED/GREEN evidence and change this plan to `Complete`
  only after all gates pass. P0.4/P0.5 remain Draft unless separately promoted.

## Execution protocol

Use the matching Ready runbook sequentially. Each task records observed RED,
the smallest GREEN implementation, focused checks, and a scope/type/privacy
review. Work on a fresh feature branch; never commit directly to `main`.

## Stop conditions and promotion gate

Stop and create a new decision/plan if implementation needs general NLU, a tool
registry/framework/runtime, database/schema work, legacy relationship queries,
permission policy, cloud, biometrics, physical actions, or an audio/robot
contract change. Change this plan to `Complete` only after all listed tests and
final gates pass; P0.4 and P0.5 remain Draft.

## Completion evidence

Implementation is `5954a90` (`feat(cognition): add deterministic chat
controller`). It introduced only the permitted controller, immutable response
contracts, pure calendar helpers, `/chat` adapter, and their tests; it added no
dependency, database/migration, memory, authorization-policy, biometric,
provider/cloud, audio, vision, robot, or public-schema change.

Observed TDD evidence:

- `test_response_plan.py` was RED with two missing-module failures, then GREEN
  with 2 passing tests.
- `test_calendar_tools.py` was RED with four missing-module failures, then
  GREEN with 6 passing tests.
- `test_cognitive_controller.py` was RED with five missing-module failures,
  then GREEN with 5 passing tests.
- New `/chat` integration assertions were RED for the missing `_today` adapter
  and an unsafe legacy delegation; the corrected integration suite was GREEN
  with 13 passing tests.
- A public-export regression was found by the first full suite, corrected in
  `server.cognition.__all__`, and the final full suite passed.

Final implementation verification recorded before PR creation:

- focused P0.3 contracts/controller/chat coverage passed (25 tests before the
  final export correction);
- `just lint` passed;
- `just typecheck` passed (`mypy`: 67 source files; `pyright`: 0 errors);
- final `just test` passed: **514 passed in 36.25s**;
- `just audit` passed (Ruff security and `pip-audit` found no known
  vulnerabilities);
- `just check` passed cleanly after the implementation commit.

No real Ollama `/chat` request, camera, microphone, LAN, biometric, or hardware
acceptance was performed. Those results are not inferred from unit/integration
tests. P0.4 and P0.5 remain Draft and are not authorized by this completion.
