# Plan 0003 — Typed controller and deterministic tools design

## Status

Approved design for a future **Draft** implementation plan. Plan 0002 remains
the only `Ready` plan. This document authorizes neither production code nor
making Plan 0003 executable before P0.2 has completed and the source tree has
been revalidated.

## Purpose

P0.3 introduces the first narrow controller seam that turns a typed text event
into a typed response plan. It proves that calendar facts and age calculation
can be deterministic, inspectable, and local without replacing the existing
server architecture with a cognitive framework or agents.

The target is one small, explicit, typed Python `CognitiveController` inside
the generic server. It is not a production multi-agent system: temporary Codex
subagents may implement or review its runbook, but Iroko receives one
sequential service with visible control flow.

## Authority and dependencies

- [`0005-small-typed-cognitive-controller.md`](../adr/0005-small-typed-cognitive-controller.md)
  accepts incremental evolution toward one controller.
- [`cognitive-roadmap.md`](../roadmap/cognitive-roadmap.md) places P0.3 after
  P0.2 and before relational memory P0.4.
- [`cognitive-architecture.md`](../architecture/cognitive-architecture.md)
  requires deterministic tools for dates, counts, relations, and permission
  boundaries, while treating LLMs as language tools rather than decision
  engines.
- [`cognitive-contracts.md`](../architecture/cognitive-contracts.md) defines
  typed events, uncertainty, authorization separation, and the conceptual
  controller/response-plan boundary.
- [Plan 0002](0002-active-person-context.md) supplies the active-person
  boundary. P0.3 must consume its output rather than reimplement identity.
- [`p0-cognitive-plan-portfolio-design.md`](p0-cognitive-plan-portfolio-design.md)
  limits P0.3 to a controller seam plus date/age tools; relationships and
  protected retrieval wait for P0.4/P0.5.

## Approved design

### 1. Single `/chat` pilot

The first adapter to use the controller is existing `POST /chat`. Its request
and response JSON remain unchanged. The controller sits behind the chat router
and existing text-generation boundary; it does not alter the robot audio
contract, `/transcribe`, `/transcribe/stream`, or `/vision/respond`.

This is a pilot, not a new public API. After P0.2 completes, the canonical
Plan 0003 will re-check the actual text-turn interface and use an adapter that
maps the existing validated chat input into a typed cognitive text event.

### 2. Small controller boundary

The controller is an ordinary typed Python service with one public asynchronous
method conceptually equivalent to:

```python
async def handle(event: CognitiveEvent[TextTurnPayload]) -> ResponsePlan: ...
```

Its P0.3 sequence is deliberately short:

```text
validate typed text event
-> consume the P0.2 active-person outcome
-> classify only supported deterministic information needs
-> execute permitted pure local tool(s)
-> assemble bounded result evidence
-> produce ResponsePlan
-> delegate wording to existing local generation
-> validate that wording cannot turn uncertainty into certainty
```

It has no event bus, dynamic plugins, autonomous goal loop, separate agents,
provider discovery, cloud branch, direct database access, or hardware control.
It does not redo active-person fusion or authorization policy.

### 3. Typed response and tool results

P0.3 adds small immutable value objects, keeping `KnowledgeStatus` and
`Confidence` from Plan 0001 as the source vocabulary:

- `TextTurnPayload`: validated text and adapter-safe context only;
- `InformationNeed`: a closed P0.3 set for generic conversation, current date,
  and age from an explicit ISO `birth_date`;
- `ToolResult`: a named result with explicit `KnowledgeStatus`, a typed value
  or safe reason, and source/evidence references where applicable;
- `ResponsePlan`: bounded claims, tool results, open questions, knowledge
  status, and optional natural-language guidance. It contains no action
  request, raw memory dump, permission grant, or mutable global state.

The plan must be expressible and unit-testable without an LLM, network, SQLite,
web server, audio, or hardware.

### 4. Deterministic tools activated in P0.3

Only these tools execute real product logic:

| Tool | Input | Deterministic output | Boundary |
|---|---|---|---|
| `get_current_date` | optional injected clock/date | ISO date and local display-ready value | Does not ask an LLM for today's date. |
| `calculate_age` | strict ISO `birth_date`, explicit `on_date` | completed years and status | Handles leap-day and future-date cases explicitly; never persists a mutable age. |

The request classifier is intentionally conservative. It recognizes only
small, documented date/age forms and otherwise returns the generic conversation
path or an explicit `unknown`; it is not general NLU. Tests call tool and
controller contracts directly, so natural-language pattern coverage never
becomes the only evidence that calculations are correct.

### 5. Deferred tools return safe outcomes

The architectural names `get_children`, `count_relationships`,
`get_person_details`, `get_known_preferences`, `get_current_perception`, and
`remember_confirmed_fact` remain documented but are not active P0.3 tools.

- Relation/count/profile operations return a typed `unknown` when the P0.4
  entity-ID relation model is absent.
- Any operation requiring protected data returns `unauthorized` while P0.5
  deterministic policy is unavailable; identity confidence or manual selection
  cannot change that result.
- Current perception, memory write, and cloud escalation remain out of scope.

No controller path may use the current string-valued relation storage as a
shortcut to answer a family query. P0.4 must first establish entity-ID targets,
cardinality, temporal rules, provenance, and compatibility.

### 6. Generation and response validation

The controller provides bounded, typed facts/results to the existing local LLM
generation adapter. The LLM chooses Spanish wording and character style only.
It must not select tools, compute age, infer an active person, elevate
`unknown` to known, treat `unauthorized` as permission, create a fact, or
invoke an actuator.

A deterministic response-plan validator checks that every factual claim is
backed by a P0.3 tool result, and that `unknown` and `unauthorized` remain
explicit in the plan supplied to generation. Free-form generic conversation
may still use the existing local generator, but cannot be represented as a
verified tool fact.

## Questions and decisions log

This log records the questions intentionally resolved while designing P0.3 so a
future implementation session does not need chat history to understand the
scope.

| ID | Question | Alternatives considered | Decision | Why |
|---|---|---|---|---|
| D03-01 | Which existing channel pilots the controller? | Migrate all shared `text_turn`; pilot `/transcribe`; pilot `/chat`. | Pilot only `/chat`. | It proves the boundary while preserving public WAV, audio, streaming, robot, and vision behavior. This follows ADR-0005's incremental migration rule. |
| D03-02 | Should P0.3 introduce a framework, runtime, or agents? | LangChain/LlamaIndex-style framework; multi-agent runtime; one typed service. | One typed Python service. | The stages are deterministic responsibilities, not autonomous actors. Extra runtime hides control flow and violates ADR-0005. |
| D03-03 | Which tools may execute real logic now? | All household tools; date/age only; contracts only. | `get_current_date` and `calculate_age` only. | They are pure, local, independently testable, and need neither unresolved P0.4 relations nor P0.5 authorization. |
| D03-04 | Can legacy string relations answer family/count questions temporarily? | Reuse current facts; adapt them in the controller; return safe outcomes. | Return safe outcomes until P0.4. | Reusing name-valued relations would encode a migration shortcut that conflicts with integer entity links, cardinality, provenance, and authorization ordering. |
| D03-05 | Does an identified active person permit protected retrieval? | Treat as authorized; use confidence threshold; return `unauthorized` pending policy. | Return `unauthorized` pending P0.5. | Identity and authorization are separate. `conversation_id`, confidence, and manual selection are not permission grants. |
| D03-06 | How broad is NLU in the pilot? | General LLM intent routing; new broad NLP layer; closed deterministic routing. | Closed deterministic routing for date/ISO-age forms. | It keeps the first vertical slice observable and prevents the LLM from deciding what data/tool access it needs. |
| D03-07 | Who verifies facts and calculates values? | LLM; tool result plus validator; prompt instructions only. | Typed tool result plus deterministic validator. | The LLM may verbalize results but must not invent or recalculate dates, ages, counts, permissions, or relations. |
| D03-08 | Why is audio deferred rather than removed? | Change all channels; add an audio-specific controller; leave audio adapters unchanged. | Leave audio/vision/streaming unchanged in P0.3. | Their contracts are stable and P0.2 changes their identity boundary first. A later bounded migration can reuse the proven chat seam with current evidence. |

## Non-goals

- Implementing P0.2, P0.4, P0.5, P1, P2, or P3 work.
- Any SQL schema or migration, relational memory rewrite, fact lifecycle, world
  state, perception adapter, household onboarding, biometric behavior, or
  memory persistence change.
- Broad NLU, model-based routing, tool calling by an LLM, framework/plugin
  adoption, cloud escalation, web browsing, or dependency addition.
- Authorization policy, roles, consent, audit persistence, or protected-memory
  retrieval.
- Changes to `/transcribe`, streaming, vision, robot code, audio format, or
  existing public response JSON.

## Readiness conditions for the canonical Plan 0003

Plan 0003 may be drafted as `Draft` after this document, but can become `Ready`
only when all are true:

1. Plan 0002 is Complete with its full verification evidence.
2. The implementation tree is re-read, including the actual P0.2 controller
   seam and all `/chat` tests.
3. The canonical plan states exact permitted files, Pydantic contracts, tool
   error/status mapping, response-validation rules, RED/GREEN tests, and
   unchanged public contract assertions.
4. It preserves the design decisions above or records an approved replacement
   decision before implementation begins.
