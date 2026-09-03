# Deterministic CI Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:test-driven-development` and
> `superpowers:verification-before-completion`.

**Goal:** Make every PR run the deterministic API/local integration evidence
that already passes locally, with at least 80% coverage.

**Architecture:** Test markers describe resources, not directory names. CI
excludes only tests requiring slow models, real hardware, or model-quality
evaluation.

**Tech Stack:** pytest, pytest-xdist, pytest-cov, Ruff, MyPy, Pyright, uv,
GitHub Actions.

**Spec:**
[`server-production-baseline.md`](../../architecture/server-production-baseline.md)

## Permitted files

- `pyproject.toml`
- `.github/workflows/ci.yml`
- Test marker declarations on existing tests only when classification is
  factually wrong
- New CI-contract tests only if needed

No production code, mass test-directory move, coverage omission, or relaxed
type/security configuration is allowed.

## Verified starting evidence

At commit `7d68641`, `pytest -m "not slow"` passes 920 tests with 88.39%
combined coverage. The current CI selection excludes `integration` and sets
`--cov-fail-under=0`.

## Task 1: Lock marker semantics

- [x] Define markers for `unit`, `api`, `integration`, `slow`, `hardware`, and
  `eval` with resource-based descriptions.
- [x] Inventory all explicitly marked tests. Reclassify only cases whose real
  dependencies contradict the description; local temporary SQLite and ASGI
  tests stay in the deterministic gate.
- [x] Do not move files solely to satisfy taxonomy.

## Task 2: Prove the local target before editing CI

- [x] Run exactly:

  ```powershell
  uv lock --check
  uv run pytest -m "not slow and not hardware and not eval" --cov=server/src --cov=robot/src --cov-report=term-missing --cov-fail-under=80
  ```

- [x] Record test count and coverage in the plan execution evidence. Any drift
  below 80 blocks the CI edit until missing behavior tests—not omissions—close
  the gap.

## Task 3: Align CI with local commands

- [x] Add `uv lock --check` and use
  `uv sync --locked --all-packages --all-groups`.
- [x] Run Ruff check/format, MyPy, and Pyright. Prefer `just typecheck` if the
  workflow environment supports the same command without hiding output.
- [x] Replace the pytest selection with the proven deterministic command and
  remove the zero coverage override.
- [x] Retain vulture, deptry, Ruff security rules, and pip-audit.
- [x] Add `uv build --all-packages` only after verifying both workspace
  packages build from the committed lock.

## Task 4: Verify

- [x] Run every workflow command locally in workflow order.
- [x] Run `just check` and `git diff --check`.
- [x] Review the YAML for Windows/PowerShell compatibility and no network/model
  download during pytest.

## OpenAPI contract test

- [x] Add a cheap generated-contract test to the deterministic gate so `/docs`
  can never silently break:

  ```python
  def test_openapi_schema_is_valid() -> None:
      schema = app.openapi()
      assert schema["openapi"].startswith("3.")
      assert schema["paths"]
  ```

  It belongs in this plan rather than 0040 because it guards the gate itself;
  0040 then extends it with per-endpoint contract assertions.

## Rollback

Revert CI/marker changes together. Production runtime is unaffected.

## Completion criteria

- PR CI covers API and temporary-SQLite integration behavior.
- Coverage is at least 80 with no new omission workaround.
- MyPy and Pyright both run.
- Slow, hardware, and eval suites remain separately runnable.

## Execution notes

Executed 2026-09-03 on branch `feat/0037-deterministic-ci-baseline`.

### The real gap: CI was silently skipping a third of the suite with no coverage floor

Before this plan, CI ran `pytest -m "not integration and not slow"
--cov-fail-under=0` — excluding 353 of 997 tests (`integration`, minus the 9
already `slow`) from every PR, and enforcing no coverage floor at all on what
remained. `integration`'s own marker description
("requiere hardware real o APIs externas (Claude/Whisper)") was the
justification for the exclusion — but auditing all 39 files using the marker
found none matching that description: every one uses a temporary SQLite DB,
an ASGI `TestClient`, or a monkeypatched double. The tests that genuinely need
a real model (`tests/slow/test_stt_transcription.py`,
`test_tts_synthesis.py`) were already correctly isolated under `slow`, with a
fixture that skips if the model file isn't downloaded. The marker's
description was simply stale — it never matched the tests using it.

### Task 1 — no reclassification needed, only correct the description

Given that finding, Task 1 became narrower than expected: define `api`,
`hardware`, and `eval` as new resource-based markers (currently zero tests
need `hardware`/`eval` — reserved for future use, not a gap), correct
`integration`'s description to what it actually means today (local,
deterministic multi-component tests — never real hardware or external
network), and reclassify nothing. `--strict-markers` plus a `--collect-only`
sweep before and after confirms no test's marker usage broke.

### Task 2 — the 80% target was already exceeded locally

```
uv lock --check            # clean, no drift
uv run pytest -m "not slow and not hardware and not eval" \
  --cov=server/src --cov=robot/src --cov-report=term-missing --cov-fail-under=80
# 997 passed, 9 deselected, TOTAL coverage 90.19%
```

No missing-behavior tests were needed to close a gap — the aggregate target
was already exceeded by 10 points running the exact same tests that were
already passing locally, just previously hidden from CI's own gate.

### Task 3 — CI now runs what local already proves, plus the Pyright gap it was missing

`quality-gate` ran MyPy but never Pyright, even though `just typecheck` (the
documented local equivalent) runs both — a real, separate gap from the
pytest-selection one, closed by adding a `Type Check (Pyright)` step.
`uv lock --check` and `uv sync --locked` were added so CI fails loudly on lock
drift instead of silently re-resolving. `uv build --all-packages` runs after
local verification confirmed both workspace packages build from the committed
lock.

### OpenAPI contract test — cannot RED, added as a lock-down

`app.openapi()` already returns a valid `3.1.0` schema with 10 paths before
any change in this plan — FastAPI generates it from the app's existing
routes with no extra wiring needed. The new test cannot fail against current
code; it exists as a regression guard for the gate itself, the same category
as Plan 0035's `test_close_db_leaves_get_conn_raising` (locking down behavior
already known correct, not proving a fix).

### A transient `just check` failure, not a real one

One `just check` run failed `check-added-large-files` right after `uv build`
wrote fresh `dist/*.whl`/`*.tar.gz` files — `dist/` is gitignored (with its
own auto-generated `dist/.gitignore` containing `*`) and re-running the exact
same hook alone, and then the full `just check` again, both passed clean.
Recorded as noise, not a defect — no code or config explains a real failure
here, and it did not reproduce.

### Verification

- `uv lock --check`, `uv sync --locked --all-packages --all-groups` — clean
- `ruff check .`, `ruff format --check .` — clean
- `mypy` (90 files), `pyright` — 0 errors
- `vulture`, `deptry` (both packages), `ruff check --select S`, `pip-audit`
  — clean
- `uv build --all-packages` — both packages build from the committed lock
- `pytest -m "not slow and not hardware and not eval" --cov-fail-under=80` —
  **998 passed** (997 + the new OpenAPI contract test), 9 deselected,
  **90.15% coverage**
- `just check` — clean (after the one transient large-files false alarm)
- `git diff --check` — clean
- Real acceptance: not applicable — no `server/src` or `robot/src` file
  changed; this plan touches only CI configuration, pytest markers, and one
  new test. No voice-path or runtime behavior changes, matching Plan 0035's
  precedent for a config-only plan.
