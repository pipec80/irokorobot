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

Plans 0002b, 0002c, 0003, the Plan 0004 design, and Plan 0005 are complete.
Plan 0005 merged as `3b01b58` through PR #40 after its final 527-test gate.
Its companion [execution runbook](0005-relational-memory-v4-execution.md)
freezes the exact file scope, migration version, dry-run-first local command,
and boundary that keeps v4 out of the runtime until authorization exists.

[Plan 0007](0007-household-authorization-foundation.md) and its
[execution runbook](0007-household-authorization-foundation-execution.md) are
the complete P0.5-A implementation: deterministic fail-closed policy, local
role bootstrap/audit, and controller enforcement. Its local gates and GitHub
CI passed; PR #42 merged to `main` as `960f160` on 2026-08-12.
They do not authorize P0.5-B v4 runtime retrieval or family tools; that
follow-up is designed in
[Plan 0008](0008-policy-gated-v4-household-tools-design.md). Its P0.5-B1
[Plan 0009](0009-policy-gated-v4-reader.md) is complete: PR #45 merged as
`a7550d0` on 2026-08-13 after local gates (555 tests) and green GitHub CI. It
adds only the policy-gated v4 reader and target-ID query filter. P0.5-B2
family tools are now specified in [Plan 0010](0010-policy-gated-v4-family-tools.md)
and are Ready after its 2026-08-14 revalidation. The evidence-only
[Plan 0011](0011-p0-closure-and-acceptance.md) remains Draft until B2 merges.

The [P0 cognitive portfolio design](p0-cognitive-plan-portfolio-design.md)
links every current P0 plan and records their dependency order and status.
The [P0-S hardening design](p0-s-hardening-design.md) explains why the current
P0-S plans are split before P0.3.
