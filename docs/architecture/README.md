# Canonical architecture index

This directory is the versioned source of truth for Iroko's cognitive
architecture. Every future task, by an agent or an implementer, must use this index instead of inferring the
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
| Memory or onboarding | [`ADR 0031`](../adr/0031-the-memory-engine-boundary.md) (the engine's boundary), `memory-and-world-state.md`, `longitudinal-conversational-memory-evaluation.md`, `rag-and-memory-retrieval.md`, `identity-and-access.md`, `../roadmap/conversational-memory-delivery-map.md` |
| RAG, embeddings, documents, or retrieval | `rag-and-memory-retrieval.md`, [`ADR 0031`](../adr/0031-the-memory-engine-boundary.md), [`ADR 0028`](../adr/0028-recall-what-the-owner-told.md), `memory-and-world-state.md`, `identity-and-access.md`, current-state baseline |
| Personality or prompts | `personality-and-interaction.md`, `identity-and-access.md` |
| Sensors, vision, or world state | `memory-and-world-state.md`, `cognitive-contracts.md`, media contracts in `implementation-guardrails.md`, [`ADR 0035`](../adr/0035-deployment-worlds.md) (the body is an ESP32) |
| Model providers, a second model, or any cloud use | [`ADR 0004`](../adr/0004-local-first-cognitive-policy.md), [`ADR 0036`](../adr/0036-model-providers-local-first.md) (Proposed), `cognitive-architecture.md`, `identity-and-access.md` |
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
  Only Uvicorn concurrency calibration remains; since 2026-09-30 it is measured on the home server inside PC-5 (portfolio row 12), not in a separate `perf(...)` plan.
- [`seed-data-pool.md`](seed-data-pool.md): what the commissioning (Step 0) captures, where each
  datum lives, its sensitivity and the capability it will feed. *Canonical* since
  [ADR 0024](../adr/0024-seed-load-senses-secrets-and-channels.md) became `Accepted` (2026-10-27);
  the Step 0 seed load closed 2026-10-28 in Plans 0070 to 0073 (the data is loaded and amendable
  with `iroko-admin`; since Plans 0074 to 0080 the owner's tastes, recall, the relatives and the
  sensitive data are read back by voice, behind default-off switches).
- [`../roadmap/personal-companion-delivery-map.md`](../roadmap/personal-companion-delivery-map.md):
  canonical mapping from the personal-companion outcome to existing code,
  tests, verified gaps, and the one accountable executable plan.
- [`../roadmap/conversational-memory-delivery-map.md`](../roadmap/conversational-memory-delivery-map.md):
  staged bridge from the current split memory paths to authorized,
  corrigible, forgettable longitudinal memory. **CM-0 closed 2026-09-08**
  ([Plan 0046](../plans/completed/0046-reproducible-longitudinal-memory-baseline.md)):
  the benchmark harness is GREEN and the measured baseline is a reproducible
  cognitive RED. CM-1's grant scoping is closed
  ([Plan 0051](../plans/completed/0051-scoped-owner-grants.md)) and its memory
  capabilities are policy only ([Plan 0060](../plans/completed/0060-cm1-personal-memory-capabilities.md));
  CM-2 (short-term continuity for the identified person) closed 2026-10-13
  ([Plan 0061](../plans/completed/0061-cm2-generic-turn-continuity.md)); CM-3a closed
  2026-10-16: its first cut ([Plan 0062](../plans/completed/0062-cm3a-memory-candidates-and-writer.md),
  2026-10-15) lets a face-identified voice turn leave a stored memory candidate with one
  canonical writer, and [Plan 0063](../plans/completed/0063-cm3a-memory-dialogue.md) (closed
  2026-10-16, accepted on real hardware) adds the spoken offer and the explicit spoken answer
  that promote or reject it, all behind a default-off kill-switch
  ([ADR 0021](../adr/0021-memory-candidates-and-the-canonical-writer.md), `Accepted`
  2026-10-16); CM-3b tranche A closed with Plan 0065 (2026-10-22) and CM-4 with [Plan 0076](../plans/completed/0076-cm4-conversation-record-and-diary.md) (2026-10-30: the conversation record and the diary); the household protection answers requests, not mentions, with [Plan 0077](../plans/completed/0077-household-requests-not-mentions.md) (2026-11-02, step 1 of the closing path); CM-5a ([Plan 0074](../plans/completed/0074-cm5a-profile-card.md)), recall (CM-5b + R3, [Plan 0078](../plans/completed/0078-cm5b-recall-what-the-owner-told.md)), the owner's sensitive read by voice (block B, [Plan 0079](../plans/completed/0079-block-b-sensitive-read-and-spoken-secrets.md)) the MVP recall phrasings ([Plan 0080](../plans/completed/0080-mvp-recall-phrasings.md), 2026-11-10), what the robot says ([Plan 0081](../plans/completed/0081-what-the-robot-says.md), 2026-11-11), the whole alta by voice ([Plan 0082](../plans/completed/0082-the-whole-alta-by-voice.md), 2026-11-12) and when a told event happened with one reader of spoken time ([Plan 0083](../plans/completed/0083-spoken-time-and-when-it-happened.md), 2026-11-12) are closed; the pending topics (Plan 0084, ADR 0037 decision 2), block C (correct and forget, CM-6) and block D (CM-7 + PC-5) remain. PC-3A ([Plan 0047](../plans/completed/0047-speaker-evidence-calibration-study.md)) closed 2026-09-25 with a provisional PASS, and PC-3B ([Plan 0053](../plans/completed/0053-consented-speaker-runtime-evidence.md)) closed 2026-09-29 with default-off `VOICE` evidence; PC-4 ([Plan 0054](../plans/completed/0054-face-default-identity-fusion.md)) closed 2026-09-30, accepted on real hardware.
- [`p0-runtime-policy-audit.md`](p0-runtime-policy-audit.md): current
  disposition of remaining public-route and operator-acceptance gaps.
- [`implementation-guardrails.md`](implementation-guardrails.md): tracked
  repository boundaries and instructions for bounded agent execution.
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
- [ADR 0031](../adr/0031-the-memory-engine-boundary.md): the memory engine's boundary, the
  authority for what the engine owns and how a policy port guards every read and write.
- [ADR 0035](../adr/0035-deployment-worlds.md): the three deployment worlds (the ESP32 body, the
  server board, the remote dashboard) and [ADR 0036](../adr/0036-model-providers-local-first.md)
  (Proposed): local by default, a cloud provider only as an explicit opt-in.
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
