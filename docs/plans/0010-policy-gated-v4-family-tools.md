# P0.5-B2 Policy-Gated V4 Family Tools Implementation Plan

> **Status:** Complete — merged as `0d16969` through PR #48 on 2026-08-14.

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let trusted internal seams answer a small closed set of family
questions from authorized v4 data, while public `/chat` stays unknown-by-default.

**Architecture:** `HouseholdKnowledgeTools` is a typed application service, not
a tool framework or LLM loop. It evaluates and audits `EXECUTE_HOUSEHOLD_TOOL`
from immutable predicate metadata. Only then it calls `PolicyGatedV4Reader`,
which separately evaluates and audits `READ_HOUSEHOLD_DATA` before a v4 query.
The controller recognizes only the two self-child questions that need no name
resolution and returns deterministic Spanish `ResponsePlan` values.

**Tech Stack:** Python 3.12, Pydantic v2, SQLite/aiosqlite, existing P0.3
calendar/controller, P0.4 repositories, P0.5 policy/audit, pytest, Ruff, mypy,
Pyright, pre-commit, and `just`.

## Revalidation record

Revalidated on `main` at `e00992a` on 2026-08-14. The approved
[Plan 0008 design](0008-policy-gated-v4-household-tools-design.md) still
matches code after B1: `PolicyGatedV4Reader` exists, public `/chat` creates only
an unknown actor, and there is no `cognition.tools` module or generic registry.

## Global constraints

- Implement only P0.5-B2. Plan 0011 owns P0 closure evidence; P1 is excluded.
- No text, name, alias, conversation ID, face, voice, HTTP field, or LLM output
  can supply trusted identity or consent.
- Every tool follows: closed predicate -> tool policy/audit -> reader
  policy/audit -> bounded active-v4 read. A non-allowed outcome never calls a
  raw reader, entity-label lookup, legacy memory, prompt, or LLM.
- Use existing integer IDs and closed v4 predicates only. Never use v3 facts,
  vector memory, free-text lookup, aliases, generated SQL, or prompt context as
  family truth.
- `child_of` and `birth_date` require injected `ConsentStatus.GRANTED`;
  `likes`, `dislikes`, and `prefers` are normal household data. Medical data is
  not a B2 tool capability.
- Keep migrations 1–5, public schemas, `/transcribe`, audio, server/robot
  boundary, local-only providers, and v4 writes unchanged.
- Add no dependency, environment variable, migration, endpoint, public
  identity/consent path, cloud, biometrics, name grounding, or model call.
- Type/document every public API, freeze Pydantic values, use logger not
  `print()`, and avoid bare `except`, `Any`, and unexplained suppressions.
- Work on a feature branch. Every task requires real RED/GREEN evidence,
  privacy review, Conventional Commit, green CI, and merge before the next PR.

## Permitted files

| Path | Responsibility |
|---|---|
| `server/src/server/memory/entity_labels.py` | Exact person ID to display label without legacy facts. |
| `server/src/server/cognition/household_tools.py` | Closed family tools plus tool policy/audit boundary. |
| `server/src/server/cognition/controller.py` | Narrow child list/count orchestration. |
| `server/src/server/cognition/response_plan.py` | Two closed information needs only. |
| `server/src/server/cognition/__init__.py` | New cognitive public exports only. |
| `server/src/server/routers/chat.py` | Compose tools but preserve public unknown actor. |
| `tests/unit/test_entity_labels.py` | Exact label lookup behavior. |
| `tests/unit/test_household_knowledge_tools.py` | Tool ordering, privacy, age, count, preferences. |
| `tests/unit/test_cognitive_controller.py` | Trusted dispatch and no legacy fallback. |
| `tests/integration/test_chat_endpoint.py` | Public no-v4-read guarantee. |
| `tests/integration/test_p05b2_household_acceptance.py` | Synthetic end-to-end P0 acceptance. |
| Canonical status/plan/roadmap docs | Actual post-merge evidence only. |

No other source files are permitted. Do not modify `text_turn.py`, legacy
memory, predicate registry, policy rules, migrations, providers, prompts,
robot code, audio, or public request/response schemas.

## Locked contracts

### Minimal label reader

```python
class EntityLabel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    entity_id: int
    display_name: str
```

**Function signature:**
`async def get_person_label(*, entity_id: int) -> EntityLabel | None`

The production function gets the existing request-scoped SQLite connection from
`server.db.get_conn`; `HouseholdKnowledgeTools` receives this function as its
injectable label-reader boundary. The sole query is parameterized and exact:
`SELECT id, name FROM entities WHERE id = ? AND type = ?`. It selects no facts
and imports no v3 context, router, controller, provider, prompt, or LLM code.

### Household tool service

```python
class HouseholdToolName(StrEnum):
    GET_CHILDREN = "get_children"
    COUNT_CHILDREN = "count_children"
    GET_PREFERENCES = "get_preferences"
    GET_PERSON_BIRTH_DATE = "get_person_birth_date"
    CALCULATE_PERSON_AGE = "calculate_person_age"


class PreferencePredicate(StrEnum):
    LIKES = "likes"
    DISLIKES = "dislikes"
    PREFERS = "prefers"


class HouseholdToolResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    tool_name: HouseholdToolName
    status: KnowledgeStatus
    value: str | int | tuple[str, ...] | None = None
    reason: str | None = None
```

`HouseholdKnowledgeTools` injects `PolicyEvaluator`, `AuditWriter`,
`PolicyGatedV4Reader`, and the label reader. Public methods are
`get_children`, `count_children`, `get_preferences`, `get_person_birth_date`,
and `calculate_person_age`; all receive typed entity IDs, actor, consent,
correlation ID, and aware request time; age also receives a `date`.

Private closed metadata maps children to `child_of`, birth/age to `birth_date`,
and preferences to the exact `PreferencePredicate`. It constructs an
`EXECUTE_HOUSEHOLD_TOOL` request using predicate visibility/sensitivity,
evaluates and audits exactly once, then invokes B1 with the same actor, consent,
correlation ID, time, predicate, and bounded ID.

Non-allowed execution or reader results return `UNAUTHORIZED`, no value, and
the fixed reason `"household tool is not authorized"`. Empty allowed data is
`UNKNOWN`. `count_children` counts unique source IDs. `get_children` reads
person labels only after a known relation read and returns no partial list if a
label is absent. Preferences preserve active row order. One known birth date is
passed to existing `calculate_age`; multiple active birth dates return
`CONTRADICTORY`; raw repository failures propagate.

### Narrow controller integration

Add `OWN_CHILDREN_LIST` and `OWN_CHILDREN_COUNT` to `InformationNeed`. Match
only `como se llaman mis hijos` and `cuantos hijos tengo`, accented or not,
before generic household terms. `CognitiveController` receives optional
`household_tools` plus internal `consent_resolver(event, actor) -> ConsentStatus`;
the default is `NOT_REQUIRED`. The public router composes real tools but still
provides only `_public_unknown_actor` and no consent from HTTP.

Known responses are deterministic: `Tus hijos son Máximo y Sofía.` and
`Tienes 2 hijos.` Unknown/contradictory cases explain the limitation;
unauthorized uses the existing safe response. None reaches legacy text,
prompting, or an LLM.

## Task 1: Exact person-label lookup

**Files:** create `entity_labels.py`; create `test_entity_labels.py`.

- [ ] Write tests using an `AsyncMock` connection/cursor. Assert a person row
  returns immutable `EntityLabel`, missing/non-person rows return `None`, and
  the query/parameters are exactly the locked SQL and `(entity_id, "person")`.
- [ ] RED: run `uv run pytest tests/unit/test_entity_labels.py -v`; expect an
  import failure because the module is absent.
- [ ] Add the frozen model and exact reader. Close the cursor on both outcomes.
- [ ] GREEN: rerun the same test command.
- [ ] Review imports with `git diff --check`; commit
  `feat(memory): add exact person label lookup`.

## Task 2: Closed household tools

**Files:** create `household_tools.py`; create `test_household_knowledge_tools.py`.

- [ ] Write failing unit tests with injected fakes for: unknown actor audited
  then denied before reader; consented owner call order
  `tool-policy -> tool-audit -> reader -> labels`; missing label produces
  unknown/no partial names; multiple likes remain; no consent blocks birth/age;
  one birth date calculates age; two birth dates are contradictory.
- [ ] RED: run `uv run pytest tests/unit/test_household_knowledge_tools.py -v`;
  expect import failure for the absent service.
- [ ] Implement types, closed metadata, tool authorization/audit, then B1
  composition and result mapping exactly as locked above.
- [ ] GREEN and static checks:

  ```text
  uv run pytest tests/unit/test_household_knowledge_tools.py -v
  uv run ruff check server/src/server/cognition/household_tools.py tests/unit/test_household_knowledge_tools.py
  uv run ruff format --check server/src/server/cognition/household_tools.py tests/unit/test_household_knowledge_tools.py
  uv run mypy server/src/server/cognition/household_tools.py
  uv run pyright server/src/server/cognition/household_tools.py
  ```

- [ ] Confirm denied paths never call reader/label and audit carries no data
  values. Commit `feat(cognition): add policy-gated household tools`.

## Task 3: Narrow controller and public denial

**Files:** modify controller, response plan, exports, router, controller tests,
and chat-endpoint tests.

- [ ] Write failing tests: trusted consented owner gets deterministic child
  list/count with no legacy delegate; unresolved actor receives unauthorized
  before fake tools; public `/chat` child question never awaits the v4 relation
  reader and keeps its unchanged schema.
- [ ] RED: run controller and chat endpoint test files; expect new assertions
  to fail because P0.5-A still returns the unconnected outcome.
- [ ] Add only the two information needs and deterministic dispatch. Resolve
  actor/consent exclusively through constructor injection. The router composes
  real tools but has no new request field.
- [ ] GREEN:

  ```text
  uv run pytest tests/unit/test_cognitive_controller.py tests/unit/test_household_knowledge_tools.py -v
  uv run pytest tests/integration/test_chat_endpoint.py tests/integration/test_policy_gated_v4_reader.py -v
  uv run ruff check server/src/server/cognition server/src/server/routers/chat.py tests/unit/test_cognitive_controller.py tests/integration/test_chat_endpoint.py
  uv run ruff format --check server/src/server/cognition server/src/server/routers/chat.py tests/unit/test_cognitive_controller.py tests/integration/test_chat_endpoint.py
  ```

- [ ] Confirm public chat accepts no identity/consent input and all child paths
  bypass legacy/LLM. Commit
  `feat(cognition): route trusted child queries through tools`.

## Task 4: Disposable-SQLite P0 acceptance

**Files:** create `tests/integration/test_p05b2_household_acceptance.py`.

- [ ] Write failing tests with a temporary database, migrations 1–5, explicit
  owner bootstrap, and synthetic v4 entities only. Prove a consented owner can
  list/count Máximo and Sofía; unconsented child queries produce only the tool
  audit (no data-read audit); preferences retain `café` and `robótica`; and age
  is 8 from `birth_date`, not stored age.
- [ ] Also assert success audit action order is `execute_household_tool`, then
  `read_household_data`, and that audit fields contain no child name, birth
  date, preference value, or age.
- [ ] RED: run
  `uv run pytest tests/integration/test_p05b2_household_acceptance.py -v`.
- [ ] Make only test-supported corrections; do not add routes, real-household
  data, consent persistence, models, hardware, or P1 adapters.
- [ ] GREEN:

  ```text
  uv run pytest tests/integration/test_p05b2_household_acceptance.py -v
  uv run pytest tests/unit/test_entity_labels.py tests/unit/test_household_knowledge_tools.py tests/unit/test_cognitive_controller.py -v
  uv run pytest tests/integration/test_policy_gated_v4_reader.py tests/integration/test_household_authorization_runtime.py tests/integration/test_chat_endpoint.py -v
  ```

- [ ] Commit `test(cognition): cover policy-gated household acceptance`.

## Task 5: B2 PR and evidence

- [ ] Inspect `git diff --name-only main...HEAD`; stop if any forbidden module
  changed. Confirm no public identity/consent schema was added.
- [ ] Run `just lint`, `just typecheck`, `just test`, `just audit`, `just
  check`, and `git diff --check`; record actual output only.
- [ ] Request/reconcile review, open a non-draft code PR, and merge only with
  green GitHub CI. Return to updated `main`.
- [ ] In a separate documentation PR, record RED/GREEN, gates, merge SHA, and
  B2 limitations in current state, plans, portfolio, and roadmap. Keep Plan
  0011 Draft until its revalidation.

## Rollback and stop conditions

No migration or durable knowledge write is introduced. Reverting B2 removes the
label lookup, internal tools, and narrow dispatch while keeping v4 storage,
roles, audit history, B1 reader, public schema, and legacy runtime intact.

Stop for an ADR/design if implementation requires public identity/consent,
name grounding, policy changes, confirmation persistence, v3/vector access,
migration, dependency, endpoint/schema change, cloud/model path, biometrics,
world state, hardware action, or audio/server-robot change.

## Execution evidence

- Observed RED/GREEN cycles covered the absent exact-label reader, absent
  household-tool service, and absent controller tool injection. The final
  acceptance suite uses a disposable SQLite database and migrations 1--5.
- Local final verification before PR #48 passed: `just lint`, `just
  typecheck`, `just test` (**571 passed**), `just audit`, `just check`, and
  `git diff --check`.
- GitHub CI for PR #48 passed the Conventional Commit title, Quality & Security,
  Automated Tests, Python analysis, and CodeQL checks. It merged to `main` as
  `0d16969`.
- The post-merge P0 closure revalidation passed the named acceptance paths (20
  tests), then repeated all local gates on `main`. No real household data,
  public identity/consent flow, Ollama request, camera, microphone, LAN, or
  hardware acceptance was exercised by this plan.
