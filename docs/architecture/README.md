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
8. The one task plan explicitly named by the user under `docs/plans/`.

Code and tests outrank a stale statement about current behavior. An accepted
decision is not silently changed by implementation; replace it with a new ADR.

## Required reading by task

| Task | Read completely |
|---|---|
| Any cognitive implementation | `implementation-guardrails.md`, this index, the named plan, every document that plan lists |
| Domain models/controller | ADR-0004, ADR-0005, `cognitive-contracts.md`, `cognitive-architecture.md` |
| Identity or permissions | `identity-and-access.md`, ADR-0004, ADR-0006, ADR-0008, `cognitive-contracts.md` |
| P0-S hardening | `p0-s-hardening-audit.md`, `identity-and-access.md`, the named P0-S plan |
| Memory or onboarding | `memory-and-world-state.md`, `rag-and-memory-retrieval.md`, `identity-and-access.md` |
| RAG, embeddings, documents, or retrieval | `rag-and-memory-retrieval.md`, `memory-and-world-state.md`, `identity-and-access.md`, current-state baseline |
| Personality or prompts | `personality-and-interaction.md`, `identity-and-access.md` |
| Sensors, vision, or world state | `memory-and-world-state.md`, `cognitive-contracts.md`, media contracts in `implementation-guardrails.md` |
| Prioritization | `current-state.md`, `../roadmap/cognitive-roadmap.md` |

Do not scan the whole repository when a ready plan supplies narrower required
reading and permitted paths. If evidence contradicts a plan, stop and report the
specific conflict instead of redesigning the project implicitly.

## Canonical documents

- [`current-state.md`](current-state.md): verified implementation snapshot and
  known gaps.
- [`p0-s-hardening-audit.md`](p0-s-hardening-audit.md): targeted disposition of
  immediate security/configuration hardening before P0.3.
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
- [`../plans/0024-owner-authenticated-memory-mvp-design.md`](../plans/0024-owner-authenticated-memory-mvp-design.md):
  current product-spine design for the first authenticated personal-memory
  proof. Its executable, still-unimplemented sequence is
  [0025](../plans/0025-personal-owner-bootstrap-and-pin-setup.md) →
  [0026](../plans/0026-one-use-owner-authenticated-classic-turn.md) →
  [0027](../plans/0027-one-use-owner-streaming-parity.md) →
  [0028](../plans/0028-owner-authenticated-memory-runtime-acceptance.md).
- [`memory-and-world-state.md`](memory-and-world-state.md): relational knowledge,
  memory lifecycle, onboarding, retrieval, and present-time state.
- [`rag-and-memory-retrieval.md`](rag-and-memory-retrieval.md): detailed target
  architecture for documentary RAG, embeddings, hybrid retrieval, evidence,
  evaluation, and its staged relationship to Iroko's memory system.
- [`personality-and-interaction.md`](personality-and-interaction.md): stable
  identity, adaptive style, relationship context, and prompt boundaries.
- [`cognitive-foundation-audit.md`](cognitive-foundation-audit.md): read-only
  readiness protocol before handing Plan 0001 to an implementation session.
- [`roadmap-cerebro-agnostico-pre-electronica.md`](roadmap-cerebro-agnostico-pre-electronica.md):
  historical pre-electronics execution record; the cognitive roadmap supersedes
  it for new cognitive priorities.

## Historical and local-only material

`docs/local/` contains valuable specifications, audits, prompts, bitácoras,
evaluations, and electronics research. It is intentionally ignored by Git. It
was consulted to build these canonical documents, but future tasks must not
depend on its presence and must not treat an older local proposal as current
authority.

In particular:

- `docs/local/BRAIN_SPEC_v3.md` describes the origin of the current SQLite
  memory but includes planned sensor/dashboard work that is not implemented.
- `docs/local/architecture/vision-y-arquitectura-iroko.md` is the broad product
  vision from 2026-07-21; this tracked set preserves its valid decisions and
  updates its cloud and cognitive-controller policy.
- local audits and bitácoras are evidence and history, not implicit
  implementation instructions.

No future plan may cite a local-only file as required reading.
