# Cognitive audit — Iroko

**Observed:** 2026-08-11
**Revision:** `01876ec` (`main`, equal to `origin/main`)
**Scope:** current tracked code, tests, configuration, plans, and CI/tooling. No
runtime provider, hardware, model, or network call was made. This is therefore
an implementation audit, not evidence of production hardware health.

> **Implementation update — 2026-08-11:** Plan 0002a subsequently removed the
> direct Anthropic dependency and runtime paths, made Ollama the only accepted
> provider, and added local streaming-fallback coverage. Its full verification
> record is in [`0002a-local-first-provider-quarantine.md`](../plans/0002a-local-first-provider-quarantine.md).
> On 2026-08-12, a real local Ollama generation and the text-to-LLM-to-Piper
> pipeline also completed successfully. The findings below are the
> pre-implementation audit snapshot; only the cloud-default finding is
> superseded by that completed plan.

## Executive summary

Iroko is currently a **typed, local-capable conversational system with
SQLite/sqlite-vec memory and on-demand visual adapters**. It is not yet a
situated multimodal cognitive system. The recent P0.2 work materially improved
safety: public turns default to an unknown person, use an opaque one-turn
history scope, do not read persistent memory, and do not schedule
consolidation. It also removed the fixed `voice-primary` runtime scope.

That safety boundary is not an end-to-end identity feature: no public adapter
instantiates `IdentitySessionRegistry` or supplies `ActivePersonContext` to
`/chat`, `/transcribe`, `/transcribe/stream`, or `/vision/respond`. Thus the
system does not currently confuse an unknown speaker with the owner, but it
also cannot reliably answer household-memory questions through those public
channels.

The critical remaining risks are: no authorization policy, a LAN-bound API
with unauthenticated face enrollment, string-valued relationships, universal
fact supersession, non-deterministic ages, and unconditional top-K vector
retrieval. There is no controlled cloud-escalation boundary, by deliberate
policy: no direct cloud provider remains in the runtime.
`CognitiveController`, deterministic family tools, entity-ID relationships,
`WorldState`, speaker recognition, identity fusion, scene graphs, and spatial
memory are absent from runtime code.

**Audit verdict: READY WITH WARNINGS.** The current tree supports planning the
next narrow, local-only controller slice, but `docs/plans/0003-typed-controller-and-deterministic-tools.md`
is still Draft and must be promoted to a precise Ready runbook before any code
implementation. This audit does not authorize that implementation.

## Evidence and verification boundary

### Repository baseline

| Item | Observed result |
|---|---|
| Branch / remote | `main...origin/main`; `origin` is `git@github-personal:pipec80/irokorobot.git` |
| Worktree before audit | Clean |
| Worktree after audit | Only this report is added |
| Ruff | `uv run ruff check .` passed |
| Formatting | `uv run ruff format --check .` passed; 171 files already formatted |
| Typing | `just typecheck` passed: mypy 65 source files, Pyright 0 errors/warnings |
| Focused cognitive test suite | 104 passed in 0.90 s |
| Full suite | `just test` was interrupted by this session's 64-second command limit; it is **not** claimed green in this audit |

The focused suite was:

```text
tests/unit/test_cognitive_models.py
tests/unit/test_active_person_identity.py
tests/unit/test_identity_sessions.py
tests/unit/test_text_turn.py
tests/integration/test_transcribe_memory.py
tests/integration/test_memory_relational.py
tests/integration/test_vision_memoria.py
```

## Architecture today

This flow is derived from `routers/*`, `text_turn.py`, `llm.py`, the memory
package, and the robot client; it is not a target diagram.

```text
robot microphone                 local chat              one requested camera frame
        |                            |                              |
        v                            v                              v
POST /transcribe[/stream]       POST /chat                POST /vision/respond
        |                            |                              |
  Faster-Whisper                   process_text_turn() <--- textual scene description
        |                            |                    (Ollama VLM; one frame)
        |                            v
        |                    unknown ActivePersonContext by default
        |                            |
        |             unknown/probable/ambiguous -> no history, retrieval, or write
        |             explicit internal manual context -> working history + build_context
        |                            |
        |                       character prompt + LLM provider
        |                   (Anthropic by default; Ollama when configured)
        |                            |
        +-- Piper TTS <-------------+-- optional background consolidation
                                             |
                                SQLite entities/facts/memories/sqlite-vec
```

`server/src/server/vision/perception.py:85` contains a combined
face-recognition-plus-description helper, but no production caller invokes it.
`/vision/respond` calls `perceive_scene()` instead (`routers/vision.py:172`),
so public visual dialogue currently uses scene text only, not recognized faces.

## Capability matrix

| Capability | State | Evidence | Risk | Priority |
|---|---|---|---|---|
| STT | Implemented | `server/stt.py`; `/transcribe` invokes `_run_stt()` | Runtime/model health not exercised | P1 |
| NLU / NLG | Partial | `llm.py:148-228`; prompts and provider adapters | LLM remains responsible for many factual answers | P0 |
| Working memory | Implemented, safely restricted | `memory/working.py`; `text_turn.py:145-177` | Public channels are intentionally one-turn only | P1 |
| Episodic memory | Partial | `consolidation.py:268-280` writes `kind="episodic"` | Public adapters cannot reach the write path | P1 |
| Semantic memory | Partial | `memory/semantic.py:106-177` | Always top-K; no policy, threshold, or reranking | P0 |
| Relational graph | Partial / legacy | `facts.object_value TEXT`; `memory/relations.py:20-107` | No target FK, inverse integrity, or tenant/person scoping | P0 |
| Onboarding | Implemented service, unavailable in public flow | `onboarding.py:44-108`; `text_turn.py:112-121` returns `False, None` | Owner-centric and deliberately suppressed | P1 |
| Personality | Implemented | `characters/iroko.py`; `characters/__init__.py:232-284` | Memory prompt still says “owner” | P1 |
| Vision | Implemented on demand | `routers/vision.py:65-190`; `vision/describe.py` | One ephemeral frame and free text only | P1 |
| Face recognition | Partial / not integrated | `vision/faces.py:204-340`; no runtime caller of `perceive()` | No ActivePersonContext bridge; enrollment is unauthenticated | P0 |
| Speaker recognition | Not found | No speaker embedding, verification, enrollment, or diarization code | Voice identity remains unknown | P1 |
| Diarization | Not found | No diarization runtime code or dependency | Multiple speakers cannot be separated | P1 |
| Identity fusion | Not found | `resolve_active_person()` accepts only manual/session evidence (`identity.py:143-211`) | Face, voice, and context cannot be fused | P1 |
| World model | Not found | No `WorldState` runtime symbol or service | No present-state representation | P1 |
| Scene graph | Not found | VLM returns only text; no typed relation model | No structured `person-holds-object` claims | P1 |
| Spatial memory | Not found | `SensorReading.location` is a string only (`schemas.py:199-218`) | No rooms, pose, map, last-seen, or place certainty | P1 |
| Cognitive controller | Not found | No runtime `CognitiveController` usage; only P0.3 Draft plan | Executive decisions remain implicit in `text_turn.py` | P0 |
| Tool execution | Not found | No `ToolRegistry`, `calculate_age`, or family tools in runtime code | LLM can still answer counts and ages | P0 |
| Permissions | Not found / partially fail-safe | Model types exist, but no evaluator; public unknown turns skip memory | No role/visibility enforcement; LAN endpoints unauthenticated | P0 |
| Provenance | Partial | facts retain `source_memory_id`; memories carry metadata | No typed assertion provenance or policy audit | P2 |
| Confidence | Partial | confidence fields and strict cognitive value objects | Retrieval and policy do not consume confidence semantically | P2 |
| Forgetting / lifecycle | Partial infrastructure | `retention.py` purges sensors/cache/outbox | No memory decay, archival policy, promotion, or reflection writer | P2 |
| Cloud escalation | Not found | No gateway/policy; `settings.py:13` defaults to Anthropic | Private conversational data may use cloud by default | P0 |

## Hypotheses revisited

| Hypothesis | Status | Evidence and impact |
|---|---|---|
| P0-A — speaker implicitly treated as owner | **RESOLVED (safety boundary)** | `text_turn.py:60-68` creates an unknown context without supplied evidence; lines 165-177 skip persistent context. `owner_name` is no longer a `Settings` field. This prevents the old attribution, but no public identity adapter exists. |
| P0-B — shared `voice-primary` history | **RESOLVED in runtime; configuration drift remains** | `/transcribe`, streaming, and visual dialogue use `new_interaction_scope()` at `transcribe.py:126-130`, `:174-177`, and `vision.py:178-182`. `.env.example:94-97` still documents the removed `VOICE_CONVERSATION_ID=voice-primary`. |
| P0-C — no speaker recognition | **CONFIRMED** | No code/dependency/test implements speaker embeddings, verification, enrollment, or diarization. STT is not speaker identity. |
| P0-D — absent permissions | **CONFIRMED** | `AuthorizationDecision` is a value type only (`cognition/models.py:93-105`); no policy evaluator/route integration exists. `server_host` defaults to `0.0.0.0` (`settings.py:39`), while `/vision/enroll` only checks `vision_enabled` (`routers/vision.py:96-135`). |
| P0-E — textual family relations | **CONFIRMED** | `schema.sql:33-47` uses `object_value TEXT`; `relations.py:38-50` compares text. No `relationships` table or target entity FK exists. |
| P0-F — all predicates are single-valued | **CONFIRMED** | `assert_fact()` defaults `supersede_existing=True` (`declarative.py:138-196`) and consolidation never overrides it. A second `le_gusta` would replace the first. |
| P0-G — age is static / not deterministic | **CONFIRMED** | Consolidation accepts both `fecha_nacimiento` and `edad` as extracted facts; date is stored in text. No `calculate_age` runtime function exists. |
| P0-H — unbounded top-K retrieval | **CONFIRMED** | `search_memories()` returns the nearest `k` only (`semantic.py:106-177`); it has no distance ceiling, policy/actor filter, sensitivity filter, reranker, or importance/recency scoring. |
| P1-A — onboarding incomplete | **PARTIAL** | Checklist has owner/date/home/relations/work/preferences, but one relation satisfies a family slot (`onboarding.py:58-75`). It is deliberately suppressed in `text_turn.py:112-121`, and no public identity path can persist it. |
| P1-B — vision has no world state | **CONFIRMED** | Request contract is one frame (`routers/vision.py:1-4`); perception is discarded after a textual response. |
| P1-C — no scene graph | **CONFIRMED** | No structured visual observation/relations; `describe_image()` returns `str`. |
| P1-D — no spatial memory | **CONFIRMED** | Only a free-text sensor location field exists; there is no room/place/pose/last-seen model. |
| P2-A — no deep consolidation lifecycle | **CONFIRMED** | Schema permits `episodic`, `semantic`, and `reflection`, but runtime consolidation writes only episodic records. Retention does not archive memories. |

## Confirmed problems

### P0 — privacy and controlled cognition

1. **No authorization enforcement; biometric enrollment is exposed on the LAN.**
   - Evidence: `settings.py:39` binds all interfaces; `main.py:108-112` mounts
     all routers; `routers/vision.py:96-135` accepts name plus image with no
     authentication, role, consent, or policy decision.
   - Impact: Any reachable client can enroll a face when vision is enabled.
     Unknown public turns are memory-safe, but that is not authorization.

2. **Cloud is the code and example-configuration default, without an
   escalation gateway.**
   - Evidence: `settings.py:11-13` and `.env.example:5-8` set Anthropic as the
     default; `llm.py:193-218` builds a prompt containing context/history and
     calls Anthropic whenever provider is not `ollama`; no
     `CognitiveEscalationGateway` runtime symbol exists.
   - Impact: The default conflicts with the local-first policy. An identified
     internal session can send formatted memory/context to a remote provider
     without deterministic authorization, minimization, or an audit record.

3. **The active-person implementation is a safe internal seam, not an
   operational identity feature.**
   - Evidence: `IdentitySessionRegistry` is referenced only by its module and
     tests; public router schemas contain no trusted local adapter for its
     evidence. `text_turn.py:165-177` skips memory without manual evidence.
   - Impact: Memory questions are not reliably answerable from public voice,
     chat, or visual flows. This is a correct safety failure, not a reason to
     reintroduce owner inference.

4. **Family knowledge cannot be safely counted or traversed.**
   - Evidence: relation targets are `facts.object_value TEXT` and lookups use
     exact strings (`relations.py:20-50`); no relationship table exists.
   - Impact: aliases/renames and inverse or multi-hop questions are fragile;
     deterministic `get_children` and `count_children` cannot be made correct
     on this representation.

5. **Fact cardinality is not modeled.**
   - Evidence: `assert_fact()` supersedes every active `(entity_id, predicate)`
     pair; only this writer is used by consolidation.
   - Impact: adding “Sofía likes robotics” can erase “Sofía likes coffee”.

6. **Ages, counts, permissions, and retrieval selection still lack
   deterministic boundaries.**
   - Evidence: no controller/tool registry/age function; semantic retrieval
     always passes top-K candidates; prompt assembly delegates factual wording
     to the LLM.
   - Impact: the LLM remains able to calculate or overstate facts that code
     should determine.

### P1/P2 — perception and memory lifecycle

7. **Face recognition is implemented but not used by visual dialogue or active
   identity.**
   - Evidence: `perception.perceive()` is called only in unit tests; the
     production visual route calls `perceive_scene()`.
   - Impact: enrolled face embeddings do not establish an active person, and
     visual replies cannot reliably say who is present.

8. **Current perception is ephemeral and unstructured.**
   - Evidence: VLM output is a `str`; no `WorldState` or scene observation
     runtime types exist.
   - Impact: questions requiring persistence, spatial certainty, tracking, or
     “where are we?” cannot be grounded.

9. **Memory lifecycle stops at episodic extraction.**
   - Evidence: `consolidation.py:271-280` writes episodic memory; no
     semantic/reflection writer, promotion, confirmation, archival, or memory
     decay implementation was found.
   - Impact: no safe path from observations to verified household knowledge.

## Architecture gaps

- `CognitiveController.handle(CognitiveEvent) -> ResponsePlan` and an
  executable, closed deterministic tool boundary.
- Entity-ID relationships, predicate cardinality, temporal validity, and
  migration from legacy text facts.
- Household roles, policy evaluator, visibility/sensitivity classification,
  explicit owner bootstrap, confirmation, and local audit record.
- A trusted local adapter that turns explicit manual selection into an active
  session; later, separate face/voice evidence adapters and conservative
  fusion. Face/voice confidence must never grant permission.
- Typed `SceneObservation` and ephemeral `WorldState`; later tracking and
  spatial memory only after a present-state contract exists.
- Deterministic age/count/preference tools; no LLM calculation or policy
  decision.
- Memory confidence/provenance, confirmation, promotion, reflection,
  forgetting/archive lifecycle, and bounded cloud escalation.

## Technical debt (not feature scope)

- `.env.example` retains `VOICE_CONVERSATION_ID=voice-primary`, although the
  setting and runtime use were removed by P0.2.
- Current docs and runtime disagree on local-first defaults: the repository
  presents local-first policy while `Settings.llm_provider` and the template
  default to Anthropic.
- The prompt's memory header says “Memoria activa sobre tu dueño” at
  `characters/__init__.py:340-349`, even though active identity is explicitly
  not ownership or authorization.
- The schema comments describe planned sensor modules that do not exist. This
  is documentation/schema intent, not an implemented world-state service.
- `memories.archived_at`, `outbox`, and several sensor tables express useful
  future infrastructure but do not establish the corresponding behavior.

## Recommended roadmap

### P0 — Foundation and safety

1. Resolve the local-first default/policy contradiction before enabling any
   controller migration that could pass protected data to a provider. Record
   the interim cloud behavior explicitly; do not silently treat a provider
   setting as authorization.
2. Promote Plan 0003 only after adding exact current file scope and tests.
   Implement its narrow `/chat` pilot: typed response plan plus local
   `get_current_date` and `calculate_age` from strict ISO input. Family/profile
   queries must remain `unknown` or `unauthorized` in this slice.
3. Implement relationships v4 additively: entity-ID targets, cardinality
   registry, normalized ISO birth-date handling, provenance/lifecycle fields,
   migration and compatibility tests. Do not reuse text relationships as a
   controller shortcut.
4. Implement fail-closed household authorization before protected retrieval,
   tools, writes, model context, enrollment, or any cloud consideration.
5. Connect only a trusted explicit local manual-selection adapter to the
   existing session registry. Keep face/voice separate evidence sources.

### P1 — Family cognition and situated perception

1. Replace owner-centric onboarding with explicit, confirmed household
   enrollment profiles.
2. Define typed scene observations and ephemeral `WorldState`; connect
   on-demand face results to identity evidence only after policy exists.
3. Add local speaker enrollment/verification and conservative face+voice
   fusion with `unknown` and `ambiguous` as normal results.
4. Add a room/place model, last-seen policy, and only then tracking/spatial
   memory.

### P2 — Long-term cognition

1. Add confidence calibration, provenance, confirmation, and promotion from
   episodic observation to verified semantic knowledge.
2. Add reflection, archival/forgetting policy, deletion/export rules, and
   evaluation metrics.
3. Add `CognitiveEscalationGateway` only after a local policy can authorize,
   redact/minimize, time-bound, budget, audit, and locally fall back.

### P3 — Embodiment

Do not begin ROS2, motors, navigation, SLAM, tracking, or physical autonomy
until P0/P1 policy, identity, deterministic tools, and world-state boundaries
are stable and tested.

## Proposed PR sequence

| PR | Scope | Exit criterion |
|---|---|---|
| 0 | Documentation gate: reconcile local-first default/remote-provider policy and revise Plan 0003 from Draft to a precise Ready runbook | No code; exact files, RED/GREEN commands, and explicit cloud boundary accepted |
| 1 | P0.3 `/chat` controller pilot with typed response plan and only date/ISO-age tools | No dependency/schema/audio/robot change; unsupported/protected family queries preserve `unknown`/`unauthorized` |
| 2 | P0.4 relational memory v4 migration and cardinality | Legacy data migrated additively; multiple preferences survive; relation targets are entity IDs |
| 3 | P0.5 household authorization | Denial happens before retrieval/context/model/write; owner bootstrap and enrollment are explicit local operations |
| 4 | P1.1 household onboarding and trusted active-session adapter | Restart-safe profile completion without inferring owner or role |
| 5 | P1.2 typed observation/world state, then separate face/voice evidence adapters | Ephemeral state, calibrated evidence, no permission grant from recognition |
| 6 | P2 lifecycle and controlled cloud gateway | Confirmed promotion/forgetting and audited, minimized, authorized escalation |

## First proposed implementation PR after the documentation gate

**Title:** `feat(cognition): pilot typed controller with deterministic calendar tools`

**Goal:** prove the controller seam on `POST /chat` without changing audio,
vision, persistence, relationships, permissions, provider behavior, or public
JSON.

**Proposed files (to freeze in the Ready plan):**

- Create `server/src/server/cognition/controller.py` — small injected
  `CognitiveController` and typed response planning boundary.
- Create `server/src/server/cognition/calendar_tools.py` — pure date/age
  functions using strict ISO dates and an injected clock/date.
- Create `server/src/server/cognition/response_plan.py` — immutable
  text-payload, information-need, tool-result, and response-plan contracts,
  reusing the P0.1 vocabulary.
- Modify `server/src/server/routers/chat.py` — adapter only; preserve request
  and response schemas exactly.
- Modify `server/src/server/text_turn.py` only if the Ready design proves a
  narrow adapter is necessary; do not broaden it into a controller rewrite.
- Add `tests/unit/test_calendar_tools.py` and
  `tests/unit/test_cognitive_controller.py`.
- Extend `tests/integration/test_chat_endpoint.py` for unchanged JSON and
  controller-pilot behavior.
- Modify `docs/plans/0003-typed-controller-and-deterministic-tools.md` only
  to record observed completion after all gates pass.

**Acceptance criteria:**

1. Date and age results are derived solely by Python from valid ISO input;
   birthday, leap-day, malformed, missing, and future-date cases are explicit.
2. The LLM cannot choose tools, compute age, upgrade uncertainty, write memory,
   grant access, or invoke a remote provider from the controller.
3. Family/profile/retrieval/perception requests do not use legacy text facts;
   they return a typed safe outcome until later PRs.
4. `/chat` request/response JSON remains byte-for-byte contract-compatible;
   `/transcribe`, streaming, vision, robot, schema, and dependencies remain
   unchanged.
5. Focused RED then GREEN tests, `uv run ruff check .`,
   `uv run ruff format --check .`, `just typecheck`, and `just test` pass with
   observed evidence.

## Scorecard

| Dimension | Score | Justification |
|---|---:|---|
| Conversation | 3/5 | STT, chat, streaming, LLM, and TTS are composed; public history is intentionally stateless and factual control is still prompt-led. |
| Memory | 2/5 | SQLite, entities, facts, episodic store, embeddings, and retrieval exist; current public channels cannot safely use them and lifecycle/cardinality are incomplete. |
| Identity | 1/5 | Strict models and manual-session seam exist, but no public trusted adapter, no speaker recognition, no face bridge, and no fusion. |
| Perception | 2/5 | One-frame VLM and a face-recognition service exist; face output is not connected to production dialogue/identity and there is no temporal state. |
| Deterministic reasoning | 1/5 | Some normalization and reverse lookup exist; no controller/tool registry, age calculation, reliable count, or policy engine. |
| Personality | 3/5 | Typed profile and prompt assembly are mature enough for expression; they must not be used as truth or access control. |
| Privacy | 1/5 | Unknown turns are memory-safe and frames are designed ephemeral, but API enrollment is unauthenticated and Anthropic is the default without escalation control. |
| World model | 0/5 | No `WorldState`, scene graph, tracking, place model, or spatial memory runtime implementation. |
| Testability | 4/5 | Strong type/lint configuration, 414 discovered test functions, and a 104-test focal suite passed; full-suite status was not re-established in this session. |
| Local-first | 2/5 | SQLite, embeddings, STT, TTS, VLM, and face inference can be local, but the configured/default text provider is Anthropic and no cloud policy gateway exists. |

## Explicit non-goals

- Do not reintroduce `owner_name`, a global voice session, identity inference
  from a name, or automatic memory writes for unknown speakers.
- Do not add LangChain, LangGraph, CrewAI, AutoGen, a multi-agent runtime,
  Kafka, Redis, Neo4j, Kubernetes, or a broad plugin system.
- Do not implement speaker recognition, face/voice fusion, tracking, maps,
  ROS2, navigation, motors, SLAM, or physical actions in P0.
- Do not use an LLM as the source of truth for identity, role, permissions,
  relationships, counts, dates, ages, or memory promotion.
- Do not add a cloud fallback before it is a bounded, authorized, minimized,
  auditable exception with a local failure path.
