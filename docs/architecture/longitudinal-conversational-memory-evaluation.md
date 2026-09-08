# Longitudinal conversational-memory evaluation

**Status:** canonical specification; CM-0 benchmark and first RED baseline
delivered by Plan 0046 (closed 2026-09-08)
**Last reviewed:** 2026-09-08

## Purpose

Define how to demonstrate that Iroko learns, keeps, updates, protects, and
removes autobiographical memories across multiple sessions. This specification
evaluates a complete experience; it does not turn an extraction test or a green
`pytest` into product acceptance.

Longitudinal memory is part of PC-5 acceptance. The corresponding delivery map
is in
[conversational-memory-delivery-map.md](../roadmap/conversational-memory-delivery-map.md).
The first bounded implementation is
[Plan 0046](../plans/completed/0046-reproducible-longitudinal-memory-baseline.md):
it built the instrument and recorded RED, without fixing the runtime. Its
measured baseline is in [CM-0 measured baseline](#cm-0-measured-baseline) below.

## Unit under evaluation

A longitudinal run must be able to traverse, with the same authorized subject:

```text
learn
  -> restart the process
  -> recall
  -> correct
  -> restart again
  -> recall the current truth
  -> forget
  -> check absence and non-disclosure
```

Each case must record the person who is the subject of the memory, who asserted
it, the source, the relevant times, the truth state, the visibility, the
sensitivity, the policy decision, and the derivatives removed.

## Mandatory capabilities

| Category | Question the evaluation must answer |
|---|---|
| Extraction | Was the correct memory proposed without turning an inference into a fact? |
| Multi-session | Can it be retrieved after closing and recreating the session or the process? |
| Temporality | Does it distinguish when it happened, when it was asserted, and whether it still holds? |
| Update | Does a correction replace the active truth without erasing its provenance? |
| Abstention | Does it admit not knowing when there is no sufficient and current evidence? |
| Provenance | Can the response be linked to the correct subject, assertor, and source? |
| Cross-person privacy | Is an unauthorized identity excluded before the prompt is built? |
| Complete deletion | Does forgetting remove or invalidate derived facts, episodes, embeddings, summaries, and caches? |
| False-memory resistance | Does it reject spurious negations, misattributions, and unconfirmed contradictions? |

## Evidence layers

Acceptance requires three layers, each with a different responsibility:

1. **Deterministic tests:** contracts, lifecycle, cardinality, authorization,
   filtering, and deletion.
2. **Local Ollama evaluations:** extraction and verbalization over versioned
   sets, with model and parameters recorded.
3. **Real scenario:** `just run-server` and `just run-robot`, using the audio
   contract and the available identity, with real restarts between sessions.

Unit or integration tests do not replace the third layer. A manual test does
not replace the deterministic privacy and deletion invariants.

## Minimum sets

The future suite must include at least:

- simple, correctable preferences;
- ages, domiciles, and relations with temporal validity;
- family and pet relations, including deceptive negations;
- private data for two distinct adults;
- `recipient_only` messages with an authorized and an unauthorized recipient;
- unknown information to check abstention;
- sensitive episodes whose deletion has vector derivatives;
- perceptual evidence that must not on its own become durable truth.

Real family names and data must not be part of the versioned set. Synthetic
identities and content must be used.

## Metrics and results

Each run must produce, at a minimum:

- candidate precision and recall by type;
- subject, object, and relation precision and recall;
- current-truth accuracy after corrections;
- correct-abstention rate;
- forbidden-disclosure rate, whose acceptable threshold is zero;
- complete-derivative-deletion rate, whose acceptable threshold is 100%;
- p50 and p95 latencies;
- provider, exact model, quantization, parameters, SHA, diff, and service
  status.

Quality thresholds must not be encoded only in this document: Plan 0046 froze
them together with the versioned dataset and observed RED before any runtime
change (see below).

## CM-0 measured baseline

Plan 0046 (closed 2026-09-08) delivered the benchmark and its first reproducible
RED baseline. It changed no runtime memory code.

**Frozen dataset (version 1):** `tests/evals/golden_longitudinal_memory.yaml` —
nine synthetic scenarios covering all nine mandatory categories, the frozen
sequence `propose → restart → recall → correct → restart → recall current truth
→ forget → inspect derivatives → unauthorized recall`, two synthetic adults plus
unknown actors, and every minimum domain. No real names, paths, or secrets;
enforced by `validate_dataset_privacy`.

**Frozen gates (each requires a non-empty denominator; an empty one is `FAIL`):**

- forbidden-disclosure rate: exactly `0`;
- complete-derivative-deletion rate: exactly `1.0`;
- truth-current accuracy after correction: exactly `1.0`;
- provenance accuracy on scored fields: exactly `1.0`;
- unsupported categories are always visible and product-failing;
- provider/harness errors are never counted as cognitive failures or passes;
- extraction and abstention report precision/recall; CM-0 records them without
  inventing a release threshold.

**Baseline result** (`ac43c58`, `just eval-longitudinal --runs 3`, exit `1`,
report [`docs/evals/0046-longitudinal-memory-baseline.md`](../evals/0046-longitudinal-memory-baseline.md)):
single-turn extraction is the only live seam and is **measured, not passing** —
precision/recall `0.25` on the Spanish suite (`qwen2.5:3b` chat,
`qwen3:4b-instruct-2507-q4_K_M` consolidation), scored `FAIL`; there is no
extraction release gate in CM-0. Every other operation (`propose`, `restart`,
`recall`, `correct`, `forget`, `inspect_derivatives`) is honestly `unsupported`
with its exact missing seam. All four frozen gates `FAIL`. The production
database hash was unchanged before and after the run.

This is the current reproducible RED. CM-1…CM-7 will be measured against it and
must not relax a threshold or hide an unsupported category to move the number.

## Recovered historical baseline

The 2026-09-02 audit produced useful evidence, but **it is not a current
baseline or a reproducible acceptance**: it ran on a tree with local changes
and the conversational report was left at a temporary path. The CM-0 baseline
above supersedes it as the comparison point.

- extraction, 22 conversations, model
  `qwen3:4b-instruct-2507-q4_K_M`: global recall 0.69; precision 0.75; entity
  recall 0.89; mean latency 27.5 s; maximum 55.2 s; result below the historical
  threshold of 0.80;
- conversational faithfulness, 12 cases, model `qwen2.5:3b`: pass rate 58.33%;
  required recall 70.59%; forbidden violations 8.33%.

Losses of `hijo_de`, `mascota_de`, and `pareja_de` relations were observed,
along with false negations, a preference for stale information, and responses
that failed to abstain. These results justify the benchmark, but they must be
repeated on a frozen SHA before being used as a comparison.

## PC-5 longitudinal gate

PC-5 cannot be accepted until a reproducible run demonstrates:

1. learning as a candidate and authorized promotion;
2. recall after restart with provenance;
3. correction and exclusive retrieval of the current truth;
4. forgetting with verifiable deletion or invalidation of all derivatives;
5. non-disclosure to another person or to an unknown interlocutor;
6. a complete conversation over the real server/robot path.

The LLM response is presentation of evidence. The decision about which memory is
current, authorized, or deleted must remain deterministic.

## Run evidence

Each future report must be a versionable artifact, or linked from the plan, and
must include:

- date, branch, SHA, and `git status`;
- exact commands and results;
- effective models and Ollama availability;
- dataset and version;
- a per-case table, not just averages;
- false positives, disclosures, and residue after forgetting;
- limitations and any manual intervention.

A temporary report, a result without a reproducible SHA, or a run over a
mutable tree is kept as research, not as a closed gate.
