# Current cognitive implementation

> **Observed:** 2026-08-03
>
> **Base commit:** `a590a3340b005ecb20851a8af097f0abd6115aef`
>
> **Scope:** code and repository structure inspected; the full runtime and
> hardware acceptance journey were not executed during this documentation pass.

## Accurate description

Iroko currently is a **channel-agnostic conversational brain with persistent
memory and on-demand visual perception**. It is more than
`STT -> LLM -> TTS`, but it is not yet a situated multimodal cognitive system.

```text
audio, text, or one requested frame
                |
                v
        channel-specific adapter
                |
                v
    working history + memory retrieval
                |
                v
 personality + onboarding + date + perception
                |
                v
              LLM
                |
                v
 response + optional background consolidation
```

The shared text-to-text path lives in `server/src/server/text_turn.py`.
`prepare_text_turn()` gathers memory and prompt inputs, `_generate()` invokes
the configured LLM, and `record_text_turn()` stores working history and may
schedule consolidation. This is the seed to evolve, not a module to replace in
one rewrite.

## Implemented capabilities

| Capability | State | Code evidence and boundary |
|---|---|---|
| Audio client | Implemented | `robot/audio_capture.py`, VAD, WAV encoding, playback, half-duplex FSM. |
| STT | Implemented | faster-whisper in `server/stt.py`; dynamic entity hotwords are supported. |
| LLM providers | Implemented/configurable | Ollama and Anthropic paths in `server/llm.py`; settings currently default to Anthropic, so local-first deployment requires explicit configuration until changed by a later plan. |
| TTS | Implemented | Piper with resampling to the audio contract in `server/tts.py`. |
| Text core | Implemented | `server/text_turn.py` is reused by voice, local chat, and vision response paths. |
| Diagnostic chat UI | Implemented | `chat_ui.py` serves same-origin local assets at `/chat-ui/`; `tests/integration/test_chat_ui.py` verifies HTTP delivery and static safety invariants. Historical M4 closure evidence is not preserved. |
| Working memory | Implemented | Bounded in-process history per `conversation_id` in `memory/working.py`. |
| Declarative memory | Implemented | SQLite entities and versioned string-valued facts in `memory/declarative.py`. |
| Relational lookup | Partial | `memory/relations.py` searches inverse predicates but destinations are names in `object_value`, not entity foreign keys. |
| Semantic/episodic memory | Implemented | SQLite + sqlite-vec, `memory/semantic.py`; top-K KNN has no relevance threshold or policy filtering. |
| Consolidation | Implemented | Background extraction plus deterministic normalization in `memory/consolidation.py` and `memory/normalize.py`. |
| Onboarding | Implemented/basic | Persistent slot checklist in `onboarding.py`; focused on one owner, not full household enrollment. |
| Personality | Implemented/basic | Typed axes, built-in Iroko profile, optional validated Markdown override, and dynamic prompt assembly. |
| Scene description | Implemented/on demand | One validated image sent to the VLM; frames are intended to remain ephemeral. |
| Face recognition | Implemented | InsightFace embeddings linked to the same SQLite person entities. |
| Streaming response | Implemented/optional | NDJSON sentence streaming exists beside the classic endpoint. |
| Operational FSM | Implemented/client only | `IDLE`, `LISTENING`, `THINKING`, `SPEAKING`, `LOOKING`, `ERROR`; this is not a cognitive world-state model. |
| Test suite | Present | 367 test functions were discovered; this documentation pass did not assert that every runtime/E2E test is currently green. |

Current HTTP routes are `/health`, `/chat`, `/transcribe`,
`/transcribe/stream`, `/vision/describe`, `/vision/enroll`, and
`/vision/respond`. The stable audio response contract remains governed by
[`implementation-guardrails.md`](implementation-guardrails.md).

The local diagnostic UI at `/chat-ui/` is a static mount rather than an OpenAPI
route. Its implementation is present in the current tree, but the historical
M4 record does not preserve affirmative evidence of the planned Playwright
test, wheel inspection, real-provider browser smoke, `025_m4` bitacora, or
final gate. It is therefore **implemented with historical closure not
demonstrated**, not a historically closed milestone.

## Current memory model

The SQLite schema is at migration version 3 and contains:

- `entities` with JSON attributes and aliases;
- `facts` with string `object_value`, confidence, and supersession history;
- `memories` with episodic/semantic/reflection kinds, importance, access data,
  and JSON entity references;
- `vec_memories` for 768-dimensional semantic embeddings;
- `face_profiles` and `vec_faces` from migration 3;
- sensor, event, embedding-cache, outbox, and metadata tables.

Some tables express future intent rather than an operational feature. There is
no current `server/sensors/` package, world-state service, outbox consumer, or
cloud synchronization worker.

## Verified architectural strengths

- Server and robot packages communicate only through API/media contracts.
- SQLite and sqlite-vec keep relational and vector memory in one local file.
- Entity aliases are deduplicated accent- and case-insensitively.
- Facts preserve superseded history instead of deleting corrections.
- Retrieval combines inverse relation triggers, named entities, and semantic
  memory.
- Consolidation validates LLM extraction before permanent storage.
- A face profile points to the same entity used by family memory.
- Personality configuration is separate from persistent household memory.
- Memory or model failures degrade instead of necessarily silencing the robot.

## Critical gaps that future work must not overlook

### Speaker identity is assumed

When `owner_name` exists, the prompt states that the current speaker is that
owner. Voice uses the default conversation ID `voice-primary`. Face recognition
does not prove who produced the audio. Different family members can therefore
share history and be treated as the owner.

### Authorization is absent

There is no household role or data-visibility enforcement before memory
retrieval. Face recognition is personalization evidence, not authorization.
Local network reachability is also not a permission model.

### Relations point to text

`Máximo -> hijo_de -> "Felipe"` does not enforce a foreign-key relationship to
Felipe's entity. Renames, aliases, ambiguity, multi-hop traversal, and owner
filtering remain fragile.

### Fact cardinality is not modeled

`assert_fact()` supersedes active facts sharing `(entity_id, predicate)` by
default. That is correct for a single active birth date or residence, but can
erase earlier values of multi-valued predicates such as `le_gusta` and
`alergico_a`.

### Ages are not deterministic

Birth dates are stored as free text and the LLM can calculate age. The target
must store an ISO birth date and use a Python date tool at query time; age is
derived state, not a permanent fact.

### Retrieval always returns nearest memories

Semantic search returns top-K results without a maximum distance threshold,
identity filter, authorization filter, sensitivity filter, or combined
importance/recency score. The least irrelevant memories can still enter the
prompt.

### Onboarding is owner-centric

One relation can mark a slot complete even when a family list is incomplete.
The current service does not create a complete per-person profile, consent,
visibility, dates, preferences, allergies, voice enrollment, or household map.
The `/chat` adapter also does not schedule persistent consolidation.

### Visual perception is textual and momentary

A requested frame yields a text description. There is no typed scene graph,
temporal tracking, object permanence, room model, location certainty, or
ephemeral `WorldState`.

### Memory lifecycle is incomplete

The schema supports episodic, semantic, and reflection kinds, but the normal
flow mainly writes episodic memories. It does not systematically promote
repeated observations to hypotheses, request confirmation, derive stable
knowledge, summarize old episodes, or forget by policy.

### Executive control is implicit

The current flow prepares context, calls an LLM, records the turn, and may
consolidate it. It cannot yet explicitly decide to identify the person, deny
retrieval, calculate an age, disambiguate a child, inspect current perception,
or request confirmation before writing sensitive knowledge.

## Explicitly not implemented

- speaker recognition, speaker verification, or diarization;
- multimodal identity fusion;
- household roles and per-memory visibility;
- deterministic cognitive tool registry;
- entity-to-entity relationship table and predicate cardinality policy;
- structured current world state or spatial memory;
- proactive event-driven behavior;
- cloud escalation policy/gateway;
- physical actions, motor safety, firmware, ROS2, navigation, or SLAM;
- remote dashboard, backup, restore, LTE, or media relay.

Documentation mentioning these features is a target or historical proposal,
not proof that they exist.
