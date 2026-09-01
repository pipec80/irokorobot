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

- [ ] Define markers for `unit`, `api`, `integration`, `slow`, `hardware`, and
  `eval` with resource-based descriptions.
- [ ] Inventory all explicitly marked tests. Reclassify only cases whose real
  dependencies contradict the description; local temporary SQLite and ASGI
  tests stay in the deterministic gate.
- [ ] Do not move files solely to satisfy taxonomy.

## Task 2: Prove the local target before editing CI

- [ ] Run exactly:

  ```powershell
  uv lock --check
  uv run pytest -m "not slow and not hardware and not eval" --cov=server/src --cov=robot/src --cov-report=term-missing --cov-fail-under=80
  ```

- [ ] Record test count and coverage in the plan execution evidence. Any drift
  below 80 blocks the CI edit until missing behavior tests—not omissions—close
  the gap.

## Task 3: Align CI with local commands

- [ ] Add `uv lock --check` and use
  `uv sync --locked --all-packages --all-groups`.
- [ ] Run Ruff check/format, MyPy, and Pyright. Prefer `just typecheck` if the
  workflow environment supports the same command without hiding output.
- [ ] Replace the pytest selection with the proven deterministic command and
  remove the zero coverage override.
- [ ] Retain vulture, deptry, Ruff security rules, and pip-audit.
- [ ] Add `uv build --all-packages` only after verifying both workspace
  packages build from the committed lock.

## Task 4: Verify

- [ ] Run every workflow command locally in workflow order.
- [ ] Run `just check` and `git diff --check`.
- [ ] Review the YAML for Windows/PowerShell compatibility and no network/model
  download during pytest.

## Rollback

Revert CI/marker changes together. Production runtime is unaffected.

## Completion criteria

- PR CI covers API and temporary-SQLite integration behavior.
- Coverage is at least 80 with no new omission workaround.
- MyPy and Pyright both run.
- Slow, hardware, and eval suites remain separately runnable.
