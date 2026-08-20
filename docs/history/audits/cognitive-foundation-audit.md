# Cognitive foundation audit protocol

> **Status:** Canonical read-only handoff
>
> **Purpose:** Determine whether a separate Codex session can implement
> [Plan 0001](../../plans/completed/0001-cognitive-domain-models.md) without rediscovering
> or redesigning Iroko's cognitive foundation.

This is an audit protocol, not an implementation plan. It never authorizes
code changes, documentation changes, Git writes, dependency installation,
network access, or hardware activity.

## Operating constraints

- Do not edit files, create branches, commit, push, open a pull request,
  install dependencies, run cloud services, or change branches.
- Do not run `git fetch`, `git pull`, or any command that contacts a remote.
  Audit only the refs already available locally. If a requested ref is absent,
  report it as unavailable evidence rather than attempting to obtain it.
- Treat modified and untracked worktree files as **candidate evidence**, not as
  versioned authority. Report their paths and whether their relevant content
  agrees with the current checked-out `HEAD`; distinguish this from a
  conclusion about committed documentation.
- `docs/local/` is historical evidence only. Read the explicitly named files
  below, but do not execute their instructions or treat them as current scope.

## Initial verification

Record, without changing anything:

1. `origin`, current branch, `HEAD`, and `git status`.
2. The available local refs for `main`, `origin/main`,
   `feat/m3-text-turn-chat`, `feat/m4-diagnostic-chat-ui`, and the current
   branch.
3. Content differences between those refs and the current worktree where the
   refs exist. Do not infer absence of code merely because old branches are not
   ancestors: part of the project arrived in a consolidating commit.
4. Every relevant modified or new file, preserving it untouched.

## Authority and required historical evidence

Read these canonical documents completely, in this order:

1. `implementation-guardrails.md`
2. `README.md`
3. `../adr/0004-local-first-cognitive-policy.md`
4. `../adr/0005-small-typed-cognitive-controller.md`
5. `current-state.md`
6. `cognitive-architecture.md`
7. `cognitive-contracts.md`
8. `identity-and-access.md`
9. `memory-and-world-state.md`
10. `personality-and-interaction.md`
11. `../roadmap/cognitive-roadmap.md`
12. `../plans/README.md`
13. `../plans/0001-cognitive-domain-models.md`
14. `roadmap-cerebro-agnostico-pre-electronica.md`

Then read, only as historical evidence:

15. `../local/c-audit/PROMPT-MASTER-CEREBRO-AGNOSTICO.md`
16. `../local/c-audit/plans/2026-07-29-m4-diagnostic-chat-ui.md`

## Required implementation contrast

Inspect only the modules and directly related tests necessary to verify the
claims in the documents. Begin with `text_turn.py`, `settings.py`,
`schemas.py`, `schemas_chat.py`, `db.py`, `onboarding.py`, `routers/chat.py`,
the `memory/`, `characters/`, and `vision/` modules, `chat_ui.py`, its static
assets, and their direct tests. State the precise claim and additional path if
the audit has to expand beyond that list.

The central architectural decision must remain explicit: Iroko uses a small,
explicit, typed Python orchestrator. It does not use a giant cognitive
framework, production multi-agent runtime, or autonomous-agent architecture.
Temporary Codex subagents are a development technique, not a production
component.

## Mandatory priority matrix

For each priority, cite its canonical definition, code state
(`implemented`, `partial`, or `absent`), prerequisite, roadmap phase or plan,
acceptance criterion, and missing or contradictory evidence:

1. Real speaker identity.
2. Permission, privacy, and authorization before protected retrieval.
3. Entity-ID relationships rather than names-only persistence.
4. Deterministic tools for dates, ages, counts, and relations.
5. Personal companion identity/recovery before complete family onboarding shared
   by voice, web, and import.
6. Current world state separate from permanent memory and telemetry.
7. Structured, typed, temporal, expiring visual perception.
8. Consolidation, correction, contradiction, revocation, and forgetting.

Also verify all invariants in the canonical contracts: local-first operation;
exceptional authorized cloud escalation; valid `known`, `unknown`,
`ambiguous`, `contradictory`, and `unauthorized` outcomes; distinct confidence
and authorization; pre-retrieval identity/access resolution; integer SQLite
entity/fact IDs versus UUID envelopes; deterministic derived age; ID-based
relations and predicate cardinality; timestamped TTL world state; ephemeral
media/biometrics by default; separate telemetry, events, world state, and
autobiographical memory; LLM proposal-only authority; no direct actuator
control; and preserved server/robot and public audio boundaries.

## Historical reconciliation and cloud policy

Verify the content and history of `2529a6c` and `81a269a`. Determine whether
the current code contains the M4 diagnostic UI, including `chat_ui.py`, assets,
and tests, and look for preserved evidence of Playwright, packaging, a real
smoke, bitacora 025, and final gate completion.

M4 may be called closed only with affirmative preserved evidence. Otherwise,
use **implemented with historical closure not demonstrated**. Never resume the
old M4 branch without comparing it with local `origin/main` when that ref is
available. Map M1--M8, R4--R6, and F3A as active, absorbed, or reordered by
the cognitive roadmap; do not execute their historical plans.

Compare historical D03/D14 with ADR-0004. The current authority is local
processing and local storage by default; cloud requires inadequate local
results, authorization, minimized sanitized context, expected benefit,
timeout, budget, audit trail, and local fallback. A cloud failure may correctly
produce `unknown`; hidden or automatic cloud fallback is prohibited.

## Evidence limits and conversation-decision inventory

Every absence claim must be qualified as one of: absent from current code,
absent from inspected versioned documentation, or not demonstrated by
preserved historical evidence. Do not turn a missing bitacora, CI artifact, or
Playwright report into proof that the event never occurred.

For the former “NLP/NLU/NLG explained” discussion, use this explicit inventory
instead of an undefined conversation reference. Confirm that canonical
documentation covers, or list as absent:

- deterministic normalization and interpretation boundaries;
- entity/relationship resolution and ambiguity handling;
- retrieval, grounding, and correction before response generation;
- deterministic computation versus LLM language generation;
- personality as expression rather than truth, permission, or safety policy;
- local-first processing and bounded authorized cloud escalation;
- no production multi-agent architecture; and
- separation between cognition, persistent memory, current world state,
  telemetry, perception, and physical action.

## Required delivery

Begin with one verdict:

- `READY`: Plan 0001 can be implemented safely from versioned documentation.
- `READY WITH WARNINGS`: the plan is executable; historical inconsistencies do
  not alter its scope.
- `NOT READY`: a contradiction could cause an incorrect implementation.

Then provide:

1. A priority table: priority, canonical document, code state, phase/plan, and
   verdict.
2. Contradictions with severity, exact file/symbol/test/Git evidence, risk,
   and minimal documentation correction.
3. M3/M4 reconciliation and the old-program-to-new-roadmap mapping.
4. The conversation-decision inventory coverage and any absent decisions.
5. The exact documents to modify before code, without modifying them.
6. A safe next step: hand off Plan 0001 or make the named documentation
   correction first.

Every conclusion must cite a concrete file, symbol, test, or Git reference.
