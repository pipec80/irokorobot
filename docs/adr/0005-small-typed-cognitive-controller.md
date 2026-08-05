# 0005 — Evolve a small typed cognitive controller

- **Status:** Accepted
- **Date:** 2026-08-03

## Context

The current `server.text_turn` module already orchestrates memory retrieval,
working history, onboarding, emotion, visual perception, LLM generation, and
turn recording. It is a useful starting point, but it does not explicitly
resolve the active person, enforce authorization before retrieval, execute
deterministic family tools, maintain a current world state, or represent
uncertainty as a domain result.

Robot software must eventually process events from audio, vision, sensors, and
system state. A large agent framework or several autonomous agents would add
hidden control flow, dependencies, latency, and debugging difficulty before the
project has demonstrated a need for them.

## Decision

Evolve the existing orchestration incrementally into one small, typed Python
`CognitiveController`. It receives a typed cognitive event and produces a typed
response plan. Its conceptual stages are:

1. accept and validate the event;
2. resolve the active person;
3. evaluate authorization;
4. determine required information;
5. execute deterministic tools;
6. retrieve permitted memory;
7. assemble current context and world state;
8. generate natural language when needed;
9. validate claims and outcome status;
10. propose, confirm, or reject memory changes.

These are sequential responsibilities inside one service, not independent
agents. Each stage uses a small interface and can be tested without models,
network, database, or hardware when appropriate.

The controller remains inside the generic server brain. HTTP, voice, web,
vision, simulator, and future hardware are adapters. The existing `/transcribe`
contract remains compatible while migration occurs.

An event bus, behavior tree, ROS2, or separate process may be introduced only
when measured concurrency, physical control, or reactive behavior requires it.
They are not prerequisites for the cognitive foundation.

## Alternatives considered

- **Keep adding logic directly to `text_turn.py`:** rejected because identity,
  policy, tools, and response validation would become one untestable god module.
- **Adopt LangChain, LlamaIndex, CrewAI, AutoGen, or a similar framework:**
  rejected because the required flow is small, product-specific, and must stay
  observable and local-first.
- **Use multiple autonomous agents:** rejected because the ten stages are a
  deterministic workflow, not separate actors with independent goals.
- **Introduce ROS2 now:** rejected because the current milestone is a brain
  running on the PC; ROS2 belongs at the later communication and physical-body
  boundary.

## Consequences

### Positive

- Control flow, data access, and failure handling remain explicit.
- Each stage can be implemented and verified in a small change.
- Models and hardware providers remain replaceable adapters.
- Deterministic calculations and authorization do not depend on LLM behavior.

### Negative

- The project owns a small amount of orchestration code.
- Existing `text_turn` callers need gradual migration and compatibility tests.
- Later real-time behavior may require a separate event or robotics runtime.

## Review

Revisit only after profiling shows that the single-process controller cannot
meet a concrete requirement, or when physical autonomy needs a robotics runtime
for concurrent sensors and actions. A framework is chosen from measured needs,
not anticipated complexity.
