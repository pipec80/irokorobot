# Implementation plans

This directory contains small, executable plans derived from accepted ADRs and
architecture contracts. A plan limits the work so an implementation task does
not need to rediscover or redesign the entire repository.

Start with the [canonical architecture index](../architecture/README.md). The
[cognitive roadmap](../roadmap/cognitive-roadmap.md) defines order and exit
gates; it is not permission to implement a whole phase.

## How to use a plan

Give Codex the plan path and ask it to implement exactly that plan. For example:

```text
Implement docs/plans/0001-cognitive-domain-models.md exactly as written.
Read only the required inputs and permitted implementation files listed there.
Stop if a contract change or an out-of-scope file is required.
```

Every plan must define:

- objective and architectural source of truth;
- required reading and permitted file scope;
- deliverables and invariants;
- explicit non-goals;
- tests and verification commands;
- exact completion criteria.

A completed plan remains as implementation history. Contract changes are made
in architecture documents or ADRs, not hidden inside code tasks.

## Plan readiness

Only plans marked `Ready` are executable. Write the next detailed plan just in
time, after the preceding plan's checks and exit gate pass. This keeps file
scopes and assumptions anchored to the code that actually exists.

No plan may require chat history or a file under ignored `docs/local/`. If a
historical insight is still required, first promote it into a tracked ADR or
canonical architecture document.

Plans 0001, 0002, and 0002a are complete. Plan 0002's approved
[design](0002-active-person-context-design.md) records the identity and privacy
decisions, and its [execution runbook](0002-active-person-context-execution.md)
records the observed TDD, final-gate, and final-remediation evidence. The last
remediation commit is `79258cc`; its combined P0.2 suite passed 174 tests and
the full repository suite passed 497 tests.

Plans 0002b, 0002c, 0003, and the Plan 0004 design are complete. Plan 0005 is
Ready for only the additive v4 storage/migration foundation; P0.5 and later
plans remain Draft. Its companion
[execution runbook](0005-relational-memory-v4-execution.md) freezes the exact
file scope, migration version, dry-run-first local command, and boundary that
keeps v4 out of the runtime until authorization exists. Before any promotion,
re-read the completed prerequisite
implementation and revise the candidate plan with its exact current file scope
and tests.

The [P0 cognitive portfolio design](p0-cognitive-plan-portfolio-design.md)
links every current P0 plan and records their dependency order and status.
The [P0-S hardening design](p0-s-hardening-design.md) explains why the current
P0-S plans are split before P0.3.
