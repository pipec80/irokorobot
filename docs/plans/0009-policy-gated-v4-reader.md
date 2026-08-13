# P0.5-B1 Policy-Gated V4 Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [x]`) syntax for execution history.

**Goal:** Add an auditable, policy-gated reader for bounded active v4 literal
facts and entity relations, without connecting any v4 value to controller,
prompt, public HTTP, or family-tool runtime behavior.

**Architecture:** A new memory-application service resolves a closed predicate,
constructs `READ_HOUSEHOLD_DATA` from immutable predicate metadata, evaluates
and audits policy, and only then calls an injected raw v4 reader. It returns
frozen `known`, `unknown`, or `unauthorized` results. The existing raw
repository gains only a backward-compatible target-ID relation filter.

**Tech Stack:** Python 3.12, Pydantic v2, aiosqlite/SQLite, existing P0.4 v4
repositories, existing P0.5 authorization/audit services, pytest, Ruff, mypy,
Pyright, and pre-commit.

## Global Constraints

- Implement only [Plan 0008](0008-policy-gated-v4-household-tools-design.md)
  P0.5-B1. P0.5-B2 controller patterns and family tools are not authorized.
- Identity, role, consent, and authorization remain distinct. No name,
  conversation ID, HTTP input, face, voice, or LLM output may grant access.
- Evaluate and safely audit policy before every raw v4 read. Denied or
  confirmation-required requests never execute a raw reader or reveal record
  existence.
- Keep the closed P0.5 action/category/consent vocabulary and policy matrix.
  Do not issue/persist consent or add a confirmation/session mechanism.
- Query only active v4 rows using a closed registry predicate and explicit
  integer IDs. Never query v3/vector memory, free-text entity lookup, prompts,
  LLMs, or SQL assembled from input.
- Preserve migrations 1–5, v4 writes/migration behavior, public schemas, the
  audio contract, server/robot boundary, and local-only providers. No new
  dependency, env var, HTTP endpoint, cloud, biometric path, or migration.
- Use frozen Pydantic values, type every public API, add Google docstrings, and
  use explicit exceptions/logger rather than `print()`.
- Work in a feature branch. Every task records RED, focused GREEN, a privacy
  diff review, and a Conventional Commit; never commit directly to `main`.

---

## File Structure

| Path | Responsibility |
|---|---|
| `server/src/server/memory/relational_v4.py` | Raw v4 storage boundary; add optional target-ID filter to active-relation lookup. |
| `server/src/server/memory/policy_gated_v4_reader.py` | New typed reader: predicate resolution, policy/audit ordering, bounded reads, non-disclosing outcomes. |
| `tests/integration/test_memory_v4_repository.py` | Prove the raw target filter selects only requested active relations. |
| `tests/unit/test_policy_gated_v4_reader.py` | Prove policy/audit/read ordering and no-read outcomes with injected fakes. |
| `tests/integration/test_policy_gated_v4_reader.py` | Prove local SQLite v4/role/audit composition without real models. |
| `docs/architecture/current-state.md` | Record completion evidence only after final gates/PR CI/merge. |
| `docs/plans/0009-policy-gated-v4-reader.md` | Record actual execution evidence and limits only after final gates. |
| `docs/plans/README.md`, `docs/plans/p0-cognitive-plan-portfolio-design.md` | Record B1 completion; retain B2 and P0-final as Draft. |

No other file is permitted. Do not modify `controller.py`, `routers/chat.py`,
`text_turn.py`, legacy modules, predicate registry, migrations, role service,
policy rules, providers, prompts, audio, robot, or public schemas.

## Locked Interfaces

### Raw repository extension

Extend the existing function without breaking current callers:

`get_active_entity_relations(*, definition: PredicateDefinition,
source_entity_id: int | None = None, target_entity_id: int | None = None) ->
list[EntityRelationV4]`

When `target_entity_id` is present append the parameterized condition
`target_entity_id = ?`. If both IDs exist intersect them; if neither exists,
preserve the existing predicate-bounded raw behavior. The application reader
must require exactly one relation endpoint and therefore never make an
unbounded relation request.

### Typed policy-gated reader

Create `server.memory.policy_gated_v4_reader` with frozen results:

```python
class LiteralReadResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: KnowledgeStatus
    facts: tuple[LiteralFactV4, ...] = ()
    reason: str | None = None


class RelationReadResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: KnowledgeStatus
    relations: tuple[EntityRelationV4, ...] = ()
    reason: str | None = None


`PolicyGatedV4Reader.read_active_literals(*, actor: ActivePersonContext,
subject_entity_id: int, predicate_alias: str, consent: ConsentStatus,
correlation_id: UUID, requested_at: datetime) -> LiteralReadResult`

`PolicyGatedV4Reader.read_active_relations(*, actor: ActivePersonContext,
predicate_alias: str, source_entity_id: int | None = None,
target_entity_id: int | None = None, consent: ConsentStatus,
correlation_id: UUID, requested_at: datetime) -> RelationReadResult`
```

The constructor injects `PolicyEvaluator`, `AuditWriter`, `LiteralReader`, and
`RelationReader` callable aliases defaulting to `evaluate_authorization`,
`record_authorization_decision`, `get_active_literal_facts`, and
`get_active_entity_relations`. This is testability, not a tool framework.

Resolve the alias before all policy/audit/read work. A wrong/unsupported kind
returns `UNKNOWN`, an empty tuple, and no reason without collaborator calls.
For a valid predicate construct `AuthorizationRequest` with
`READ_HOUSEHOLD_DATA`, the supplied actor/consent/correlation/time, one
`DataVisibility` and one `DataSensitivity` converted from the predicate
definition, and the selected endpoint as `target_person_id`.

Then evaluate and audit exactly once. Non-`ALLOWED` returns `UNAUTHORIZED`, an
empty tuple, and the fixed reason `"household data is not authorized"`; it
never calls raw storage. An allowed empty result returns `UNKNOWN`, empty tuple,
and `"no active authorized record"`. An allowed non-empty result returns
`KNOWN`, immutable rows, and no reason. Do not expose
`AuthorizationDecision.reason` or record values to callers/audit.

`read_active_relations` rejects both-or-neither endpoint filters with
`ValueError` before predicate resolution, policy, audit, or database access.
Raw repository/database exceptions remain available failures; never mislabel
them as `unknown` or `unauthorized`.

## Task 1: Add inverse relation target filter

**Files:**
- Modify: `server/src/server/memory/relational_v4.py:244-267`
- Test: `tests/integration/test_memory_v4_repository.py`

**Consumes:** Existing temporary v4 fixture, `child_of` predicate, and
`assert_entity_relation()`.

**Produces:** Target-filtered active relation lookup with parameterized
intersection semantics.

- [x] **Step 1: Write the failing test**

Add this test beside existing relation tests:

```python
@pytest.mark.integration
async def test_relation_target_filter_returns_only_active_inverse_matches(
    household_db: None,
) -> None:
    felipe_id = await upsert_entity(name="Felipe", type="person")
    maximo_id = await upsert_entity(name="Maximo", type="person")
    sofia_id = await upsert_entity(name="Sofia", type="person")
    ana_id = await upsert_entity(name="Ana", type="person")
    child_of = _predicate("hijo_de")
    for child_id, parent_id in ((maximo_id, felipe_id), (sofia_id, felipe_id), (ana_id, sofia_id)):
        await assert_entity_relation(
            source_entity_id=child_id,
            target_entity_id=parent_id,
            definition=child_of,
        )

    relations = await get_active_entity_relations(
        definition=child_of,
        target_entity_id=felipe_id,
    )

    assert {relation.source_entity_id for relation in relations} == {maximo_id, sofia_id}
    assert {relation.target_entity_id for relation in relations} == {felipe_id}
```

- [x] **Step 2: Verify RED**

Run: `uv run pytest tests/integration/test_memory_v4_repository.py::test_relation_target_filter_returns_only_active_inverse_matches -v`

Expected: `FAIL` because the function has no `target_entity_id` parameter.

- [x] **Step 3: Implement the minimal filter**

Extend only the existing query builder:

```python
if source_entity_id is not None:
    sql += " AND source_entity_id = ?"
    params += (source_entity_id,)
if target_entity_id is not None:
    sql += " AND target_entity_id = ?"
    params += (target_entity_id,)
```

Update the public docstring to name both filters and preserve the explicit
statement that this raw repository has no runtime authorization behavior.

- [x] **Step 4: Verify GREEN**

Run: `uv run pytest tests/integration/test_memory_v4_repository.py -v`

Expected: all repository tests pass, including the target filter.

- [x] **Step 5: Review and commit**

Run `git diff --check`; inspect that only the filter/test changed.

Commit: `feat(memory): filter active v4 relations by target`

## Task 2: Create and unit-test the policy-gated reader

**Files:**
- Create: `server/src/server/memory/policy_gated_v4_reader.py`
- Create: `tests/unit/test_policy_gated_v4_reader.py`

**Consumes:** P0.2 actor, P0.5 authorization contracts, predicate registry,
raw v4 row models, and injected read collaborators.

**Produces:** `PolicyGatedV4Reader`, `LiteralReadResult`, and
`RelationReadResult` for later internal application code only.

- [x] **Step 1: Write the failing unit tests**

Create these fixed helpers before the tests; imports are the matching existing
P0.2/P0.4/P0.5 contracts plus `AsyncMock`, `pytest`, and `UUID`:

```python
_NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
_CORRELATION_ID = UUID("22222222-2222-2222-2222-222222222222")


def _actor(role: HouseholdRole, person_id: int | None) -> ActivePersonContext:
    return ActivePersonContext(
        person_id=person_id,
        display_name="Ada" if person_id is not None else None,
        status=ActivePersonStatus.IDENTIFIED
        if person_id is not None
        else ActivePersonStatus.UNKNOWN,
        confidence=Confidence(
            score=1.0 if person_id is not None else 0.0,
            basis=ConfidenceBasis.ASSERTED
            if person_id is not None
            else ConfidenceBasis.NOT_APPLICABLE,
            calibrated=False,
        ),
        role=role,
        evidence=(),
        resolved_at=_NOW,
    )


def _literal_fact() -> LiteralFactV4:
    return LiteralFactV4(
        id=1,
        subject_entity_id=7,
        predicate="likes",
        value_text="robotica",
        confidence=1.0,
        source_memory_id=None,
        asserted_at="2026-08-12T12:00:00+00:00",
        valid_from=None,
        valid_to=None,
        lifecycle=AssertionLifecycle.ACTIVE,
        visibility="household",
        sensitivity="normal",
        superseded_at=None,
        superseded_by=None,
    )


def _allowed_decision(request: AuthorizationRequest, calls: list[str]) -> AuthorizationDecision:
    calls.append("policy")
    return AuthorizationDecision(
        decision=AuthorizationStatus.ALLOWED,
        action=request.action,
        data_categories=frozenset({"household", "normal"}),
        policy_id="test.allowed",
        reason="safe test reason",
        evaluated_at=request.requested_at,
        correlation_id=request.correlation_id,
    )


async def _audit(calls: list[str]) -> None:
    calls.append("audit")


async def _one_literal(calls: list[str]) -> list[LiteralFactV4]:
    calls.append("raw")
    return [_literal_fact()]
```

Use `_actor(HouseholdRole.UNKNOWN, None)` and
`_actor(HouseholdRole.OWNER, 7)` directly in the tests below. Add at least
these cases:

```python
@pytest.mark.asyncio
async def test_unknown_actor_is_audited_and_cannot_read_preferences() -> None:
    raw_reader = AsyncMock()
    audit_writer = AsyncMock()
    result = await PolicyGatedV4Reader(
        literal_reader=raw_reader,
        audit_writer=audit_writer,
    ).read_active_literals(
        actor=_actor(HouseholdRole.UNKNOWN, None),
        subject_entity_id=7,
        predicate_alias="le_gusta",
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=_CORRELATION_ID,
        requested_at=_NOW,
    )

    assert result.status is KnowledgeStatus.UNAUTHORIZED
    assert result.facts == ()
    audit_writer.assert_awaited_once()
    raw_reader.assert_not_awaited()
```

```python
@pytest.mark.asyncio
async def test_allowed_read_audits_before_raw_reader() -> None:
    calls: list[str] = []
    reader = PolicyGatedV4Reader(
        policy_evaluator=lambda request: _allowed_decision(request, calls),
        audit_writer=lambda _request, _decision: _audit(calls),
        literal_reader=lambda **_kwargs: _one_literal(calls),
    )
    result = await reader.read_active_literals(
        actor=_actor(HouseholdRole.OWNER, 7),
        subject_entity_id=7,
        predicate_alias="le_gusta",
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=_CORRELATION_ID,
        requested_at=_NOW,
    )

    assert calls == ["policy", "audit", "raw"]
    assert result.status is KnowledgeStatus.KNOWN
    assert result.facts == (_literal_fact(),)
```

Also cover: wrong/unsupported kind invokes no collaborator; allowed empty read
is `UNKNOWN`; confirmation-required `child_of` audits but skips raw storage;
and both/neither relation endpoint filters raise before all collaborators.

- [x] **Step 2: Verify RED**

Run: `uv run pytest tests/unit/test_policy_gated_v4_reader.py -v`

Expected: `FAIL` with `ModuleNotFoundError` for the new reader module.

- [x] **Step 3: Implement the smallest service**

The authorization helper must follow this exact ordering:

```python
request = AuthorizationRequest(
    actor=actor,
    action=AuthorizationAction.READ_HOUSEHOLD_DATA,
    target_person_id=target_person_id,
    visibility=frozenset({DataVisibility(definition.default_visibility)}),
    sensitivity=frozenset({DataSensitivity(definition.default_sensitivity)}),
    consent=consent,
    correlation_id=correlation_id,
    requested_at=requested_at,
)
decision = self._policy_evaluator(request)
await self._audit_writer(request, decision)
if decision.decision is not AuthorizationStatus.ALLOWED:
    return _unauthorized_result()
facts = await self._literal_reader(
    subject_entity_id=subject_entity_id,
    definition=definition,
)
return _literal_result_from_rows(facts)
```

The relation method uses the same authorization helper, then calls exactly one
of these parameterized forms according to its validated endpoint:

```python
relations = await self._relation_reader(
    definition=definition,
    source_entity_id=source_entity_id,
)
relations = await self._relation_reader(
    definition=definition,
    target_entity_id=target_entity_id,
)
```

Keep safe result builders private. Do not catch raw-reader exceptions, create
SQL, import `controller`, `router`, `text_turn`, or a provider.

- [x] **Step 4: Verify GREEN and static checks**

Run:

```text
uv run pytest tests/unit/test_policy_gated_v4_reader.py -v
uv run ruff check server/src/server/memory/policy_gated_v4_reader.py tests/unit/test_policy_gated_v4_reader.py
uv run ruff format --check server/src/server/memory/policy_gated_v4_reader.py tests/unit/test_policy_gated_v4_reader.py
uv run mypy server/src/server/memory/policy_gated_v4_reader.py
uv run pyright server/src/server/memory/policy_gated_v4_reader.py
```

Expected: all pass without warning or suppression.

- [x] **Step 5: Privacy review and commit**

Confirm result objects expose neither policy reasons nor audit values; no
free-text reaches SQL; and no module imports a router, controller, provider,
or legacy v3 path.

Commit: `feat(memory): add policy-gated v4 reader`

## Task 3: Prove real SQLite/audit behavior

**Files:**
- Create: `tests/integration/test_policy_gated_v4_reader.py`

**Consumes:** Temporary migrations 1–5, P0.4 writers, P0.5 bootstrap/policy/audit,
and the new service.

**Produces:** Local integration evidence for allowed and denied reads without a
model, real household database, or public route.

- [x] **Step 1: Write failing integration tests**

Create this fixture/helper boundary, mirroring the existing P0.4/P0.5 temporary
database setup. It must never use a household database:

```python
@pytest.fixture
async def policy_reader_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "policy-gated-v4-reader.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield
    await db.close_db()
    db._conn = None


def _predicate(alias: str) -> PredicateDefinition:
    definition = resolve_predicate(alias)
    assert definition is not None
    return definition


def _identified_owner(owner_id: int) -> ActivePersonContext:
    return ActivePersonContext(
        person_id=owner_id,
        display_name="Owner",
        status=ActivePersonStatus.IDENTIFIED,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.ASSERTED, calibrated=False),
        role=HouseholdRole.OWNER,
        evidence=(),
        resolved_at=_NOW,
    )
```

Seed people, bootstrap an owner, and add v4 rows only through existing writers.
Cover:

```python
@pytest.mark.integration
async def test_owner_reads_normal_preference_and_audit_never_contains_value(
    policy_reader_db: None,
) -> None:
    owner_id = await upsert_entity(name="Owner", type="person")
    await bootstrap_initial_owner(
        person_entity_id=owner_id,
        confirmed_person_entity_id=owner_id,
    )
    await assert_literal_fact(
        subject_entity_id=owner_id,
        definition=_predicate("le_gusta"),
        value="robotica",
    )

    result = await PolicyGatedV4Reader().read_active_literals(
        actor=_identified_owner(owner_id),
        subject_entity_id=owner_id,
        predicate_alias="le_gusta",
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=_CORRELATION_ID,
        requested_at=_NOW,
    )

    assert result.status is KnowledgeStatus.KNOWN
    assert [fact.value_text for fact in result.facts] == ["robotica"]
    cursor = await db.get_conn().execute(
        "SELECT action, data_categories, decision, policy_id, reason FROM authorization_audit_events"
    )
    rows = await cursor.fetchall()
    await cursor.close()
    assert rows == [
        (
            "read_household_data",
            "household,normal",
            "allowed",
            "p0.5.owner-household",
            "Policy permits normal household data.",
        ),
    ]
    assert all("robotica" not in str(column) for row in rows for column in row)
```

Add this consent-gate test in the same fixture:

```python
@pytest.mark.integration
async def test_child_relation_requires_consent_before_target_read(
    policy_reader_db: None,
) -> None:
    owner_id = await upsert_entity(name="Owner", type="person")
    child_id = await upsert_entity(name="Child", type="person")
    await bootstrap_initial_owner(
        person_entity_id=owner_id,
        confirmed_person_entity_id=owner_id,
    )
    await assert_entity_relation(
        source_entity_id=child_id,
        target_entity_id=owner_id,
        definition=_predicate("hijo_de"),
    )
    reader = PolicyGatedV4Reader()

    denied = await reader.read_active_relations(
        actor=_identified_owner(owner_id),
        predicate_alias="hijo_de",
        target_entity_id=owner_id,
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=_CORRELATION_ID,
        requested_at=_NOW,
    )
    allowed = await reader.read_active_relations(
        actor=_identified_owner(owner_id),
        predicate_alias="hijo_de",
        target_entity_id=owner_id,
        consent=ConsentStatus.GRANTED,
        correlation_id=UUID("33333333-3333-3333-3333-333333333333"),
        requested_at=_NOW,
    )

    assert denied.status is KnowledgeStatus.UNAUTHORIZED
    assert denied.relations == ()
    assert allowed.status is KnowledgeStatus.KNOWN
    assert [relation.source_entity_id for relation in allowed.relations] == [child_id]
```

Query the two audit rows only for action/category/decision/correlation and
assert none contains a child name or any fact value.

- [x] **Step 2: Verify RED**

Run: `uv run pytest tests/integration/test_policy_gated_v4_reader.py -v`

Expected: `FAIL` until the service composes actual repository/policy/audit
collaborators correctly.

- [x] **Step 3: Make only test-supported corrections**

Correct reader or fixture contracts only. Do not add schema columns, change
policy rules, add routes, or test against a household database.

- [x] **Step 4: Verify GREEN and regressions**

Run:

```text
uv run pytest tests/unit/test_policy_gated_v4_reader.py tests/integration/test_policy_gated_v4_reader.py -v
uv run pytest tests/integration/test_memory_v4_repository.py tests/integration/test_household_authorization_runtime.py -v
uv run pytest tests/unit/test_household_authorization_policy.py -v
```

Expected: all listed suites pass with no model, camera, microphone, LAN, cloud,
or real household database involved.

- [x] **Step 5: Commit integration evidence**

Commit: `test(memory): cover policy-gated v4 reader`

## Task 4: Final review, documentation, and handoff

**Files:**
- Modify: `docs/architecture/current-state.md`
- Modify: `docs/plans/0009-policy-gated-v4-reader.md`
- Modify: `docs/plans/README.md`
- Modify: `docs/plans/p0-cognitive-plan-portfolio-design.md`

**Consumes:** Actual local command outputs, reviewed diff, PR CI, and merge.

**Produces:** Evidence-backed B1 completion without marking B2 or P0 complete.

- [x] **Step 1: Check the boundary**

Run:

```text
git diff main...HEAD -- server/src/server/memory/relational_v4.py server/src/server/memory/policy_gated_v4_reader.py tests
rg -n "policy_gated_v4_reader|literal_facts_v4|entity_relations_v4" server/src/server/cognition/controller.py server/src/server/routers/chat.py server/src/server/text_turn.py
```

Expected: only the new reader reaches raw v4 retrieval. If controller, `/chat`,
or `text_turn.py` reaches a v4 value, stop rather than widening B1.

- [x] **Step 2: Run final quality gates**

Run:

```text
just lint
just typecheck
just test
just audit
just check
git diff --check
```

Expected: every command passes. Record actual results/counts and unavailable
hardware/model checks; do not copy historical evidence.

- [x] **Step 3: Update evidence only after verification**

Mark B1 complete only after local gates, scope/privacy review, PR CI, and merge
evidence. State that B2 tools/controller, public trusted identity, consent
persistence, and P1 onboarding remain unimplemented. Do not mark P0 complete.

- [x] **Step 4: Commit docs and open one PR**

Commit: `docs(cognition): record policy-gated v4 reader evidence`

Merge only after GitHub CI is green. Return to updated `main` and revalidate
before writing the B2 plan.

## Execution evidence

Plan 0009 is **Complete**. The implementation was split into three
Conventional Commits on `feat/p05b-policy-gated-v4-reader`:

- `9f43302 feat(memory): filter active v4 relations by target`
- `7a64514 feat(memory): add policy-gated v4 reader`
- `7df3537 test(memory): cover policy-gated v4 reader`

Observed RED evidence:

- the target-filter test failed with `TypeError` because
  `get_active_entity_relations()` did not yet accept `target_entity_id`;
- the reader unit suite failed with `ModuleNotFoundError` before the new reader
  module existed.

Observed GREEN evidence included the targeted repository suite (7 passed), the
reader unit suite (6 passed), the reader SQLite/audit suite (2 passed), and
the combined relevant P0 suites (25 passed). The final local gates passed:
`just lint`; `just typecheck` (mypy: 73 source files with no issues; pyright:
0 errors); `just test` (555 passed in 54.17s); `just audit` (no known
vulnerabilities); `just check`; and `git diff --check`.

PR #45 passed GitHub conventional-title, quality/security, automated-test,
Python-analysis, and CodeQL checks, then squash-merged to `main` as
`a7550d0` on 2026-08-13. The reviewed boundary confirmed no references to the
reader or v4 tables from `controller.py`, `routers/chat.py`, or `text_turn.py`.
No camera, microphone, LAN, real Ollama inference, biometric enrollment, or
hardware acceptance was executed; none is required or reachable in this
reader-only slice.

P0.5-B2 family tools/controller wiring, public trusted identity, consent
persistence, and P1 onboarding remain unimplemented. This plan does not close
P0.

## Rollback

No migration or knowledge write is created. Reverting this plan removes only
the reader and optional target filter; existing v4 tables, roles, audits,
legacy data, and public routes remain intact. Automated tests use disposable
temporary databases only.

## Stop Conditions

Stop and write a new design/ADR if implementation requires public trusted
identity/consent, policy changes, confirmation persistence, name resolution,
controller/tool cutover, v3/vector retrieval, schema migration, dependency,
cloud, biometrics, world state, hardware action, or an audio/server-robot
contract change.
