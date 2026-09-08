# Canonical architecture index

This directory is the versioned source of truth for Iroko's cognitive
architecture. Future Codex tasks must use this index instead of inferring the
design from chat history or from ignored local documents.

## Authority order

When sources disagree, use this order:

1. Runtime `AGENTS.md` instructions, when present.
2. [`implementation-guardrails.md`](implementation-guardrails.md) for tracked
   repository rules, immutable HTTP/audio boundaries, and task discipline.
3. Accepted ADRs for architectural decisions.
4. [`current-state.md`](current-state.md) for what the code actually implements
   at its stated commit.
5. [`cognitive-architecture.md`](cognitive-architecture.md) for the target brain
   and its boundaries.
6. Specialized architecture documents for identity/access, memory/world state,
   personality, and typed contracts.
7. [`../roadmap/cognitive-roadmap.md`](../roadmap/cognitive-roadmap.md) for order,
   dependencies, and completion outcomes.
8. [`../roadmap/personal-companion-delivery-map.md`](../roadmap/personal-companion-delivery-map.md)
   for cross-plan code/test/gap traceability.
9. [`../roadmap/conversational-memory-delivery-map.md`](../roadmap/conversational-memory-delivery-map.md)
   for the longitudinal-memory sequence and verified code seams.
10. The one task plan explicitly named by the user under
    `docs/plans/open/`.

Code and tests outrank a stale statement about current behavior. An accepted
decision is not silently changed by implementation; replace it with a new ADR.

## Required reading by task

| Task | Read completely |
|---|---|
| Any cognitive implementation | `implementation-guardrails.md`, this index, the named plan, every document that plan lists |
| Server/FastAPI hardening | `server-production-baseline.md`, `implementation-guardrails.md`, the named server-baseline child plan, and every ADR that child lists |
| Domain models/controller | ADR-0004, ADR-0005, `cognitive-contracts.md`, `cognitive-architecture.md` |
| Identity or permissions | `identity-and-access.md`, ADR-0004, ADR-0006, ADR-0008, ADR-0009, `cognitive-contracts.md` |
| Memory or onboarding | `memory-and-world-state.md`, `longitudinal-conversational-memory-evaluation.md`, `rag-and-memory-retrieval.md`, `identity-and-access.md`, `../roadmap/conversational-memory-delivery-map.md` |
| RAG, embeddings, documents, or retrieval | `rag-and-memory-retrieval.md`, `memory-and-world-state.md`, `identity-and-access.md`, current-state baseline |
| Personality or prompts | `personality-and-interaction.md`, `identity-and-access.md` |
| Sensors, vision, or world state | `memory-and-world-state.md`, `cognitive-contracts.md`, media contracts in `implementation-guardrails.md` |
| Prioritization | `current-state.md`, `../roadmap/cognitive-roadmap.md`, `../roadmap/personal-companion-delivery-map.md`, `../roadmap/conversational-memory-delivery-map.md` |

Do not scan the whole repository when a ready plan supplies narrower required
reading and permitted paths. If evidence contradicts a plan, stop and report the
specific conflict instead of redesigning the project implicitly.

## Canonical documents

- [`current-state.md`](current-state.md): verified implementation snapshot and
  known gaps.
- [`server-production-baseline.md`](server-production-baseline.md): audited
  target rules and execution portfolio for FastAPI, Starlette, Uvicorn,
  uploads, privacy, SQLite, lifecycle, and HTTP contracts. **Fully closed
  2026-09-03** — every 0031 child (0032–0045) is closed. A second
  independent audit on 2026-09-07 confirmed the baseline and closed four
  bounded follow-up edges via
  [Plan 0048](../plans/completed/0048-fastapi-baseline-final-hardening.md)
  (semantic `max_length`, the streaming one-terminal-event guarantee, the
  NDJSON 200 OpenAPI contract, `/health` wording + injectable `create_app`).
  Only Uvicorn concurrency calibration remains, deferred to its own
  `perf(...)` plan.
- [`../roadmap/personal-companion-delivery-map.md`](../roadmap/personal-companion-delivery-map.md):
  canonical mapping from the personal-companion outcome to existing code,
  tests, verified gaps, and the one accountable executable plan.
- [`../roadmap/conversational-memory-delivery-map.md`](../roadmap/conversational-memory-delivery-map.md):
  staged bridge from the current split memory paths to authorized,
  corrigible, forgettable longitudinal memory. **CM-0 closed 2026-09-08**
  ([Plan 0046](../plans/completed/0046-reproducible-longitudinal-memory-baseline.md)):
  the benchmark harness is GREEN and the measured baseline is a reproducible
  cognitive RED. CM-1…CM-7 remain unplanned; the next slice is PC-3A.
- [`p0-runtime-policy-audit.md`](p0-runtime-policy-audit.md): current
  disposition of remaining public-route and operator-acceptance gaps.
- [`implementation-guardrails.md`](implementation-guardrails.md): tracked
  repository boundaries and instructions for bounded Codex execution.
- [`cognitive-architecture.md`](cognitive-architecture.md): complete conceptual
  architecture and controller flow.
- [`cognitive-contracts.md`](cognitive-contracts.md): typed cross-layer domain
  contracts.
- [`identity-and-access.md`](identity-and-access.md): speaker/person resolution,
  roles, visibility, consent, and pre-retrieval authorization.
- [ADR 0009](../adr/0009-locked-posture-and-scoped-capabilities.md): defines
  what remains usable for an unknown speaker and why authentication never
  becomes a master permission for memory, home, computer, or physical actions.
- [`../plans/completed/0024-owner-authenticated-memory-mvp-design.md`](../plans/completed/0024-owner-authenticated-memory-mvp-design.md):
  current product-spine design for the first authenticated personal-memory
  proof. Its executable sequence is
  [0025](../plans/completed/0025-personal-owner-bootstrap-and-pin-setup.md) (merged) →
  [0026](../plans/completed/0026-one-use-owner-authenticated-classic-turn.md) (merged) →
  [0027](../plans/completed/0027-one-use-owner-streaming-parity.md) (merged) →
  [0028](../plans/completed/0028-owner-authenticated-memory-runtime-acceptance.md)
  (executed, PASS). PC-1 is complete.
- [`memory-and-world-state.md`](memory-and-world-state.md): relational knowledge,
  memory lifecycle, onboarding, retrieval, and present-time state.
- [`longitudinal-conversational-memory-evaluation.md`](longitudinal-conversational-memory-evaluation.md):
  canonical benchmark dimensions, evidence layers, the CM-0 measured baseline
  (`ac43c58`, 2026-09-08), and the longitudinal acceptance gate for PC-5.
- [`../evals/README.md`](../evals/README.md): rules for the offline evaluation
  reports (`scripts/eval_*.py`), and
  [`../evals/0046-longitudinal-memory-baseline.md`](../evals/0046-longitudinal-memory-baseline.md),
  the recorded CM-0 RED baseline.
- [`rag-and-memory-retrieval.md`](rag-and-memory-retrieval.md): detailed target
  architecture for documentary RAG, embeddings, hybrid retrieval, evidence,
  evaluation, and its staged relationship to Iroko's memory system.
- [`personality-and-interaction.md`](personality-and-interaction.md): stable
  identity, adaptive style, relationship context, and prompt boundaries.

## Historical boundary

Tracked superseded audits, roadmaps, and bootstrap notes live under the
[historical index](../history/README.md). Unversioned specifications, prompts,
bitácoras, evaluations, electronics research, and assistant runbooks are
preserved outside this documentation tree under ignored `project-history/`.

Neither location is operational authority. No active plan may require those
files; promote any still-valid decision into an ADR or canonical architecture
document first.
