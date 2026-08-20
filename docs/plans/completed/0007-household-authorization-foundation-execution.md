# Plan 0007 — Household authorization foundation execution runbook

## Status

**Complete — merged to `main` as `960f160` through PR #42 on 2026-08-12.**
This runbook executed only [Plan 0007](0007-household-authorization-foundation.md).
It is an operational TDD aid; the canonical plan and architecture documents
remain authoritative.

## Preconditions

- Start from a clean feature branch based on `main` at or after `3b01b58`.
- Re-read the canonical plan and every required source file before editing.
- Do not run the new role CLI against a household database. Tests use temporary
  SQLite paths only.
- Record actual RED and GREEN outputs. Do not treat existing documentation as
  runtime proof.

## Execution checklist

### 1. Contracts and pure policy

1. Add failing tests first in `tests/unit/test_household_authorization_policy.py`
   and extend `test_cognitive_models.py` only for the approved contract delta.
2. Run the focused command and capture the missing/failed behavior.
3. Implement immutable request/category/action values and the pure policy
   evaluator in the permitted cognition files.
4. Re-run focused tests until green; run Ruff and type checking for touched
   modules.

Required cases: owner normal own data; adult explicit protected result;
child/guest/unknown protected denial; ambiguous identity denial; revoked/missing
consent denial; confirmation without access; missing rule denial; no I/O or LLM
call from policy construction/evaluation.

### 2. SQLite and local operator boundary

1. Add RED migration/repository tests using a temporary database.
2. Register only migration 5 and create its additive SQL.
3. Implement role/audit repositories and the local command.
4. Re-run the schema/runtime suite GREEN.

Required cases: non-person target rejected; matching confirmation required;
second active owner refused; revocation retains history; audit rows contain only
safe structured fields; `PRAGMA foreign_key_check` is clean; existing v3/v4
fixtures still pass.

### 3. Controller enforcement

1. Add RED fakes to the controller tests for evaluation ordering and audit
   capture.
2. Wire the injected collaborators with a public unknown actor in `/chat`.
3. Run focused controller/chat tests GREEN.

Required cases: protected unknown request calls policy/audit before and never
calls legacy; confirmation-required is equally non-disclosing; allowed internal
result remains `unknown`; generic unknown text keeps the legacy path; `/chat`
response keys are unchanged.

### 4. Review and gates

Run, in this order when focused tests are green:

```powershell
just lint
just typecheck
just test
just audit
just check
git diff --check
git status -sb
```

Review the final diff against Plan 0007's permitted file list. Confirm no
changed route grants roles, no prompt/log/audit contains protected data, no v4
repository reaches runtime, and no environment/dependency/audio/robot change
was introduced. Request review, push, and merge only under the repository's
normal PR/green-CI workflow.

## Completion record

- **RED:** the initial pure-policy suite exposed that `general_conversation`
  was evaluated after identity resolution, so unknown/ambiguous public turns
  were denied, and it later demonstrated that the generic action could carry
  protected categories. The schema suite also failed at collection while
  `assign_household_role` was absent.
- **GREEN:** the final focused command covered 94 tests across cognition
  contracts, active-person resolution, controller, policy, role/audit schema,
  authorization runtime, and `/chat`. It passed on 2026-08-12.
- **Quality gates:** `just lint`, `just typecheck`, `just test` (546 passed),
  `just audit`, and `just check` passed. `scripts/manage_household_roles.py
  --help` passed without opening or mutating a household database.
- **GitHub CI and merge:** title, quality/security, automated tests, and CodeQL
  passed. PR #42 was squash-merged as `960f160`.
- **Temporary database:** migration 5 applied after migrations 1–4; foreign
  keys were clean and legacy v3 facts/v4 rows were preserved.
- **Not verified:** real household bootstrap, real models, hardware, webcam,
  microphone, LAN exposure, biometric enrollment, and cloud are intentionally
  outside this runbook.
- **Next prerequisite:** P0.5-B must be a separately reviewed plan for
  policy-gated v4 reads and deterministic family tools. It cannot reuse a
  decision or pass denied data into legacy context generation.
