# Current cognitive implementation

> **Observed:** 2026-08-12
>
> **Base commit:** `a936cf8` (`main`)
>
> **Verification boundary:** code, configuration, tests, and GitHub CI were
> inspected. A local Ollama generation and the `text -> LLM -> Piper` pipeline
> were executed. Camera, microphone, LAN, biometric enrollment, and hardware
> acceptance were not executed in this snapshot.

## Accurate description

Iroko is a **typed, local-first conversational runtime with persistent legacy
memory and on-demand visual adapters**. It is more than `STT -> LLM -> TTS`,
but it is not yet a situated multimodal cognitive system.

```text
audio, text, or one requested frame
                |
                v
      channel adapter / request scope
                |
                v
unknown ActivePersonContext by default
                |
      unknown -> no persistent retrieval or consolidation
                |
                v
personality + bounded prompt + local Ollama
                |
                v
response + local Piper + optional legacy consolidation
```

The shared text path is `server/src/server/text_turn.py`. Public channels use
fresh interaction scopes. A trusted manual/session `ActivePersonContext` exists
as an internal seam, but public adapters do not yet supply one; that deliberate
gap prevents owner-by-default memory disclosure.

## Implemented capabilities

| Capability | State | Boundary |
|---|---|---|
| STT | Implemented | Faster Whisper, CPU/int8 path. |
| TTS | Implemented | Piper local synthesis. |
| LLM | Implemented/local only | Ollama is the only accepted runtime provider. |
| Text, audio, and streaming paths | Implemented | Existing public contracts are preserved. |
| Working memory | Implemented/restricted | Unknown public turns use no persistent history. |
| Episodic/vector memory | Implemented/legacy | SQLite + sqlite-vec; top-k retrieval has no policy filter or threshold. |
| Entities and facts v3 | Implemented/legacy | String relation targets and universal fact supersession remain. |
| Consolidation | Implemented/gated | LLM extraction plus deterministic normalization; requires manual identity. |
| Typed cognitive vocabulary | Implemented | Immutable evidence/event/context/knowledge contracts. |
| Active person context | Implemented/internal | Manual/session evidence only; identity is not authorization. |
| Vision/VLM | Implemented/on demand | One ephemeral frame, free-text scene description. |
| Face profiles | Implemented/sensitive | SQLite-linked embeddings; not an active-person adapter. |
| Robot client | Implemented/body adapter | PC microphone/webcam/speaker workflow; not cognitive logic. |

## Deliberately absent or deferred

- `CognitiveController`, `ToolRegistry`, deterministic family tools, and
  `calculate_age()`;
- entity-ID relationships, predicate cardinality, and Memory v4;
- household authorization and trusted owner bootstrap;
- speaker recognition, diarization, and identity fusion;
- typed `SceneObservation`, `WorldState`, tracking, scene graph, and spatial
  memory;
- cognitive memory lifecycle, confirmation, reflection, and forgetting;
- cloud escalation gateway, ROS2, motors, and physical actions.

## Active hardening status

The P0-S audit is authoritative for immediate pre-controller work:

- Plan 0002a completed the direct-cloud-provider quarantine.
- Plan 0002b is **Ready** to quarantine both public biometric enrollment paths.
- Plan 0002c remains **Draft** until P0-S1 is merged and its configuration
  assumptions are revalidated.

See [P0-S hardening audit](p0-s-hardening-audit.md) for evidence and
[plans](../plans/README.md) for execution status.

## Latest verification evidence

- `just test`: 496 passed before PR #32 merge; the PR's remote CI and CodeQL
  checks completed successfully.
- `just lint`, `just typecheck`, and `just audit` passed before that merge.
- Ollama exposed `qwen2.5:3b`; a direct generation succeeded and
  `just test-pipeline --text ... --no-play` completed through Piper.

These checks do not prove camera, microphone, biometric, LAN, or physical
hardware behavior.
