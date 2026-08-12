# Plan 0007 — Household authorization foundation execution runbook

## Status

**Ready.** This runbook executes only
[Plan 0007](0007-household-authorization-foundation.md). It is an operational
TDD aid; the canonical plan and architecture documents remain authoritative.

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

## Completion record template

Record in the canonical plan only after success:

- actual RED command and failure;
- actual focused GREEN counts;
- final gate commands/results;
- migration version and temporary-database evidence;
- PR and merge commit;
- what was not run (real household bootstrap, real models, hardware, LAN);
- remaining P0.5-B prerequisite: policy-gated v4 reads/family tools, written
  only after a fresh review.
