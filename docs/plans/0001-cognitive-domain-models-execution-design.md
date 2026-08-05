# Cognitive domain models execution design

## Purpose

Provide an operational runbook for implementing canonical Plan 0001 without
changing that plan's architectural contract or expanding its permitted code
scope.

## Authority and scope

`docs/plans/0001-cognitive-domain-models.md` remains the canonical source for
objective, domain contracts, permitted implementation files, non-goals, and
completion criteria. The operational runbook will live under `docs/plans/` and
will add execution mechanics only:

- checkbox-tracked tasks;
- strict observed RED -> minimal GREEN -> refactor cycles;
- exact focused test commands and expected failures;
- a fresh worker/review boundary for each task; and
- final repository verification in the order required by Plan 0001.

No new domain decision, dependency, persistence change, route, provider,
hardware integration, cloud call, or production multi-agent runtime is
authorized by the runbook.

## Execution model

The runbook will require `superpowers:subagent-driven-development` for a fresh
worker per task and two-stage review. If that capability is unavailable, it
will allow `superpowers:executing-plans` as the sequential fallback. These are
development techniques only; they do not alter Iroko's production architecture.

Each worker owns only the files allocated to its task and must preserve prior
accepted work. No two workers may edit the same file concurrently. The primary
agent verifies each task, integrates only reviewed changes, and runs the final
gate.

## Task decomposition

The execution plan will define five serial tasks:

1. create the cognition package and prove it imports without prohibited
   dependencies;
2. implement status enums and immutable `Confidence` validation;
3. implement `AuthorizationDecision`, `Observation`, and `CognitiveEvent`;
4. implement `ActiveContext` and public package re-exports; and
5. complete regression checks, prove the no-I/O boundary, and mark canonical
   Plan 0001 complete only after every required command passes.

Every task will list exact file ownership, inputs/outputs, a focused failing
test, the expected RED reason, the minimum implementation, a focused GREEN
command, and a review checkpoint.

## Acceptance

The runbook is complete when it is self-contained, uses checkbox syntax for
every executable step, has no placeholders, preserves Plan 0001's exact code
scope, and provides a TDD path for every behavioral requirement in the
canonical plan.
