# Conversational-memory delivery map

**Status:** canonical design; CM-0 has Plan 0046 `Ready`
**Last reviewed:** 2026-09-07

## Objective

Connect the vision of longitudinal autobiographical memory with the code, the
tests, and the observed gaps, without opening a second memory system or
confusing documentation with implementation.

This map expands P2.2 of the
[cognitive roadmap](cognitive-roadmap.md) and is a dependency of PC-5 in
[Plan 0015](../plans/open/0015-personal-companion-design.md). It is not an
executable plan: each increment needs its own `Ready` plan and runs one at a
time.

## Desired outcome

```text
conversation or perception
          ↓
memory candidate
          ↓
attribution, classification, and policy
     ┌────┼─────────┐
  accept  confirm  reject
     ↓
canonical V4 memory
     ↓
authorized retrieval
     ↓
response with evidence
     ↓
correction, history, or complete forgetting
```

Remembering more text is not the goal. Every durable memory must be able to
explain whose it is, who asserted it, what its source was, when it was valid,
what its truth state is, who may see it, whether it is sensitive, what it
corrects, and what must be removed when it is forgotten.

## Current fracture

The repository contains valuable pieces, but protected household queries and
generic conversation travel different paths:

```text
protected household query
  -> identity -> authorization -> V4 memory -> deterministic response

generic conversation
  -> legacy text_turn -> legacy/semantic memory -> LLM
```

Evidence current at the time this map was written:

- `cognition/controller.py` invokes the legacy turn with the message and the
  conversation, without carrying the resolved actor;
- `text_turn.py` enables persistent legacy memory only with `MANUAL` evidence;
  face and local unlock do not by themselves enable that access;
- `memory/consolidation.py` writes episodes and facts through the legacy APIs,
  not through literal facts or V4 relations;
- `memory/semantic.py` retrieves by file, optional type, and distance, with no
  prior filters by person, visibility, sensitivity, or authorization, and no
  minimum relevance threshold.

The current manual barrier accidentally contains part of the risk, but it is
not a sufficient policy for a conversational personal memory.

## Reusable capabilities

What already exists must not be rebuilt:

- identity separated from authorization;
- unknown as a valid state;
- policy and audit evaluator;
- V4 facts and relations with state and validity;
- authorized household reads;
- working memory bounded by identity and session;
- local extraction through Ollama;
- episodic storage and SQLite/sqlite-vec vector search;
- isolation tests that prevent legacy memory when the currently required
  evidence is missing.

## Delivery sequence

This table governs only the CM-0…CM-7 subprogram. Its position among
biometrics, personal acceptance, perception, RAG, family, and P4.2 is defined
once in the
[canonical pre-electronics delivery portfolio](cognitive-roadmap.md#canonical-pre-electronics-delivery-portfolio).

| Stage | Verifiable outcome | Dependencies | Executable plan |
|---|---|---|---|
| CM-0 | Versioned longitudinal benchmark and one reproducible RED run | evaluation specification | [Plan 0046](../plans/open/0046-reproducible-longitudinal-memory-baseline.md) — `Ready`, not started |
| CM-1 | Explicit `read`, `propose`, `confirm`, `correct`, and `forget` capabilities for personal memory | current policy and identity | not written |
| CM-2 | The authorized actor reaches the conversational flow without interpolating names or expanding permissions implicitly | CM-1 | not written |
| CM-3 | Extraction creates candidates; confirmation/promotion writes canonical V4 facts and relations | CM-0, CM-1, CM-2 | not written |
| CM-4 | Episodes declare owner, visibility, sensitivity, consent, and retention | CM-3 | not written |
| CM-5 | Retrieval filters authorization and validity before the prompt and applies a relevance threshold | CM-4 | not written |
| CM-6 | Correction and forgetting reach facts, relations, episodes, embeddings, summaries, and derived caches | CM-3 through CM-5 | not written |
| CM-7 | A real scenario learns, restarts, recalls, corrects, forgets, and does not disclose | CM-0 through CM-6, PC-3, PC-4 | not written |

The product order is therefore:

```text
CM-0 RED benchmark (can run first; does not change runtime)
  -> PC-3 speaker
  -> PC-4 multimodal fusion
  -> CM-1..CM-7 / P2.2 longitudinal
  -> PC-5 integrated personal acceptance
  -> continue in P2.1 per the canonical pre-electronics portfolio
```

Plan 0046 realizes CM-0. The numbering of CM-1 through CM-7 is not reserved:
each stage will be written only after its predecessor is closed and re-audited.
The R2/R3 documentation stages and the P3.1/P3.2 family work are not part of
this memory subsequence; they appear in the master portfolio and must not be
inserted as implicit CM plans.

## Contracts that must become explicit

### Lifecycle

`proposed -> confirmed|rejected -> corrected|revoked|expired`, with history and
provenance. Automatic extraction never on its own equals confirmed personal
truth.

### Authorization

The minimum capabilities are:

- `read_personal_conversation_memory`;
- `propose_personal_memory`;
- `confirm_personal_memory`;
- `correct_personal_memory`;
- `forget_personal_memory`.

Face, voice, PIN, or manual resolution provides evidence; policy decides each
capability and its scope.

### Retrieval

Person, visibility, sensitivity, consent, state, and validity are filtered
before any evidence reaches the LLM. Semantic similarity only ranks candidates
that are already authorized and sufficiently relevant.

### Forgetting

Forgetting must reach the canonical record and all its projections: embeddings,
summaries, caches, and retrieval material. Security logs that must be retained
will keep only the minimum permitted evidence and not the forgotten content.

## Out of scope

- own neural training, JAX, or online weight learning;
- DuckDB, microservices, or agent frameworks;
- automatically expanding current tokens or permissions;
- copying whole conversations as durable truth;
- implementing `care` or `education`;
- using the cloud in the runtime path.

## Criteria for opening plans

The first plan is Plan 0046 for CM-0 and must observe a reproducible failure
before changing the runtime. Every later plan must have small scope, RED/GREEN
tests, verification commands, non-goals, and independent review. PC-5 stays open
until CM-7 and its complete physical acceptance are passed.
