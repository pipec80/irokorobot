# Iroko documentation manual design

> **Status:** Approved design
>
> **Scope:** Documentation only. No application code, dependency, provider,
> hardware, API, or runtime-contract change is part of this design.

## Purpose

Make Iroko understandable and maintainable without prior chat context. A new
person must be able to understand the product, run the implemented local
development experience on a PC, find the applicable architecture and plan, and
contribute a bounded improvement safely.

Iroko is the product and cognitive brain. OMNiBot 2000 is a future experimental
physical embodiment, not the product name, a required deployment target, or an
operationally documented platform at this stage.

## Product position

Iroko is a local-first, typed, reusable household cognitive brain. It has a
public character profile, but its core architecture is not tied to that profile
or to a specific LLM, body, robot, cloud service, or hardware adapter.

The first public profile is Iroko: a warm, curious companion with retro
technology roots, a household-companion presence, and a careful explorer's
motivation. The profile uses neutral Spanish. Its story is product fiction; it
is never presented as a system memory, household fact, identity claim, or
authorization source.

Local providers such as Ollama or compatible implementations are the primary
development path. Cloud providers such as Anthropic or compatible
implementations remain interchangeable and subject to the canonical local-first
policy; the documentation must not imply hidden or automatic cloud fallback.

## Audience and first success

The immediate documented runtime target is a developer's PC on Windows, Linux,
or macOS. Raspberry Pi, homelab deployment, new electronics, and a physical
body remain future vision only. They receive no operational guide or support
promise in this documentation program.

The first success is a local voice conversation: a user speaks through the PC
microphone and receives Iroko's synthesized voice response. The local web chat
UI is a diagnostic and secondary path, not the primary welcome journey.

## Information architecture

```text
README.md / README.es.md
  Public welcome: product, short character story, principles, and navigation.

docs/README.md / docs/es/README.md
  Technical portal: start here, audience routes, current status, and next reads.

docs/guides/
  setup-development
  first-voice-conversation
  providers-and-local-first
  testing-and-quality
  troubleshooting
  contributing-and-pull-requests

docs/reference/
  configuration-and-environment
  public-contracts
  glossary

docs/product/
  iroko-profile

docs/architecture/
  Canonical architecture, current implementation, guardrails, and ADR routing.

docs/roadmap/
  Canonical priority and implementation order.

docs/plans/
  Bounded executable plans for Codex; not end-user or contributor tutorials.
```

The new portal and guides explain and link to canonical architecture. They do
not duplicate or override ADRs, contracts, current-state evidence, roadmap
priorities, or plans. Existing setup and tooling documents will be audited and
either retained as linked references or updated to avoid competing instructions.

## Reader routes

| Reader | Start | Completion outcome |
|---|---|---|
| Visitor | public README and Iroko profile | Understands the product, character, and safety boundaries. |
| New developer | technical portal, setup, first voice conversation | Runs the implemented PC development experience. |
| Contributor | contribution guide, quality guide, architecture, named plan | Can make a bounded change without breaking contracts. |
| Codex or architect | architecture index, current state, roadmap, named plan | Knows what is implemented, what is planned, and how to verify work. |
| Maintainer or releaser | quality, contribution, CI/versioning references, plan status | Can review, merge, version, and diagnose without inventing process. |

Every new guide declares its intended reader, status, prerequisites, verified
environment, and next reading.

## Language policy

English is the canonical source. Public and technical entry documents have a
Spanish equivalent under the agreed mirrored naming. A documentation PR either
updates both languages or explains why no translation is affected. Translation
must preserve technical meaning and status labels, not merely literal wording.

## Documentation truth and maintenance rules

1. Every behavior claim is labelled **Implemented**, **Planned**, or
   **Historical**.
2. Implemented claims link to code, a test, or `current-state.md`; planned
   claims link to the roadmap or a plan.
3. Historical material stays explicitly non-authoritative and cannot become a
   required dependency.
4. Commands state their supported operating system and verification context.
   No speculative command is represented as tested.
5. Examples contain no credentials. Configuration, sensitive permissions, and
   public contracts have one authoritative reference each.
6. A behavior, contract, configuration, plan, or status change updates the
   affected documentation in the same PR, or records why no update applies.
7. Hardware, biometrics, authorization, cloud escalation, and physical actions
   retain the limits in canonical architecture and ADRs.

## Delivery slices

### Slice 1: public and technical entry points

Create or revise the public README, Spanish translation, Iroko public profile,
and technical documentation portal. Establish reader routes and explicit links
to current state, architecture, roadmap, plans, setup, and tooling.

### Slice 2: reproducible developer manual

Create the cross-platform development setup, first voice-conversation,
provider-policy, testing/quality, troubleshooting, and contribution guides.
Use common `uv` and `just` commands with short Windows, Linux, and macOS
prerequisite sections rather than maintaining three duplicate manuals.

### Slice 3: reference, maintenance, and Spanish coverage

Create the configuration, public-contract, and glossary references. Complete
the Spanish mirrored entry and guide documentation, resolve duplicate legacy
instructions, and document the maintainer route.

Each slice is a documentation-only, independently reviewable PR. No slice may
claim support for future hardware or unimplemented cognitive phases.

## Verification

For each slice:

- verify every internal relative Markdown link and every linked repository file;
- run `git diff --check`;
- run the applicable documentation/pre-commit checks without rewriting
  unrelated files;
- inspect commands against the current repository commands and configuration;
- confirm that no secret, generated artifact, code, dependency, public API, or
  audio-contract change entered the diff;
- review English and Spanish status labels for semantic consistency.

## Program acceptance criterion

A person with a clean development PC and no project history can follow the
documented route to run the first voice conversation, find the relevant
contracts and current implementation state, choose the correct plan for an
improvement, and prepare a bounded contribution without relying on chat
history.

## Out of scope

- Implementing, simulating, or documenting an operational Raspberry Pi,
  homelab, OMNiBot 2000, ROS2, electronics, or physical-action workflow.
- Changing current provider defaults or introducing a provider dependency.
- Changing Iroko's runtime prompt, voice implementation, memory, identity,
  authorization, API, or audio behavior.
- Turning the character story into an autonomous-agent, persistent-memory, or
  household-data feature.
