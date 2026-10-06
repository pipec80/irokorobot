# Conversational-memory delivery map

**Status:** canonical design; CM-0 closed (Plan 0046, 2026-09-08); CM-1 unplanned
**Last reviewed:** 2026-09-30

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
- the production conversational routes never emit `MANUAL` evidence:
  `IdentitySessionRegistry.select_person` has test callers only, and only the
  tests and the offline `scripts/eval_chat.py` build that evidence directly
  (verified 2026-09-30). Reusable history, vector retrieval and consolidation are
  therefore off for every speaker, the face-identified owner included;
  "¿te acuerdas de…?" does not work for anyone yet. Even the previous turn is
  lost: without `MANUAL` evidence `text_turn.py` prepares `history=None` and
  clears the working memory after each reply, so "estoy arreglando una
  bicicleta" followed by "¿qué herramienta necesito?" reaches the LLM without
  the first sentence;
- only the children list and count are connected: every other authorized
  household question answers that the information "todavía no está conectada",
  and no controller branch confirms, corrects or forgets a memory;
- channels differ: classic and streaming voice pass a consolidation scheduler,
  `/chat` does not, so fixing one channel does not fix the others.

The current conversational route neither persists nor retrieves memories. That
blocks this disclosure path, but it does not yet prove that secrets are protected
once memory is enabled, nor that the database holds no earlier content, nor that
every output is confidential (for example, the opt-in console transcript of Plan
0052 is independent of memory). The barrier is a limitation, not a policy.
Connecting the actor (CM-2) does not lift it: `memory/context.py::build_context`
receives no actor or authorization and the legacy consolidation stores the full
turn text, so each legacy read or write stays blocked until the slice that
implements its guarantees (CM-3 writes, CM-4 episodes, CM-5 retrieval).

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
| CM-0 | Versioned longitudinal benchmark and one reproducible RED run | evaluation specification | [Plan 0046](../plans/completed/0046-reproducible-longitudinal-memory-baseline.md) — **closed 2026-09-08**: benchmark GREEN, measured baseline RED (`ac43c58`, exit 1) |
| CM-1 | Every grant bound to one named operation (ADR-0015 decision 1, Plan 0051), then explicit `read`, `propose`, `confirm`, `correct`, and `forget` capabilities for personal memory | current policy and identity; PC-4 (closed) | [Plan 0051](../plans/completed/0051-scoped-owner-grants.md) **closed 2026-10-06**; the memory capabilities are not written |
| CM-2 | The authorized actor and its grants reach the conversational flow without interpolating names or expanding permissions implicitly; short-term continuity (in-process working memory for the identified actor, cleared on a change of speaker) has its own acceptance test; durable legacy paths stay blocked. Identifying generic turns supersedes ADR-0016 §5 and needs a new ADR | CM-1 | not written |
| CM-3 | Extraction creates candidates; one writer assigns the classification and promotes to canonical V4 facts and relations. The seed load ("step 0") follows as its second input channel | CM-0, CM-1, CM-2; Plan 0050 | not written |
| CM-4 | Episodes declare owner, visibility, sensitivity, consent, and retention | CM-3 | not written |
| CM-5 | Retrieval filters authorization and validity before the prompt and applies a relevance threshold | CM-4 | not written |
| CM-6 | Correction and forgetting reach facts, relations, episodes, embeddings, summaries, and derived caches | CM-3 through CM-5 | not written |
| CM-7 | A real scenario learns, restarts, recalls, corrects, forgets, and does not disclose; the benchmark is GREEN on its personal-scope scenarios, and the family-scope ones (`recipient_only_message`, `two_adult_private_facts`) stay reported as pending for P3.2 | CM-0 through CM-6, PC-3, PC-4 | not written |

The single cross-track order, including the hardening rows (Plans 0055 and
0050) and the seed load, lives only in the
[canonical portfolio](cognitive-roadmap.md#canonical-pre-electronics-delivery-portfolio).
CM is not a separate program: it is the memory half of the personal companion,
and PC-5 cannot close without CM-7. Its only biometric dependency, PC-4, closed
on 2026-09-30, and its hardening follow-up, Plan 0055, merged on 2026-10-01
(PR #152); Plan 0050 (audit repairs) closed on 2026-10-01, ahead of CM-1.

The documentary-retrieval stages of
[RAG §25](../architecture/rag-and-memory-retrieval.md#25-secuencia-de-evolución)
overlap this map: R1 is CM-5 and R5 is CM-3, CM-4 and CM-6. Only R2 and R3
(documents and hybrid search) are separate portfolio rows, after CM-5 and CM-6.
The CM-1…CM-7 plan numbers are not reserved, except Plan 0051 as the first plan
of CM-1; each stage is written only after its predecessor closes and is
re-audited.

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

Plan 0046 for CM-0 is closed: it observed a reproducible failure (`ac43c58`,
exit 1) without changing the runtime. Every later plan must have small scope,
RED/GREEN tests, verification commands, non-goals, and independent review. PC-5
stays open until CM-7 and its complete physical acceptance are passed.
