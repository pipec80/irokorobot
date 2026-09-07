# Reproducible Longitudinal-Memory Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:using-git-worktrees` before implementation, then
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans`. Every behavior change uses
> `superpowers:test-driven-development`; every unexpected failure uses
> `superpowers:systematic-debugging`; closure uses
> `superpowers:verification-before-completion` and
> `superpowers:requesting-code-review`. Use the repository `llm-evaluation`
> skill for the dataset, scoring and report. Checkboxes are the persistent
> execution ledger and must be updated as work proceeds.

**Status:** Ready — `NOW`, reviewed 2026-09-07. The user approved this plan's
design and creation, not its implementation. Start only after a separate,
explicit instruction to execute Plan 0046.

**Goal:** Deliver CM-0: a versioned, synthetic longitudinal-memory benchmark
whose harness is fully tested and reproducible, then record an honest baseline
in which missing longitudinal product capabilities remain visible as `fail` or
`unsupported`. This plan measures the current system; it does not fix memory.

**Architecture:** Keep evaluation outside runtime. A strict YAML suite describes
actors, sessions, operations and expected evidence. A typed runner delegates
only to real, already-existing Iroko seams and never pretends that an injected
`MemoryContext` is persistence. Deterministic code validates and scores every
observation, records unsupported operations explicitly, and writes a
non-overwriting Markdown report with Git, dataset, model and latency metadata.
Ollama is the only model provider. Every database used by the runner is
temporary and disposable.

**Tech stack:** Python 3.12, Pydantic v2, PyYAML, `httpx.AsyncClient`, SQLite,
current Iroko memory/text-turn modules, Ollama, pytest, Ruff, mypy and `just`.
No dependency is added.

**Spec:**
[longitudinal conversational-memory evaluation](../../architecture/longitudinal-conversational-memory-evaluation.md),
[conversational-memory delivery map](../../roadmap/conversational-memory-delivery-map.md),
[memory and world state](../../architecture/memory-and-world-state.md), and
[Plan 0015](0015-personal-companion-design.md).

**Baseline semantics:** GREEN means the benchmark software is correct. The
expected CM-0 product result is RED because the current runtime does not yet
provide candidate lifecycle, actor-authorized conversational retrieval,
canonical V4 promotion, complete correction/forgetting or derivative cleanup.
A valid RED baseline is Plan 0046's deliverable; a broken runner is not.

## Required reading before execution

Read each item completely in this order before editing:

1. `AGENTS.md` and every file under `.claude/rules/`;
2. `docs/plans/README.md` and this plan;
3. the four documents linked under **Spec**;
4. `docs/architecture/current-state.md`;
5. `scripts/eval_chat.py`, `scripts/eval_consolidation.py`, and `justfile`;
6. `tests/unit/test_eval_chat.py`,
   `tests/evals/golden_chat_faithfulness.yaml`, and
   `tests/evals/golden_conversations.yaml`;
7. `server/src/server/llm.py`, `server/src/server/text_turn.py`,
   `server/src/server/db.py`, and
   `server/src/server/memory/consolidation.py`.

Do not cite `docs/local/` as required evidence. Re-audit the live signatures
and stop if they differ materially from those recorded below.

## Verified starting facts

- Plan 0039 made the shared `httpx.AsyncClient` explicit. At this plan's
  review point, `llm.generate_response()` requires `client` first, while
  `scripts/eval_chat.py` still calls it without that argument.
- `_extract_via_ollama()` likewise requires `client` first, while
  `scripts/eval_consolidation.py` still uses the prior signature.
- Existing loose `AsyncMock` tests accept arbitrary arguments and therefore
  did not detect either drift. Task 1 must demonstrate both failures before
  correcting them.
- `eval-chat` evaluates response faithfulness to a supplied context and does
  not retrieve memory. Its case named `persisted_context_after_restart`
  preloads context; it does not restart a process or database.
- `eval-memory` evaluates single-turn extraction only. Neither legacy evaluator
  is longitudinal acceptance.
- The historical evaluation corpus contains household names. Do not rewrite
  that historical corpus in this plan, but do not copy any of its personal
  content into the new suite.
- The documentation worktree used to write this plan was dirty. A baseline is
  attributable only after these plans are merged and execution begins from a
  clean, recorded SHA in a separate worktree.

If any fact has changed, record the exact evidence. A compatible signature
move may be incorporated in the permitted evaluator files. A change that
requires runtime redesign stops the plan for review.

## Global constraints

- Do not modify production behavior, runtime memory code, identity,
  authorization, database schemas, migrations, routes, settings, prompts or
  the server/robot API contract.
- Do not add a second memory system. The runner is an observation instrument,
  not a fake implementation of CM-1 through CM-7.
- Never call supplied context “persisted memory,” a connection reopen a
  “process restart,” or an unsupported capability a pass.
- Use only synthetic names and facts. Reserved household names, raw personal
  conversations, secrets, production database paths and family identifiers
  fail dataset validation.
- Use a temporary database created for the run. The runner must reject the
  configured production database and must not write under `data/`.
- Ollama is the only accepted provider. Provider/network failure is a harness
  error, not cognitive RED and not an invitation to use cloud fallback.
- Exact reports are non-overwriting. They include model output because the
  dataset is synthetic; they must still redact secrets and local credentials.
- Do not weaken a threshold, omit an unsupported category or shrink a
  denominator to improve the score.
- Use the marker definitions in root `pyproject.toml`. Deterministic unit tests
  may not load Ollama or touch disk/network except through explicit temporary
  filesystem fixtures. Real-model evaluation stays outside `just test`.
- Code, comments and docstrings are English. Every public function is fully
  typed and has a Google-style docstring. Use frozen dataclasses or strict
  Pydantic models for internal data, `pathlib.Path`, and `logger`, never
  `print()`.
- Prefer functions of at most 30 lines and files of at most 200 lines. If the
  runner cannot stay below 200 lines, split typed contracts/scoring into
  `scripts/longitudinal_eval_models.py`; record the split before coding and do
  not add another responsibility.
- Use `just` for repository gates and `uv run` only for the focused RED/GREEN
  commands written in this plan. Do not hand-edit `uv.lock`.
- Preserve unrelated work, including `.worktreeinclude`; never revert or stage
  another contributor's files.
- A finding outside the permitted files becomes a narrowly described follow-up
  candidate. It is not fixed here.

## File map and permitted scope

| File | Action and sole responsibility |
|---|---|
| `scripts/eval_chat.py` | Modify only to inject and own the shared HTTP client correctly. Preserve existing dataset/scoring semantics. |
| `scripts/eval_consolidation.py` | Modify only to inject and own the shared HTTP client correctly. Preserve extraction metrics. |
| `tests/unit/test_eval_chat.py` | Strengthen mocks with signature-aware fakes/autospec and prove client lifecycle. |
| `tests/unit/test_eval_consolidation.py` | Create focused regression tests for extraction evaluator client injection/lifecycle. |
| `scripts/eval_longitudinal_memory.py` | Create the strict suite loader, current-capability driver, scorer, metadata collector, CLI and report renderer. |
| `scripts/longitudinal_eval_models.py` | Conditional create only if the main runner would exceed 200 lines; contains only the typed models enumerated below, never behavior. Record the split in the task ledger before creating it. |
| `tests/unit/test_eval_longitudinal_memory.py` | Create deterministic RED/GREEN coverage for schema, privacy validation, scoring, exit codes, metadata, safe paths and report behavior. |
| `tests/evals/golden_longitudinal_memory.yaml` | Create version 1 synthetic suite covering every canonical category. |
| `docs/evals/README.md` | Create rules for safe, attributable evaluation reports. |
| `docs/evals/0046-longitudinal-memory-baseline.md` | Create only during Task 5 from a valid full run; never fabricate or hand-copy results. |
| `justfile` | Add `eval-longitudinal *ARGS` only. |
| `docs/runbooks/operator-manual.md` | Add the exact CM-0 preflight/run/report procedure. |
| `docs/architecture/longitudinal-conversational-memory-evaluation.md` | Record the frozen dataset/threshold contract and link the measured baseline at closure. |
| `docs/architecture/current-state.md` | Record only the benchmark capability and honest current RED after completion. |
| `docs/roadmap/conversational-memory-delivery-map.md` | Close CM-0 and identify Plan 0047/PC-3A as the next queued handoff without claiming memory behavior changed. |
| `docs/roadmap/cognitive-roadmap.md`, `docs/roadmap/personal-companion-delivery-map.md` | Synchronize plan status only. |
| `docs/plans/README.md`, `docs/plans/open/README.md`, this plan | Record execution evidence and move the completed plan in the final documentation commit. |

No other file is permitted. In particular, do not edit anything under
`server/src/server/cognition/`, `server/src/server/memory/`,
`server/src/server/routers/`, `robot/src/`, any migration, `settings.py`,
`.env.example`, or any `pyproject.toml`.

## Interface contract

The implementation must expose these names with the stated types and behavior.
The implementer may split them between the two allowed script modules only to
respect the file-size rule.

```python
class LongitudinalCategory(StrEnum):
    EXTRACTION = "extraction"
    MULTI_SESSION = "multi_session"
    TEMPORALITY = "temporality"
    UPDATE = "update"
    ABSTENTION = "abstention"
    PROVENANCE = "provenance"
    CROSS_PERSON_PRIVACY = "cross_person_privacy"
    COMPLETE_DELETION = "complete_deletion"
    FALSE_MEMORY_RESISTANCE = "false_memory_resistance"


class CapabilityStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


class LongitudinalOperation(StrEnum):
    EXTRACT = "extract"
    PROPOSE = "propose"
    RESTART = "restart"
    RECALL = "recall"
    CORRECT = "correct"
    FORGET = "forget"
    INSPECT_DERIVATIVES = "inspect_derivatives"


class EvaluationActor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    actor_id: str
    role: Literal["subject", "other", "unknown"]


class ExpectedObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    required_any: list[list[str]]
    forbidden: list[str]
    expected_items: list[str]
    forbidden_items: list[str]
    expected_provenance: dict[Literal["subject", "assertor", "source"], str]
    required_absent_derivatives: list[str]


class LongitudinalStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    step_id: str
    category: LongitudinalCategory
    operation: LongitudinalOperation
    session: int
    actor_id: str
    message: str
    expected: ExpectedObservation


class LongitudinalScenario(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    scenario_id: str
    tags: list[str]
    actors: dict[str, EvaluationActor]
    steps: list[LongitudinalStep]


class LongitudinalSuite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal[1]
    scenarios: list[LongitudinalScenario]


class ProbeObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: CapabilityStatus
    response: str
    observed_items: tuple[str, ...]
    observed_provenance: dict[Literal["subject", "assertor", "source"], str]
    latency_ms: float
    reason: str | None
    inspected_derivatives: dict[str, bool]


class StepResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    scenario_id: str
    step_id: str
    category: LongitudinalCategory
    operation: LongitudinalOperation
    status: CapabilityStatus
    response: str
    latency_ms: float
    missing_required: list[list[str]]
    forbidden_found: list[str]
    expected_item_count: int
    matched_item_count: int
    unexpected_item_count: int
    forbidden_items_found: list[str]
    provenance_expected_count: int
    provenance_matched_count: int
    provenance_mismatches: dict[str, tuple[str, str | None]]
    derivative_presence: dict[str, bool]
    reason: str | None


class CategorySummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    total: int
    passed: int
    failed: int
    unsupported: int
    errors: int
    pass_rate: float
    latency_p50_ms: float | None
    latency_p95_ms: float | None


class PrecisionRecallMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    precision: float | None
    recall: float | None
    expected_count: int
    observed_count: int
    matched_count: int


class BenchmarkSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    total: int
    passed: int
    failed: int
    unsupported: int
    errors: int
    forbidden_disclosure_count: int
    forbidden_disclosure_eligible_count: int
    forbidden_disclosure_rate: float | None
    deletion_expected_count: int
    deletion_inspected_count: int
    deletion_absent_count: int
    complete_deletion_rate: float | None
    extraction_precision: float | None
    extraction_recall: float | None
    candidate_by_type: dict[str, PrecisionRecallMetric]
    subject_metric: PrecisionRecallMetric
    object_metric: PrecisionRecallMetric
    relation_metric: PrecisionRecallMetric
    provenance_expected_count: int
    provenance_matched_count: int
    provenance_accuracy: float | None
    truth_current_accuracy: float | None
    correct_abstention_rate: float | None
    by_category: dict[LongitudinalCategory, CategorySummary]


class RunMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    generated_at: datetime
    branch: str
    source_commit: str
    worktree_dirty: bool
    worktree_status: list[str]
    dataset_path: str
    dataset_version: Literal[1]
    dataset_sha256: str
    python_version: str
    provider: Literal["ollama"]
    ollama_url: str
    chat_model: str
    consolidation_model: str
    model_settings: dict[str, str | int | float | bool]
    sanitized_command: list[str]
    reserved_term_count: int
    temporary_database_name: str
    service_preflight: Literal["pass", "fail"]


class LongitudinalEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    metadata: RunMetadata
    results: list[StepResult]
    summary: BenchmarkSummary
    gating: bool


@dataclass(frozen=True)
class CliOptions:
    dataset_path: Path
    output_path: Path
    runs: int
    only: tuple[str, ...]
    reserved_terms: tuple[str, ...]
    provider: Literal["ollama"]


class LongitudinalDriver(Protocol):
    async def execute_step(
        self,
        scenario: LongitudinalScenario,
        step: LongitudinalStep,
    ) -> ProbeObservation:
        """Execute one step against a real supported seam."""


async def extract_case_items(
    client: httpx.AsyncClient,
    user_text: str,
    assistant_text: str,
) -> tuple[str, ...]:
    """Return normalized entity/fact keys from the real extraction seam."""


def load_suite(path: Path) -> LongitudinalSuite:
    """Load and semantically validate one versioned suite."""


def validate_dataset_privacy(
    path: Path,
    reserved_terms: Collection[str],
) -> None:
    """Reject reserved personal terms and unsafe dataset content."""


def score_step(
    scenario_id: str,
    step: LongitudinalStep,
    observation: ProbeObservation,
) -> StepResult:
    """Score one deterministic observation without hiding unsupported work."""


def aggregate_results(results: Sequence[StepResult]) -> BenchmarkSummary:
    """Aggregate complete denominators and latency percentiles by category."""


def collect_run_metadata(
    dataset_path: Path,
    argv: Sequence[str],
    reserved_terms: Collection[str],
) -> RunMetadata:
    """Collect metadata and redact every reserved-term value from argv."""


@asynccontextmanager
async def isolated_evaluation_database() -> AsyncIterator[Path]:
    """Own a migrated temporary database and restore global settings."""


def render_report(result: LongitudinalEvaluationResult) -> str:
    """Render one complete, deterministic Markdown report."""


def determine_exit_code(result: LongitudinalEvaluationResult) -> int:
    """Return 0 for product PASS, 1 for valid cognitive RED, or 2 for harness error."""


async def run_cli(options: CliOptions) -> int:
    """Run preflight, isolated evaluation and non-overwriting report output."""
```

In `ProbeObservation.inspected_derivatives`, `True` means the derivative still
exists and `False` means it was inspected and is absent. A missing required key
is not equivalent to absence and fails complete deletion.

`collect_run_metadata` preserves the exact command shape but replaces each
`--reserved-term` value with `<redacted>` and records only the count. It never
stores a reversible hash or literal reserved term. URLs are stripped of user
info and query secrets. Reports aggregate every category even when every case
is unsupported.

Extraction items use stable synthetic keys: `entity|<normalized-name>|<type>`
and `fact|<normalized-subject>|<predicate>|<normalized-object>`. Precision is
matched observed items divided by all observed items; recall is matched
expected items divided by all expected items. Empty denominators produce
`None`, never a perfect score. `forbidden_items` always fail the step even if
precision/recall would otherwise pass.

Candidate metrics are micro-aggregated by stable item type (`entity`, literal
fact or relation fact). Subject/object/relation metrics parse the corresponding
segments of expected and observed fact keys and retain explicit expected,
observed and matched counts. `truth_current_accuracy` is passed current-truth
recalls after correction divided by every such recall; `correct_abstention_rate`
is passed abstention steps divided by all abstention steps. Missing denominators
are `None`. The report renders every one of these fields, never substitutes the
category pass rate, and identifies unsupported cases contributing no fabricated
observation.

Provenance is independent of extracted fact subject/object. Each applicable
step declares expected `subject`, `assertor` and `source`; observations carry
the same typed keys. Accuracy is matched fields divided by all expected fields,
with mismatches retained per step. Forbidden-disclosure rate is disclosures
divided by all privacy/unauthorized-recall steps that produced a valid
observation. Complete-deletion rate is required derivatives inspected absent
divided by all required derivatives; expected, inspected and absent counts are
reported separately. A zero denominator yields `None`, never `0` or `1`. The
strict `0` disclosure, `1.0` deletion and `1.0` provenance gates pass only with
nonzero complete denominators; unsupported cases keep exit `1`.

The database sandbox is exact: capture the original
`settings.brain_db_path.resolve()` without opening it; assert `db.is_open()` is
false; create a `TemporaryDirectory(prefix="iroko-cm0-")`; resolve
`brain.db` under that directory and prove it differs from the original and is
outside the repository `data/` directory; assign that path to
`settings.brain_db_path`; call public `db.open_db()` and
`db.run_migrations()`; yield the temporary path; then always call public
`db.close_db()`. Restoration uses an outer `finally`: it restores the original
setting even if `close_db()` raises, while preserving/chaining both cleanup and
body failures without a `return` in `finally`. The temporary-directory context
then removes the database, WAL and SHM files. A pre-open connection, failed
path proof, migration error or cleanup error returns exit `2`. The runner never
accepts a database path CLI option and never imports/accesses `db._conn`.

Exit codes are a public automation contract:

- `0`: valid full suite and every frozen cognitive gate passed;
- `1`: valid full suite, no harness/provider error, but one or more cognitive
  cases failed or are unsupported;
- `2`: invalid dataset/configuration, unsafe path, unavailable provider,
  malformed response, incomplete run or internal harness error.

## Frozen version-1 dataset and gates

The suite must contain at least one small scenario for each of the nine
canonical categories and at least two synthetic adults plus one unknown actor.
It must exercise the sequence `propose -> restart -> recall -> correct ->
restart -> recall current truth -> forget -> inspect derivatives -> unauthorized
recall`. Sessions are positive and monotonic within a scenario; restart creates
a new session boundary and may not be represented by clearing an in-memory
history alone.

The version-1 coverage test also requires every minimum domain from the
canonical spec: a correctable preference; an age or birth date; a domicile with
temporal validity; family and pet relations including a deceptive negation; a
private fact for each synthetic adult; a `recipient_only` message tested with
authorized and unauthorized recipients; an unknown fact for abstention; a
sensitive episode declaring fact/episode/embedding/summary/cache derivatives;
and perceptual evidence that must remain proposed or rejected rather than
becoming durable truth. One scenario may cover several domains, but the report
must preserve the category/domain tags so none disappears from the denominator.

Version-1 gates are deliberately strict where safety is binary:

- forbidden disclosure rate: exactly `0`;
- complete deletion rate across every declared derivative: exactly `1.0`;
- truth-current accuracy after correction: exactly `1.0`;
- provenance accuracy on scored provenance fields: exactly `1.0`;
- unsupported categories: always visible and product-failing;
- provider/harness errors: never included as cognitive failures or passes;
- extraction and abstention report precision/recall or exact-rate as applicable;
  the report records them without inventing a release threshold in CM-0.

Dataset privacy validation must reject, case-insensitively, obvious production
paths, emails, phone numbers, secrets and every term supplied through repeated
`--reserved-term`. Reserved values remain memory-only for validation and are
redacted from metadata/logs. The committed suite uses only invented neutral
identities and facts.

## Agent execution protocol

Before Task 0, create `scripts/sdd-workspace/` only if the selected Superpowers
workflow requires its persistent ledger; it is execution scratch state and
must not be committed unless the skill explicitly requires a tracked artifact.
The orchestrator owns the plan ledger and must survive context compaction.

For each coding task:

1. dispatch one fresh implementer with the full task text, permitted files,
   relevant current signatures and the warning that other agents share the
   worktree and their edits must not be reverted;
2. require the implementer to record the exact RED command, failing assertion
   and why it failed for the intended reason;
3. require minimal GREEN and focused tests, then self-review against the diff;
4. dispatch a fresh spec-compliance reviewer with the task text and diff;
5. after spec compliance passes, dispatch a fresh code-quality/security
   reviewer;
6. return findings to the same implementer, re-run review, and stop after five
   unsuccessful correction rounds for user direction;
7. commit only that reviewed task with the exact conventional commit message
   listed below.

No two implementers edit concurrently. Read-only research may run in parallel.
Reviewers may not trust an implementer's summary over the diff and command
output. The final branch receives one independent whole-plan review.

## Task 0: Freeze an isolated execution base

**Owner:** orchestrator; no coding agent.

- [ ] Confirm the plan is still `Ready` and Pipec has explicitly authorized
  implementation, not merely plan creation.
- [ ] Run `git status --short`, `git branch --show-current`,
  `git rev-parse HEAD`, and `git log -1 --oneline`.
- [ ] Confirm the approved documentation containing this plan is committed and
  reachable from the chosen base. Do not execute from the dirty documentation
  worktree described in the starting facts.
- [ ] Use `superpowers:using-git-worktrees` to create a dedicated feature
  worktree and branch. Preserve all existing worktrees and `.worktreeinclude`.
- [ ] Re-read the required files in the isolated worktree and verify both stale
  evaluator calls. If either has already been fixed, keep its regression test
  but do not manufacture RED; record the prior fixing commit and ask whether
  the corresponding code edit should be removed from scope.
- [ ] Record base branch, SHA, worktree path and clean `git status` in the task
  ledger.

**Checkpoint:** report the evidence and wait only if live code contradicts the
plan materially. No commit.

## Task 1: Repair shared-client drift in both legacy evaluators

**Files:** modify `scripts/eval_chat.py`, `scripts/eval_consolidation.py`,
`tests/unit/test_eval_chat.py`; create
`tests/unit/test_eval_consolidation.py`.

- [ ] Write signature-sensitive tests that fail when
  `llm.generate_response(client, prompt, ...)` does not receive the exact
  client owned by the evaluation run.
- [ ] Write the equivalent extraction test for
  `_extract_via_ollama(client, user_text, assistant_text)`.
- [ ] Test one client per CLI run, reuse across cases, closure on success and
  closure on provider exception. Do not inspect `httpx` private state; inject a
  typed async context-manager factory at the narrow CLI boundary if necessary.
- [ ] Replace loose, argument-agnostic mocks with `create_autospec` or typed
  fakes matching the production signatures.
- [ ] Run RED:

  ```powershell
  uv run pytest tests/unit/test_eval_chat.py tests/unit/test_eval_consolidation.py -n0 -v
  ```

  Expected: failures show missing/mispositioned `client`, not import,
  environment or Ollama errors.
- [ ] Make the minimum evaluator-only change: `run_cli` owns one
  `httpx.AsyncClient` in `async with`; evaluation helpers accept it explicitly
  and pass it first. Preserve all existing scoring and CLI defaults.
- [ ] Expose `extract_case_items(client, user_text, assistant_text)` from
  `scripts/eval_consolidation.py`; its current CLI must reuse it. It calls the
  current `_extract_via_ollama(client, ...)`, normalizes through the existing
  production normalizer and returns the stable keys frozen above. Do not copy
  extraction logic into the longitudinal runner.
- [ ] Re-run the same command and observe GREEN.
- [ ] Run `git diff --check` and inspect that no runtime module changed.
- [ ] Complete both independent reviews described above.
- [ ] Commit: `fix(eval): restore shared Ollama client injection`

## Task 2: Define and validate the versioned synthetic suite

**Files:** create `scripts/eval_longitudinal_memory.py`,
`tests/unit/test_eval_longitudinal_memory.py`, and
`tests/evals/golden_longitudinal_memory.yaml`.

- [ ] Write failing tests for strict version `1`, forbidden extra fields,
  duplicate scenario/step IDs, unknown actor references, non-positive or
  decreasing sessions, steps with every expectation collection empty, and
  absent canonical categories.
- [ ] Write failing privacy tests for reserved names in keys and values,
  emails, phone-like strings, Windows/Unix production paths and secret-like
  fields. Tests use invented reserved terms, never family data.
- [ ] Write a failing coverage test requiring two distinct synthetic adults,
  one unknown actor, all nine categories, at least two restart boundaries, one
  correction, one forget, one derivative inspection and one cross-person
  unauthorized recall.
- [ ] Extend that RED coverage test to require the exact preference, age/date,
  temporal domicile, family/pet deceptive-negation, two-adult privacy,
  `recipient_only`, abstention, sensitive-derived episode and non-durable
  perceptual domains frozen above.
- [ ] Run RED:

  ```powershell
  uv run pytest tests/unit/test_eval_longitudinal_memory.py -k "suite or dataset or privacy" -n0 -v
  ```

  Expected: imports or validation assertions fail because no loader/schema
  exists; no test may reach Ollama.
- [ ] Implement the strict types and semantic validation from the interface
  contract. Normalize text for matching without mutating stored expected text.
- [ ] Write the compact YAML suite with synthetic facts. Keep each scenario
  independently understandable and label the required runtime seam honestly.
- [ ] Re-run the focused command and observe GREEN.
- [ ] Run `uv run pytest tests/unit/test_eval_longitudinal_memory.py -n0 -v`.
- [ ] Complete both independent reviews, including a privacy reviewer who
  searches the committed dataset/diff for household content.
- [ ] Commit: `test(eval): add longitudinal memory suite contract`

## Task 3: Implement deterministic scoring and explicit capability states

**Files:** modify `scripts/eval_longitudinal_memory.py` and
`tests/unit/test_eval_longitudinal_memory.py`.

- [ ] Write failing tests proving a forbidden match fails even when required
  text is present; matching is case/Unicode normalized and reports the literal
  matched assertion.
- [ ] Write failing tests for `unsupported` preservation, provider/harness
  `error` separation, complete per-category denominators and p50/p95 over valid
  observations only.
- [ ] Write failing structured-extraction tests for exact canonical keys,
  micro-aggregated precision/recall, empty denominator as `None`, unexpected
  items and forbidden false memories.
- [ ] Write failing metric tests for candidate precision/recall by type,
  subject/object/relation precision/recall, current-truth accuracy after
  correction and correct-abstention rate, including unsupported/empty
  denominators and exact report rendering.
- [ ] Write failing tests for deletion: every named derivative must be inspected
  and absent; a missing inspection or one remaining derivative fails.
- [ ] Write failing provenance tests that distinguish subject, assertor and
  source from extraction subject/object; aggregate matched/expected fields and
  render mismatches.
- [ ] Write failing disclosure/deletion denominator tests: report eligible,
  expected, inspected and absent counts; return `None` with no valid
  denominator; never let an unsupported privacy/deletion step satisfy a binary
  gate.
- [ ] Write failing tests for exit codes `0`, `1`, and `2` exactly as frozen in
  this plan.
- [ ] Run RED:

  ```powershell
  uv run pytest tests/unit/test_eval_longitudinal_memory.py -k "score or aggregate or deletion or exit" -n0 -v
  ```

  Expected: missing scorer/aggregate behavior, never a real-provider error.
- [ ] Implement the minimum pure scoring functions. Do not use an LLM judge.
  Preserve every case in the denominator and reason field.
- [ ] Re-run the focused command and the full unit file; observe GREEN.
- [ ] Complete both independent reviews.
- [ ] Commit: `feat(eval): score longitudinal capability outcomes`

## Task 4: Add the safe runner, reproducibility report and command

**Files:** modify `scripts/eval_longitudinal_memory.py`,
`tests/unit/test_eval_longitudinal_memory.py`, and `justfile`; create
`docs/evals/README.md`; modify `docs/runbooks/operator-manual.md`.

- [ ] Write failing tests for metadata completeness, deterministic dataset hash,
  secret-free Ollama URL, sanitized argv with literal reserved values absent,
  pre-run dirty state and report table for all nine categories.
- [ ] Write failing tests that reject an existing output file, a path outside
  `docs/evals/`, a production/data database path, a provider other than Ollama,
  invalid `--only` IDs and incomplete category execution during a full run.
- [ ] Write failing database-sandbox tests proving original settings are
  restored and the temporary DB/WAL/SHM are removed on success, migration
  failure, driver failure and `close_db()` failure; a pre-open global
  connection is rejected; no production DB file is opened or changed.
- [ ] Write failing tests for provider preflight failure and mid-run failure;
  both return `2`, write no partial baseline report and close resources.
- [ ] Write a typed fake `LongitudinalDriver` test showing supported observations
  are executed and unsupported current seams are recorded, never synthesized.
- [ ] Run RED:

  ```powershell
  uv run pytest tests/unit/test_eval_longitudinal_memory.py -k "metadata or report or cli or driver" -n0 -v
  ```

  Expected: missing runner/report/CLI contracts.
- [ ] Implement an explicit current-runtime driver. It may call only audited
  existing seams. For an operation with no public safe seam, return
  `UNSUPPORTED` plus the missing symbol/capability; do not access `_buffers`,
  `_conn`, raw sqlite-vec tables or preloaded contexts to imitate it.
- [ ] For the initial baseline, `EXTRACT` delegates to the repaired real
  consolidation evaluator with the run-owned HTTP client. `PROPOSE`, true
  process `RESTART`, authorized longitudinal `RECALL`, `CORRECT`, `FORGET` and
  `INSPECT_DERIVATIVES` return `UNSUPPORTED` with the exact missing capability.
  Do not relabel legacy `assert_fact()` writes as candidates or a DB reconnect
  as a process restart. Later CM plans may extend the driver through separately
  reviewed runtime seams.
- [ ] `--only` is smoke/debug mode and must mark the report non-gating. A full
  baseline requires every version-1 case and `--runs 3`.
- [ ] Add exactly:

  ```just
  eval-longitudinal *ARGS:
      uv run --env-file .env python scripts/eval_longitudinal_memory.py {{ARGS}}
  ```

- [ ] Document preflight, exit codes, safe output paths, non-overwrite behavior,
  expected RED and temporary database cleanup in both evaluation README and
  operator manual.
- [ ] Re-run the focused command, the entire longitudinal unit file, and the two
  repaired evaluator test files; observe GREEN.
- [ ] Run `just lint` and `just typecheck` before review.
- [ ] Complete both independent reviews.
- [ ] Commit: `feat(eval): add reproducible longitudinal runner`

## Task 5: Record the real CM-0 baseline

**Owner:** orchestrator plus Pipec for local-service consent/checkpoints. No
coding agent may substitute generated results.

- [ ] Verify the worktree is clean, record `git rev-parse HEAD`, confirm no
  production DB path is configured, and obtain Pipec's go-ahead to use local
  Ollama compute.
- [ ] Run provider preflight with the repository command:

  ```powershell
  just services
  ```

- [ ] Run one non-gating smoke case to a temporary ignored output, then remove
  that temporary artifact after review:

  ```powershell
  just eval-longitudinal --only corrected_preference --runs 1 --output docs/evals/0046-smoke.md
  ```

  Expected: exit `1` for a valid cognitive RED or `0` only if that isolated
  case truly passes; exit `2` stops the task for debugging. Confirm the report
  says `non-gating` and the production database hash/timestamp is unchanged.
- [ ] Delete only the explicitly resolved smoke report after verifying its path
  is `docs/evals/0046-smoke.md`. Do not use recursive or wildcard deletion.
- [ ] Reconfirm a clean tracked tree, then run the frozen full suite:

  ```powershell
  just eval-longitudinal --runs 3 --output docs/evals/0046-longitudinal-memory-baseline.md
  ```

  Expected: exit `1`, a complete report, no harness errors, all nine categories
  present, and absent capabilities marked `unsupported`/`fail`. Exit `0` is not
  rejected, but requires independent inspection proving it was not produced by
  injected context or simulated lifecycle. Exit `2` is not a baseline.
- [ ] Verify SHA/dataset hash/models/settings/command/case tables/latencies are
  present, no private names or secrets occur, and the temporary DB was removed.
- [ ] Compare the production DB file metadata/hash captured before and after;
  any change invalidates the run and triggers systematic debugging.
- [ ] Have an independent evaluation reviewer inspect the report against raw
  command output and the frozen gates.
- [ ] Commit: `docs(eval): record longitudinal memory red baseline`

## Task 6: Run full gates, independent review and close CM-0

**Files:** only closure documentation listed in the file map and this plan's
move from `open/` to `completed/`.

- [ ] Run fresh full verification with the current canonical gate, then the
  documentation hook/diff checks:

  ```powershell
  just gate
  just check
  git diff --check
  ```

- [ ] Record exact commands, counts, duration, SHA and failures/warnings. A
  successful older run is not evidence for the current tree.
- [ ] Run a placeholder/hygiene search:

  ```powershell
  rg -n "TODO|TBD|FIXME|PLACEHOLDER|similar test|as above" scripts/eval_longitudinal_memory.py tests/unit/test_eval_longitudinal_memory.py tests/evals/golden_longitudinal_memory.yaml docs/evals
  ```

  Expected: no unresolved implementation placeholder. Legitimate quoted test
  fixtures must be explained in the closure notes.
- [ ] Run `git status --short`, inspect every changed file, and prove no file
  outside the permitted scope changed.
- [ ] Dispatch one fresh whole-branch reviewer for spec compliance, quality,
  privacy, result attribution and scope. Resolve every high/medium finding and
  rerun affected gates.
- [ ] Update canonical docs: CM-0 becomes complete; the baseline remains
  cognitive RED; no CM-1+ capability becomes implemented; Plan 0015 remains
  open. Re-audit Plan 0047's queued assumptions and report whether it is ready
  for its separate backend-selection review; do not nominate CM-1 before
  PC-3/PC-4.
- [ ] Move this file to
  `docs/plans/completed/0046-reproducible-longitudinal-memory-baseline.md` and
  update both plan indexes in the same commit.
- [ ] Use `superpowers:finishing-a-development-branch` to present merge/PR/keep
  options. Do not merge, push or delete a worktree without Pipec's explicit
  choice.
- [ ] Commit: `docs(plan): close reproducible longitudinal baseline`

## Rollback boundary

The evaluator repairs and new benchmark are outside runtime. Each task is an
independent conventional commit and can be reverted in reverse order. The
baseline report is evidence and may be reverted only together with the closure
claims that cite it. No rollback touches production memory because this plan
never writes it. If a supposedly temporary run touched production data, stop,
preserve forensic metadata, report the incident and do not claim rollback has
restored unknowable prior contents.

## Non-goals

- implement CM-1 capabilities or authorization;
- propagate `active_person` into legacy conversation;
- create/promote memory candidates or write V4 facts/relations;
- add episode privacy columns, retrieval filters or relevance thresholds;
- implement correction, forgetting or vector cleanup;
- improve prompts/models to make the baseline greener;
- change existing historical evaluation datasets or reinterpret their results;
- add cloud providers, new databases, agent frameworks or model dependencies;
- execute real microphone/server/robot acceptance; that belongs to CM-7/PC-5.

## Completion criteria

Plan 0046 closes only when all are true:

- both legacy evaluator entrypoints use the current shared-client contract and
  signature-aware tests prevent regression;
- the committed version-1 suite covers all nine categories with synthetic data
  and passes strict semantic/privacy validation;
- deterministic scoring, complete denominators and exit codes are GREEN;
- the runner cannot mutate the production DB, overwrite reports, use cloud or
  hide unsupported work;
- a clean-SHA, three-run Ollama baseline exists with exit `1` or a rigorously
  reviewed genuine `0`, never `2`;
- full gates and both per-task/final independent reviews pass on the final SHA;
- docs say exactly what became available: a benchmark and baseline, not
  longitudinal memory;
- the plan is moved to `completed/` with evidence and the next plan remains
  unimplemented until separately reviewed and authorized.
