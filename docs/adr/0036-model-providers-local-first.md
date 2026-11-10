# 0036 — Model providers: local by default, a cloud provider only as an explicit opt-in

- **Status:** Proposed (2026-11-10, written from Pipec's stated intent; the open questions below
  are for his later decision; nothing in the code changes)
- **Date:** 2026-11-10
- **Builds on:** [ADR 0004](0004-local-first-cognitive-policy.md),
  [ADR 0016](0016-face-and-voice-identity-fusion.md),
  [ADR 0019](0019-personal-memory-capabilities.md),
  [ADR 0029](0029-it-knows-who-is-listening.md),
  [ADR 0031](0031-the-memory-engine-boundary.md)
- **Amends:** the escalation clause of ADR 0004 (cloud as an optional escalation under five
  conditions), by direction. **ADR 0004 stays Accepted until this ADR is accepted.**
- **Delivers:** no roadmap slice. It is the decision behind P4.1, reframed as *Model-provider
  evaluation*, and behind the unplanned row *Offline run*.

## Context

Pipec's intent, in his words and in this order:

1. The cloud is **not excluded and not denied**. It was never considered inside an optimization
   plan; the rule «no cloud provider in the runtime path» of `AGENTS.md` grew out of the
   quarantine of August 2026 (Plan 0002a), not out of a decision against it.
2. The **default and the first goal stay local self-hosting** (Ollama). A pending check is to run
   the whole pipeline with the internet switched off, to prove that it is local.
3. His laptop cannot run large models or a good speech synthesis. Later he wants to compare
   (a) the current local model, (b) a second local model and (c) a cloud option (for example
   Claude), to see how each deploys **without saturating the laptop**. The only cost he expects
   from the cloud option is network latency.

What holds today (verified in the code on 2026-11-10): Ollama is the only language and vision
runtime; the model name, the host and the timeouts are settings; the cloud provider code is
quarantined (Plan 0002a) and not reachable. The language model is chosen in settings, not at one
composition point, which is what the open questions below ask about.

## Decision (proposed)

### 1. Local by default

Every capability runs locally unless a decision says otherwise. Ollama is the runtime of record
and the first goal. This does not change.

### 2. A cloud provider is an explicit opt-in, never an escalation by accident

A cloud provider may enter the runtime path only after this ADR is accepted, and only as a
**provider chosen at composition**, in one place, for a named capability. It is not a fallback
that appears when the local model fails, and it is not a setting that someone can flip by
mistake: a configuration error must never send a household's data out of the house.

### 3. The comparison comes first

Before any cloud provider enters the path, the project measures the three options of Pipec's intent on
the same benchmark: the current local model, a second local model and a cloud option. The
measures are the quality of the answers on the project's own cases, the latency and the load on
the laptop. The result is a recorded evaluation (roadmap P4.1), not a decision by itself.

### 4. What leaves the house is a policy question

The default is that **nothing identifying leaves the house**. The data classes of the
[levels and audiences table](../architecture/identity-and-access.md#levels-and-audiences) bound
it: the firewall's `sensitive` and `security` levels presumably never leave, and the raw
biometric data, the household database and the complete conversations do not leave (ADR 0004,
which stays valid on this point). Which classes may leave, if any, is an open question.

## Not decided here (open questions for Pipec)

| # | Question | Notes |
|---|---|---|
| 1 | Which data classes may ever leave the house | The `sensitive` and `security` levels presumably never; `normal` and `private` are open; a prompt with the profile card or recalled memories carries such data |
| 2 | Consent | Per capability, per session or once; who gives it (the owner alone), and what the robot says before it sends |
| 3 | Cost | A budget per day or month, and what happens when it is exhausted |
| 4 | Offline fallback | When the network fails, whether the robot falls back to a local model or says it cannot answer; ADR 0004's states `unknown` and `unauthorized` apply |
| 5 | How the provider is chosen | One composition point for the language model, not a stray setting; today the model is a setting |
| 6 | What a provider is | Language model only, or also speech to text, speech synthesis and vision; the speech and the face stay local until decided |
| 7 | Audit | What is recorded about each outgoing request (provider, model, data classes, size), without the content |
| 8 | Hugging Face and other model downloads | A download at install time is not a runtime call; the *Offline run* row checks that nothing is fetched at runtime |

## Alternatives considered

- **Keep ADR 0004 as it is.** Possible, and the default if this ADR is not accepted: cloud stays
  a five-condition escalation that no plan builds.
- **Forbid the cloud for good.** Rejected as an absolute rule by Pipec's intent: a second look at
  a hosted model is a legitimate evaluation, and the laptop cannot run the largest models.
- **Cloud first, local fallback.** Rejected for the same reasons as in ADR 0004: the normal path
  would depend on the network and on a provider.

## Consequences

### Positive

- The documents say what Pipec means: local first, the cloud neither excluded nor assumed.
- The comparison on the laptop becomes a named, measurable evaluation (P4.1).
- ADR 0004's protections of the household data stay in force until a decision replaces them.

### Negative

- Until this ADR is accepted, no cloud provider may enter the runtime path; the rule is a
  prohibition with a door, not an open choice.
- The open questions need Pipec's time before any evaluation touches real data.

## Docs to update

`AGENTS.md` and `CLAUDE.md` (the «Never Do» line), the roadmap (P4.1, the *Offline run* row),
`current-state.md`, `cognitive-architecture.md`, `cognitive-contracts.md`,
`implementation-guardrails.md`, `identity-and-access.md` (matrix row), ADR 0004 (a note). Done in
the documentation change that adds this ADR; they say «local by default; a cloud provider only
through ADR 0036».

## Review

Revisit when Pipec decides the questions above, when the model-provider evaluation (P4.1) has
numbers, or when the laptop is replaced by a server board.
