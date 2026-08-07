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

Plan 0001 is complete. The only current ready plan is:

- [`0002-active-person-context.md`](0002-active-person-context.md)

Its approved [design](0002-active-person-context-design.md) records the
identity and privacy decisions. Its companion
[execution runbook](0002-active-person-context-execution.md) adds TDD and
temporary worker mechanics without changing the canonical plan's scope or
authority. P0.3 and later plans remain Draft until Plan 0002 is completed and
their assumptions are revalidated against the then-current tree.

The [P0 cognitive portfolio design](p0-cognitive-plan-portfolio-design.md)
links every current P0 plan and records their dependency order and status.
