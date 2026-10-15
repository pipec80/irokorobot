# Conversational-memory delivery map

**Status:** canonical design; CM-0 closed (Plan 0046, 2026-09-08); CM-1's grant scoping closed
(Plan 0051, 2026-10-06) and its memory capabilities closed as policy only (Plan 0060, 2026-10-09);
CM-2 closed (Plan 0061, 2026-10-13: short-term continuity for the identified person); CM-3 designed
in [ADR 0021](../adr/0021-memory-candidates-and-the-canonical-writer.md) (`Proposed`, 2026-10-14) and split into CM-3a and CM-3b;
CM-3a corte 1 closed (Plan 0062, 2026-10-15: candidate store, canonical writer without a route caller, background proposal),
corte 2 (Plan 0063: offer, answer, hardware acceptance) next
**Last reviewed:** 2026-10-15

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
- `memory/consolidation.py` wrote episodes and facts through the legacy APIs,
  not through literal facts or V4 relations. *Since Plan 0062 (CM-3a corte 1,
  2026-10-15) `consolidate_turn`, `PROPOSE_MEMORY` and `COMMIT_MEMORY` are gone;*
  the module keeps only the extraction seam the benchmark and `just eval-memory`
  call;
- `memory/semantic.py` retrieves by file, optional type, and distance, with no
  prior filters by person, visibility, sensitivity, or authorization, and no
  minimum relevance threshold.
- the production conversational routes never emit `MANUAL` evidence:
  `IdentitySessionRegistry.select_person` has test callers only, and only the
  tests and the offline `scripts/eval_chat.py` build that evidence directly
  (verified 2026-09-30). Reusable history and vector retrieval are
  therefore off for every speaker, the face-identified owner included (the
  legacy consolidation write has since been retired, see below);
  "¿te acuerdas de…?" does not work for anyone yet. *Since Plan 0061 (CM-2,
  2026-10-13) the previous turn is no longer lost:* the identified person's
  last exchanges reach the next turn for 180 s of silence and 3000 characters,
  in process only, so "estoy arreglando una bicicleta" followed by "¿qué
  herramienta necesito?" reaches the LLM with the first sentence. Persistent
  history and retrieval stay off;
- only the children list and count are connected: every other authorized
  household question answers that the information "todavía no está conectada",
  and no controller branch confirms, corrects or forgets a memory;
- channels differ: no voice route passes a consolidation scheduler any more
  (Plan 0062). A face-identified generic classic or streaming voice turn
  schedules a background candidate proposal (default-off
  `MEMORY_CANDIDATES_ENABLED`) that also needs the voice of the same person on
  the turn's own clip; `memory_writer.promote` is the only place a candidate
  becomes a V4 literal fact and no route calls it yet. `/chat` has no audio, so
  it cannot create or confirm a candidate, and fixing one channel does not fix
  the others.

The current conversational route neither persists nor retrieves memories. That
blocks this disclosure path, but it does not yet prove that secrets are protected
once memory is enabled, nor that the database holds no earlier content, nor that
every output is confidential (for example, the opt-in console transcript of Plan
0052 is independent of memory). The barrier is a limitation, not a policy.
Connecting the actor (CM-2) does not lift it: `memory/context.py::build_context`
receives no actor or authorization, so each legacy read stays blocked until the
slice that implements its guarantees (CM-4 episodes, CM-5 retrieval); the legacy
write path was retired by Plan 0062 and the new write path only proposes
candidates until Plan 0063 wires the answer.

## Reusable capabilities

What already exists must not be rebuilt:

- identity separated from authorization;
- unknown as a valid state;
- policy and audit evaluator;
- V4 facts and relations with state and validity;
- authorized household reads;
- short-term continuity of the identified person (`memory/continuity.py`, Plan 0061):
  one in-process session slot bounded by characters and silence, suspended for an
  unknown or ambiguous speaker;
- local extraction through Ollama;
- the candidate store (`memory_candidates`, migration 009) and the canonical writer
  (`memory_writer.promote`, Plan 0062): a seam proven with doubles that no route
  calls yet;
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
| CM-1 | Every grant bound to one named operation (ADR-0015 decision 1, Plan 0051), then explicit `read`, `propose`, `confirm`, `correct`, and `forget` capabilities for personal memory | current policy and identity; PC-4 (closed) | [Plan 0051](../plans/completed/0051-scoped-owner-grants.md) **closed 2026-10-06**; the memory capabilities are [Plan 0060](../plans/completed/0060-cm1-personal-memory-capabilities.md) (closed 2026-10-09; policy only, nothing wired; [ADR 0019](../adr/0019-personal-memory-capabilities.md) `Accepted`) |
| CM-2 | The authorized actor and its grants reach the conversational flow without interpolating names or expanding permissions implicitly; short-term continuity (in-process working memory for the identified actor, deleted by another identified person or 180 s of silence, suspended on an `unknown` or `ambiguous` turn, per [ADR 0020](../adr/0020-authorized-actor-in-the-conversation.md) `Accepted`) has its own acceptance test; durable legacy paths stay blocked. Identifying generic turns supersedes part of ADR-0016 §5 | CM-1 | [ADR 0020](../adr/0020-authorized-actor-in-the-conversation.md) `Accepted`; [Plan 0061](../plans/completed/0061-cm2-generic-turn-continuity.md) — **closed 2026-10-13**, accepted on real hardware ([record](../evals/0061-generic-turn-continuity-acceptance.md)) |
| CM-3a | Extraction creates candidates; one writer assigns the classification and promotes to canonical V4 facts. First cut: the owner's own `likes`, `dislikes` and `prefers`, by voice, where every candidate, spoken value and promotion requires face and voice of the same person on that turn; it closes none of the benchmark's write steps ("CM-3" without a letter names CM-3a and CM-3b). The seed load ("step 0") follows as its second input channel | CM-0, CM-1, CM-2; Plan 0050 | [ADR 0021](../adr/0021-memory-candidates-and-the-canonical-writer.md) `Proposed` (`Accepted` when Plan 0063 closes); corte 1 [Plan 0062](../plans/completed/0062-cm3a-memory-candidates-and-writer.md) — **closed 2026-10-15** (PR #183; no spoken dialogue, no hardware; gate 2972); corte 2 Plan 0063 (the offer, the answer and the hardware acceptance) not written, `NOW` empty |
| CM-3b | The rest of the personal-scope write steps CM-7 needs: third-party relations, `lives_in` with validity, facts reported by another person, a disclosure rule, perceptual candidates, the first `SECURITY` datum and a benchmark `confirm` step (each tied to its owner in ADR 0021 decision 13) | CM-3a | not written; **required before CM-7** |
| CM-4 | Episodes declare owner, visibility, sensitivity, consent, and retention | CM-3a | not written |
| CM-5 | Retrieval filters authorization and validity before the prompt and applies a relevance threshold | CM-4 | not written |
| CM-6 | Correction and forgetting reach facts, relations, episodes, embeddings, summaries, and derived caches | CM-3a through CM-5, and CM-3b for the dataset's write steps | not written |
| CM-7 | A real scenario learns, restarts, recalls, corrects, forgets, and does not disclose; the benchmark is GREEN on its personal-scope scenarios, and the family-scope ones (`recipient_only_message`, `two_adult_private_facts`) stay reported as pending for P3.2 | CM-0 through CM-6 (including CM-3b), PC-3, PC-4 | not written |

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
The CM-1…CM-7 plan numbers are not reserved (Plan 0051, the first plan of CM-1, is
closed); each stage is written only after its predecessor closes and is
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
