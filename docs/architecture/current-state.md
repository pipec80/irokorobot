# Current cognitive implementation

> **Observed:** implementation and plan status aligned 2026-10-01 (Plan 0050
> server audit repairs closed on `fix/0050-server-audit-repairs`, 1695 tests
> passing at `dd388b1`, accepted on real hardware except the two-face veto; memory-path
> audit of the pipeline, 1557 tests passing on `e14c6ae`; Plan 0054
> PC-4 face-default identity fusion closed, accepted on real hardware, and its Plan 0055 follow-ups merged (PR #152, `1c0a914`) with 1607 tests passing; Plan 0046
> CM-0 benchmark and its measured RED baseline unchanged, no runtime memory change).
>
> **Implementation baseline:** `main` at `67d4be9` (Plan 0048 close). The
> paragraphs below retain the dated evidence of each accepted slice instead of
> presenting old test counts as a new full-suite run.
> Plan 0022 (P0-C6 reliable streaming output) is **complete and verified**:
> all 4 tasks passed task-scoped review, a whole-plan review found no
> Critical issues, and real `just run-server`/`just run-robot` operator
> evidence on 2026-08-20 confirmed the headline invariant on live hardware —
> see [Plan 0022](../plans/completed/0022-p0-reliable-streaming-output.md#execution-evidence).
> Plans 0025, 0026, 0027, and 0028 (owner-authenticated memory MVP, PC-1) are
> merged/executed; **PC-1 is accepted** — classic and streaming
> allowed/denied/replay/expiry scenarios each passed 3x with real hardware on
> 2026-08-21 (Plan 0028). Plan 0021 (P0-C5 typed intent resolution) is
> **complete and operator-confirmed**: 6/6 classic and 5/5 streaming
> acceptance cases passed on real hardware on 2026-08-21, all deterministic
> cases at `llm_ms=0` — see [Plan
> 0021](../plans/completed/0021-p0-typed-intent-resolution.md#execution-evidence).
> Plan 0023 (P0-C7 grounded visual dialogue) is **complete and
> operator-confirmed**: real hardware proved identity, enrollment,
> protected-household, grounded scene description, and VLM-down fallback,
> all 5 required cases PASS on 2026-08-21/2026-08-25 — see [Plan
> 0023](../plans/completed/0023-p0-grounded-visual-dialogue.md#execution-evidence).
> **P0 is fully operator-accepted (2026-08-25)**: the combined P0 runbook
> (R1+C1-S+C2-V+C3-Q, C5+C6+C7 together) passed, and Plan 0013's own R1
> debt closed the same day after fixing `WHISPER_INITIAL_PROMPT`/
> `WHISPER_HOTWORDS` (they still referenced the pre-rename "Omnibot" name,
> never "Iroko") — see [Plan
> 0013](../plans/completed/0013-p0-voice-controller-bridge.md#execution-evidence).
>
> **Plan 0029 (PC-2 — consented local face evidence)** merged 2026-08-25 (PR
> #73, squash, commit `4633685`): all 7 tasks complete, one commit per task
> plus one small test-maintenance follow-up commit, each independently
> code-reviewed. Full repository gates passed at merge time: `just lint`,
> `just typecheck` (mypy 89 files clean, pyright 0 errors), `just test` (905
> passed, 0 failed), `just audit`, and `just check` (16 hooks); the focused
> face-authentication scenario (161 tests) and the PC-1 PIN regression (45
> tests, proving the PIN path from Plans 0026/0027 is unmodified) both
> passed. **This plan has no liveness or anti-spoofing defense: a
> photograph of the owner held up to the camera authenticates under this
> slice.** PC-4 (Plan 0054, 2026-09-30) later added a `strong` assurance
> level for reserved data but no liveness defense. A first real-hardware
> proof of concept ran 2026-08-27 via the new
> unified `just onboard` flow — one successful live enrollment and
> face-authenticated turn on Pipec's own webcam, not a calibrated study.
> Calibrated real-camera acceptance closed 2026-09-01 as
> [Plan 0030](../plans/completed/0030-real-camera-face-acceptance.md) —
> see also [Plan 0029](../plans/completed/0029-consented-local-face-evidence.md).
> `face_authentication_match_threshold` moved from an unvalidated `0.25` to
> a measured `0.5815` (36 genuine samples, 18 impostor samples across 3
> unrelated identities, zero false accepts and zero false rejects), and 3
> accepted + 3 denied real turns confirmed it live through `just run-server`
> + `just run-robot`. **This is a provisional calibration, not a mature
> one** — the impostor set stays thin at 3 identities; a wider round remains
> welcome later, not required to keep this closed.
>
> **Verification boundary:** P0.3/P0.4 code and P0.5-A policy seams were
> inspected. P0.4 passed `just gate` (527 tests) before PR #40 merged it,
> adding an isolated v4 storage/migration foundation while retaining the v3
> runtime reader/writer. P0.5-A later passed its local 546-test gate and
> GitHub CI before PR #42 merged its policy/role/audit foundation. P0.5-B1
> later passed its local 555-test gate and GitHub CI before PR #45 merged its
> policy-gated, internal v4 reader. P0.5-B2 then passed `just lint`, `just
> typecheck`, `just test` (571 passed), `just audit`, `just check`, and five
> green GitHub CI checks before PR #48 merged its bounded internal family-tool
> seam. The P0 closure revalidation on merged `main` repeated the focused
> acceptance suite (20 passed), all five local gates, and `git diff --check`
> before this evidence update. This verifies the P0 foundation, not operator
> acceptance: [Plan 0013](../plans/completed/0013-p0-voice-controller-bridge.md)
> routes the classic voice path through the controller with an unknown public
> actor; its automated evidence and human `just run-server` plus
> `just run-robot` acceptance are now complete (2026-08-25), see above. The
> subsequent runtime-policy audit confirmed the streaming, visual-dialogue,
> QA-WAV, and protected-wording gaps. They were bounded by [Plan
> 0014](../plans/completed/0014-p0-runtime-policy-hardening-design.md), whose every
> slice (C1–C7) and the combined real operator run are now complete.
> Prior P0.3/P0-S verification includes `just lint`, `just typecheck`, `just
> test` (514 passed), `just audit`, and `just check`; P0-S2 evidence includes GitHub CI and
> `just services` detecting configured local models. Camera, microphone, LAN,
> biometric enrollment, real Ollama chat, and hardware acceptance were not
> executed in that earlier P0 foundation snapshot; the dated PC-1, PC-2 and
> server-baseline evidence above records the later real runs.
>
> **Latest repository test run:** `just gate` on 2026-10-01 at `dd388b1` (Plan
> 0050, all eleven code tasks applied): 1695 passed, lint, types, `ruff --select
> S` and `pip-audit` clean; the exact CI coverage command passed 1678 tests
> (17 deselected) with 91.69 % coverage; `uv lock --check`, `uv build
> --all-packages` and `git diff --check` clean. The baseline at `42b8908` was
> 1607. One earlier full `just test` at the same commit reported a single failed
> test that was not identified (the output had been truncated) and did not
> reproduce in four later full runs (three parallel, one serial coverage run); it
> is recorded in Plan 0050 as an open observation. The previous recorded run,
> 2026-09-30 at `e14c6ae`, passed 1557.
>
> **Historical test audit (2026-08-20):** `just test` completed with
> 635 passed and 6 failed. All six failures were in
> `tests/unit/test_robot_app.py`: the tracked tests assumed classic mode while
> the local `.env` supplied `ROBOT_STREAMING=true`. Re-running that unit file
> with `ROBOT_STREAMING=false` produced 20 passed. A subsequent full baseline
> with that same explicit override produced **641 passed in 29.81s**. This
> confirms the code baseline is green under the intended classic test posture
> while leaving an open test-isolation/configuration-drift defect: an unrelated
> local `.env` must not silently change unit-test mode.

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
 (face / face+voice / PIN resolve an actor for protected branches only)
                |
      no MANUAL evidence -> no history, retrieval or consolidation (every turn today)
                |
                v
P0 controller adapters (`/chat`, classic `/transcribe`, streaming audio, and visual dialogue)
  |-- deterministic date/strict-ISO age
  |-- protected household, no identified owner -> unauthorized
  |-- identified owner: child list/count -> policy-gated v4 tools
  |-- identified owner: other household questions -> "not connected yet"
  `-- generic text -> legacy local text turn
                |
                v
response + local Piper + optional legacy consolidation
```

`/transcribe/stream` and `/vision/respond` now create a fresh typed event and
ask the controller to decide before legacy generation. Safe plans never reach
the LLM, legacy memory, or consolidation. Since Plan 0023 (P0-C7), the
controller's `decide()` can also return a `SceneDescriptionRequest`
capability instead of a closed plan; only `/vision/respond`'s scene branch
may fulfill it by reading a frame and calling the VLM, and that description
goes directly to Piper — never through the legacy text LLM. A generic
non-scene visual request delegates to legacy generation with no perception
at all. This does not establish face identity, authorization, or durable
visual memory.

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
| Text, audio, and streaming paths | Implemented/policy parity worktree | Classic and streaming audio enter the controller; generic stream output keeps its existing NDJSON/TTS path. P0-C6 (Plan 0022) closed the silent-success gap: `done` is architecturally guarded behind at least one prior audio chunk, confirmed by 641 tests and a 2026-08-20 real microphone run. Plan 0041 (ADR-0012) added a privacy-safe terminal `error` event: every started `/transcribe/stream` now ends in exactly one `done` or `error`, never a silent truncation after headers are sent. |
| Server HTTP/ASGI hardening (Plan 0031 capsule + Plan 0048) | Closed 2026-09-03; final hardening 2026-09-07 | `create_app()` + a failure-safe `lifespan()` own every shared resource (httpx client, STT/TTS models, DB); `GET /ready` is a side-effect-free readiness probe distinct from `/health`; every route's real error codes are documented via OpenAPI; uploads are bounded twice (raw body + per-file); every SQLite write goes through one owned transaction primitive. Plan 0048 closed the second audit's four edges: free-text fields have a semantic `max_length` (chat/voice/vision, 4000 chars); `guarantee_terminal_event()` now provably emits exactly one terminal event (post-terminal producer lines dropped, latch checked in both failure paths); `/transcribe/stream`'s OpenAPI `200` is `application/x-ndjson` with the `StreamEvent` line shapes; `create_app(Settings(...))` drives lifespan behaviour with no global mutation. Uvicorn concurrency (`UVICORN_LIMIT_CONCURRENCY=100`) is still uncalibrated; since 2026-09-30 it is measured on the homelab server inside PC-5 (portfolio row 12), not in a separate `perf(...)` plan. Full narrative, measured evidence, and ADR cross-references: [`server-production-baseline.md`](server-production-baseline.md). |
| Server audit repairs (Plan 0050) | Closed 2026-10-01 on `fix/0050-server-audit-repairs`; accepted on real hardware by Pipec (the two-face veto was not run) | Closes the reproduced findings of the 0049 audit with no wire, schema or migration change. **Transport:** `llm_transport` is the one module that talks HTTP to Ollama — chat, streaming, vision and embeddings — and rejects a null or non-object message, a non-JSON body and a mid-stream `error` line as `LLMError` (a stream turn then speaks its fallback); this validates the transport envelope only, not the classic generated `response`/`emotion` object, which belongs to the voice-pipeline reliability plan. An AST guard keeps `ollama_url` out of every other module. **Images:** the 1280x720 bound is read from the header (explicit `pillow` dependency) before `cv2.imdecode`, EXIF-rotated frames stay bounded, and one `routers/image_upload.read_contract_image` replaced three copied readers; the unread `max_image_pixels` setting is gone. **Memory:** the policy-gated V4 reader returns a row only when its stored visibility and sensitivity equal the classification the policy authorized. **Hygiene:** five unread settings are removed and a test keeps dead knobs out; `app.state.ready` starts `False`; `create_app`'s docstring states its import-time side effect; three user-facing strings moved to voseo; `faces.recognize()` logs counts, never names; static guards pin one lifespan-owned HTTP client, V4 readers reachable only through the policy gate, no private SQL on V4 tables, and one aware-UTC check. **Owner → stranger matrix** (`tests/integration/test_owner_stranger_matrix.py`, real classic `/transcribe`, STT/TTS/LLM simulated, invented canaries, no frame): a stranger chats but receives no private context, a protected question is denied before the reader, "Recuerda esto para siempre" changes and consolidates nothing, a spent grant is not inherited by the next speaker. Two tests pin **documented limits** that Plan 0051 (ADR-0015) must change deliberately: a valid grant answers whoever presents it, and "¿quién soy?" spends the grant and names the owner. The matrix proves PIN behaviour on the classic route, not which physical person spoke and not streaming parity; the existing owner-authenticated, face-authenticated and identity-fusion suites cover those. **Hardware (Pipec, 2026-10-01, face and speaker flags on):** `just setup-personal status` still `personal_security_ready=True`; a protected child question answered through the face (`face_only`) in streaming (2995 ms) and classic (5291 ms); the same question answered through a fresh PIN with no face (`Identity fusion: pin`) and then denied without a token (`no_evidence`) in both modes; generic and "Te presento a mi amigo Tom" turns answered as conversation in both modes; a scene description answered correctly (cold VLM load, 116.6 s). Not run: the two-face veto. A streaming stream turn fell back to the audible phrase once (`invalid_protocol`, the open O-04 observation). |
| Working memory | Implemented, unreachable | Code keeps per-session history only with `MANUAL` evidence, and the production conversational routes never emit it (`IdentitySessionRegistry.select_person` has test callers only; tests and the offline `scripts/eval_chat.py` build that evidence directly). Every turn therefore starts with `history=None` and the scope is cleared after the reply, the face- or voice-identified owner included: there is no continuity even from one turn to the next (verified 2026-09-30). |
| Episodic/vector memory | Implemented/legacy, unreachable | SQLite + sqlite-vec; top-k retrieval has no policy filter or threshold. `memory/context.py::build_context` receives no actor or authorization; consolidation stores the full turn text. Both run only behind the same `MANUAL` gate, so neither runs today. Classic and streaming voice pass a consolidation scheduler; `/chat` does not. |
| Longitudinal conversational memory | Not demonstrated; split paths | Protected household reads use identity, authorization and V4 tools, while generic conversation uses the legacy turn. The controller does not propagate the resolved actor into that turn; durable legacy memory requires `MANUAL` evidence; consolidation writes legacy facts/episodes; semantic retrieval lacks person/visibility/sensitivity/authorization filters. Of the V4 family tools only the children list and count are wired to the controller; every other authorized household question answers that it is "todavía no está conectada", and no branch confirms, corrects or forgets a memory. See the [delivery map](../roadmap/conversational-memory-delivery-map.md). |
| Entities and facts v3 | Implemented/legacy | String relation targets and universal fact supersession remain. |
| Relational memory v4 foundation | Implemented/isolated | Additive SQLite tables, typed predicate registry, entity-ID relations, cardinality/lifecycle repositories, a dry-run-first local legacy migration ledger, and a bounded raw target-ID relation filter. |
| Consolidation | Implemented/gated | LLM extraction plus deterministic normalization; requires manual identity. |
| Typed cognitive vocabulary | Implemented | Immutable evidence/event/context/knowledge contracts. |
| Active person context | Implemented | Fuses manual, session, local-unlock, face and voice evidence (a voice only corroborates a face) and carries an `IdentityAssurance` (`none`/`basic`/`strong`); persisted role can be carried as context but identity is not authorization. |
| P0.3 cognitive controller | Implemented/chat and classic-voice bridge | Fresh typed event; immutable response plan; no FastAPI, SQLite, or provider dependency in the core. Classic voice enters with a public unknown actor. Since Plan 0050 `server.cognition` exports domain vocabulary only (the controller and household tools are imported from their own modules) and the controller's adapter imports are type-only, so importing it loads no `server` module outside `cognition` and neither `aiosqlite`, `fastapi` nor `httpx`; two subprocess probes in `tests/integration/test_import_graph.py` pin that and standalone import of every `server` module. |
| Deterministic calendar tools | Implemented/bounded | Current date and strict ISO birth-date age only; age is derived, never persisted. |
| Household authorization P0.5-A | Implemented/foundation | Pure fail-closed policy; additive role/audit SQLite records; explicit local owner bootstrap; `/chat` evaluates/audits protected branches as unknown before legacy delegation. |
| Household authorization P0.5-B1 reader | Implemented/internal | Closed-predicate v4 literal/relation reads evaluate and audit policy before storage; outputs are frozen `known`, `unknown`, or non-disclosing `unauthorized`. The B2 tools invoke it; the HTTP path reaches it only through the child list/count after a PIN token or face/voice evidence, and no prompt or LLM path does. |
| Household tools P0.5-B2 | Implemented/internal | Typed child list/count, preferences, birth date, and derived age tools authorize and audit before B1 reads; child relation/birth data require injected consent. |
| B2 controller dispatch | Implemented | Two self-child question patterns produce deterministic response plans through injected actor/consent seams. Since Plans 0026–0029 and 0054 those seams are fed by a PIN token (`/chat`, classic and streaming voice) or by face and voice evidence (voice channels only). |
| Personal owner/children/PIN setup (Plan 0025) | Implemented/local-only | `just setup-personal` bootstraps Pipec as sole owner, confirms the owner's children as active v4 `child_of` relations, and stores one scrypt-hashed PIN credential (`owner_pin_credentials`, migration 006). Idempotent rerun and PIN rotation are covered. Plan 0050 changed the input contract: the PIN format is validated first by one `validate_pin` (a malformed PIN writes nothing), children are optional (owner + PIN is a complete setup, a blank answer means none), only a comma separates two child names, and a rejected setup is a message with exit code 1, not a traceback. `personal_security_ready` now means an active owner holds the active credential, instead of global row counts, and revoking a household role revokes that person's PIN credential in the same transaction. |
| One-use owner-authenticated classic turn (Plan 0026) | Implemented; real-hardware acceptance closed | `POST /auth/owner/unlock` (loopback-only, rate-limited) issues a one-use `LOCAL_UNLOCK` grant (`OWNER_UNLOCK_TTL_SECONDS`, default 300 s); `X-Iroko-Identity-Token` is accepted by classic `/chat` and `/transcribe`; the controller awaits actor/consent resolution only for protected branches; a valid grant authorizes exactly one `personal_protected_read` of `child_data` through the existing v4 tool. Absent/expired/replayed/malformed tokens deny without disclosure, without calling the v4 reader, and the safe audit trail never carries the PIN/token/names. The robot can opt into one startup PIN prompt (`ROBOT_OWNER_UNLOCK_PROMPT`) and clears the token only on `authentication_consumed=true`. Plan 0028 (2026-08-21) proved the classic flow 3x on real microphone/speaker hardware, including expiry and generic non-consumption, cross-checked against the `authorization_audit_events` table directly. |
| One-use owner streaming parity (Plan 0027) | Implemented; real-hardware acceptance closed | `POST /transcribe/stream` accepts the same optional `X-Iroko-Identity-Token` and composes one `OwnerRequestResolver` per request before `decide(event)`, reusing Plan 0026's `OwnerUnlockService` unchanged. The terminal NDJSON `done` event gains an additive `authentication_consumed` boolean (default `false`); older robots parsing it without the field default safely to `false`. Generic/legacy streaming never resolves an actor and always reports `false`. The robot's `transcribe_stream()` sends the header when a token is held and clears `ctx.identity_token` only on a `done` with `authentication_consumed=true`; an EOF before `done` leaves it untouched (replay denied server-side). `ROBOT_OWNER_UNLOCK_PROMPT` now works with `ROBOT_STREAMING` — the prior startup guard pointing at this plan was removed. Plan 0028 (2026-08-21) proved the streaming flow 3x on real hardware; measured total latency was consistently lower than classic mode for the same answer (~1.9s vs ~2.0s) since audio starts on the first NDJSON chunk. |
| Owner-authenticated memory runtime acceptance (Plan 0028) | Executed 2026-08-21 — **PASS** for the PC-1 slice | Ran the full classic and streaming allowed/denied/replay/expiry/generic-non-consumption matrix 3x each on real hardware (`ntbk-pipec-2`), plus a direct SQLite inspection of `authorization_audit_events` (36 rows) confirming exact `execute_household_tool → read_household_data` ordering on every disclosure and no PIN/token/name leakage anywhere outside the `entities` table. Also ran Plan 0013's R1-01/R1-02/R1-03 cases: R1-01 and R1-02 passed; R1-03 failed after 5 attempts — Whisper "small" could not reliably transcribe the proper noun "Iroko" — which left Plan 0013 open on that independently tracked finding, per this plan's own rule that R1 does not gate the PC-1 verdict. That finding was later traced to the stale "Omnibot" Whisper prompt/hotwords and reconfirmed PASS on 2026-08-25, closing Plan 0013. Surfaced two other findings, neither blocking: a repeatable first-utterance-after-restart STT mis-transcription pattern, and a garbled `protected_household`-pattern match that can consume a fresh grant without disclosing or denying cleanly (no leak observed). Full untracked evidence: `project-history/acceptance/2026-08-21-owner-authenticated-memory.md`. |
| Typed intent resolution (Plan 0021 / P0-C5) | Executed 2026-08-21 — operator-confirmed | New pure `cognition/intent_resolution.py`: a closed, deterministic Spanish rule set (no LLM/VLM/embedding/database) with an `IntentResolution(need, match, rule_id)` contract, injected into `CognitiveController` as `intent_resolver` (default `resolve_information_need`), replacing the former inline `_classify_information_need`. `rule_id` is privacy-safe static metadata, never the utterance or a name. Since Plan 0050 every rule matches whole words, not substrings ("papas fritas", "los humanos" or "la primavera" are ordinary conversation); words that mean a relative only with a possessive (`papa`, `mujer`, `pareja`, `nino`) count right after one ("mi papá"); and "Te presento a …" is no longer an enrollment phrase (explicit face-learning phrases still are). Birth words and "relación" keep the reviewed over-blocking: a mention anywhere still gets the fixed denial. Precedence: own-child list/count → protected household/birth → supervised ambiguous STT aliases → current-date STT alias → current date → explicit age → relationship/profile → generic. Real hardware proved 6/6 classic and 5/5 streaming acceptance cases (`ntbk-pipec-2`), all deterministic cases at `llm_ms=0`, audibly confirmed. C6/C7 untouched (confirmed by `git diff --stat`). |
| P0 runtime acceptance | **Complete (2026-08-25)** | Enabled public routes enter the controller. Plans 0022 (streaming reliability), 0021 (typed intent, C5), 0023 (grounded visual dialogue, C7), and 0013 (voice-controller bridge, R1) are all complete with real operator evidence. The authenticated-owner proof (PC-1) is complete via Plan 0028. The combined P0-C runbook (R1+C1-S+C2-V+C3-Q) passed on commit `a07b731` — see [`p0-runtime-acceptance.md`](../runbooks/p0-runtime-acceptance.md). |
| Vision/VLM (Plan 0023 / P0-C7) | Executed 2026-08-21/2026-08-25 — operator-confirmed | Extracted C5's resolver with `SCENE_DESCRIPTION`, `ACTIVE_IDENTITY`, and `BIOMETRIC_ENROLLMENT` needs and one `SceneDescriptionRequest` capability type. Only `/vision/respond`'s scene branch reads a frame or calls the VLM; the grounded description goes directly to Piper (`ResponseSource.CURRENT_PERCEPTION`), never through the text LLM. Identity/enrollment speak exact fixed copy without ever touching the camera, even with vision disabled. `vision/triggers.py`'s parallel intent authority was deleted. Real hardware confirmed all 5 required cases: identity denial, grounded scene description with no second LLM, VLM-down exact fallback, enrollment rejection, and household denial. |
| Consented local face evidence (Plan 0029 / PC-2) | Merged (PR #73); real-camera calibration closed (Plan 0030, 2026-09-01, provisional) | Migration 007 (`face_consent_grants`) plus `memory/biometric_consent.py` grant/revoke/read consent, with revocation performing a real purge of `face_profiles` and `vec_faces` rows, not a soft flag. `IdentityEvidenceSource.FACE` is trusted as identified (`cognition/identity.py`); `VOICE` is resolvable only as a corroborating source (Plan 0054, Identity fusion row below) and `CONTEXT` remains unresolved. `cognition/face_authentication.py` adds a pure verdict function (0 faces -> unknown, 2+ faces -> ambiguous and terminal — never falls through to the PIN, one face matching another enrolled person -> `other_person`, which also denies and never falls through, one face otherwise -> unknown/identified by match+consent+role) and a lazy single-inference-per-turn `FaceRequestResolver`. The face-first composition with voice and the optional PIN now lives in `cognition/identity_fusion.py` (Plan 0054); `compose_face_then_pin_resolver()` was removed. A stricter, separate `settings.face_authentication_match_threshold` — measured by Plan 0030 at `0.5815` (was an unvalidated `0.25`) — applies on top of the existing generic `settings.face_match_threshold` (`0.4` in code, `0.65` sample override). `POST /auth/owner/face/enroll` and `/revoke` (loopback-only, requiring a fresh PIN-consumed token) always enroll the token's own owner, never a request-supplied name; the pre-existing quarantined public `POST /vision/enroll` is untouched and still returns 503. Classic and streaming `/transcribe` accept an optional multipart `frame` field gated by `settings.face_authentication_enabled` (default `False` — with it off, the frame is never even read) and report which evidence source authenticated the turn via an additive `identity_source: "face" \| "face_voice" \| "local_unlock" \| null` field, never a name or protected value. The robot opts in via `settings.robot_face_auth_enabled` (default `False`), attaching a captured frame to every turn when enabled (a camera failure degrades silently to no frame). **No liveness/anti-spoofing defense exists**: a photograph of the owner held up to the camera identifies at assurance `basic` (enough for ordinary private data such as the child read); Plan 0054 (PC-4) requires `strong` for reserved categories, which no capability uses yet, and does not defend replay — see the Identity fusion row. |
| Face profiles | Implemented/sensitive/consent-gated | SQLite-linked embeddings and recognition functions exist; Plan 0029 adds a consented, in-request runtime adapter behind `FACE_AUTHENTICATION_ENABLED` (default off) — see the row above. |
| Speaker recognition (Plan 0053 / PC-3B) | Merged behind a default-off flag; local acceptance run 2026-09-29 (one owner, one laptop microphone) | Plan 0047 (PC-3A, PR #134) measured a frozen SpeechBrain `1.1.1` ECAPA backend offline (threshold 0.4834, 0/24 impostor false accepts, 0/24 genuine false rejects in-sample, **6/8 replay probes accepted**, p95 231 ms). Plan 0053 turns it into runtime **evidence, never authority**: migration 008 (`voice_consent_grants`, `voice_profiles`, one 192-d float32 BLOB per reference tagged with `model_id`, no `vec0` table because the threshold is a distance to the reference **centroid**), `memory/voice_consent.py` (revocation purges every voiceprint in one transaction), `voice/voiceprints.py`, `voice/speaker_embedding.py` (the only place the runtime loads the model; identity from `settings`, lazy `torch` import, one bounded executor thread, silence and duration gates) and `cognition/speaker_authentication.py` (pure verdict table plus a request-scoped resolver). `POST /auth/owner/voice/enroll` and `/revoke` are loopback-only behind a fresh PIN-consumed token, always for the token's own owner; enrolment returns 503 while `SPEAKER_AUTHENTICATION_ENABLED` is off, revocation always works. With the flag on, `/transcribe` and `/transcribe/stream` consult the resolver **once per request, only after the owner's face matched** (Plan 0054, `FusedIdentityResolver`): a `verified` verdict raises that face to assurance `strong`, and `VOICE` never identifies anyone on its own — a voice without an owner's face is never embedded. Plan 0053 originally attached the evidence as untrusted with no effect on any outcome; that behaviour ended with PC-4. Verdicts are logged only (`verified`/`unknown`/`unavailable`), never a name, distance or score. Minimum 3 references; references from another model are ignored. A failed model load is not retried for `SPEAKER_MODEL_RETRY_COOLDOWN_S` (60 s) and the embedding is bounded by `SPEAKER_EMBED_TIMEOUT_S` (30 s): on expiry the verdict is `unavailable`. **Acceptance 2026-09-29:** 3 enrolments; 5 of 5 full-length genuine protected turns returned `verified` and were still denied without PIN/face; silence -> 422 before the resolver; a 1 s clip -> `unknown`; model files absent -> `unavailable` and a normal denial; revocation -> `unknown` and `voice_profiles`/active grants both 0 in SQLite. **Not measured:** impostors at runtime, genuine utterances between 1.5 s and 3 s, more than one acoustic condition, any second owner. **Replay and liveness are not defended**; the fusion is the next row. Default `SPEAKER_AUTHENTICATION_ENABLED=false`: with it off the model is never loaded and `torch` is never imported. |
| Identity fusion — face-default assurance (Plan 0054 / PC-4) | Closed 2026-09-30 (ADR-0016): `just gate` green; accepted on real hardware by Pipec | `IdentityAssurance` (`none`/`basic`/`strong`) is carried by `ActivePersonContext`, and `resolve_active_person` — still the only place that turns evidence into a status — fuses it as one deterministic table: the owner's face alone is `identified` at `basic` (the unchanged default path, no PIN); a face plus a verified voice **of the same person** is `strong`; a valid PIN token is `strong`; a voice alone is `probable` and never authorizes; a face and a voice of different people, another enrolled person's face, or two or more faces is `ambiguous`; expired evidence never participates. `cognition/authorization.py` adds `HIGH_ASSURANCE_CATEGORIES = {SECURITY}`: a request whose sensitivity includes one is denied with `policy_id` `p0.5.assurance-required` unless the actor is `strong`; every other category, including `CHILD_DATA`, needs `basic`. **No reserved capability exists yet** (no `SECURITY` data is stored or readable), so the rule is proven only by synthetic policy tests. `cognition/identity_fusion.py` holds one request-scoped `FusedIdentityResolver` (order: face; voice only when the face matched the owner; the PIN only when a token was presented and nothing resolved or vetoed) that replaced `compose_face_then_pin_resolver` and the Plan 0053 wrapper in `routers/transcribe.py`. Positive evidence of another person vetoes even with a valid PIN token and never consumes the token; a dead or unverified voice while the face matched still answers at `basic`; a turn with no owner face never builds or runs the speaker resolver. The only log carrier is a closed reason (`pin`, `face_and_voice`, `face_only`, `veto_other_person`, `veto_multiple_faces`, `backend_unavailable`, `no_evidence`) — never a name, transcript, distance or score — and the denial text does not change. The wire change is one additive value, `identity_source: "face_voice"`, in `TranscribeResponse` and the streaming `done` event. No new dependency or environment variable. The PIN is optional and administrative (loopback enrolment and revocation); recovery when biometrics fail is local administration, not a spoken step. **PC-4 follow-ups (Plan 0055, merged 2026-10-01 as PR #152, `1c0a914`; automated evidence plus one hardware sample):** a store error (`BrainMemoryError` or `aiosqlite.Error`) raised while the face is resolved no longer fails the turn: the face contributes no evidence and no veto, one class-only warning is logged, and resolution continues through the PIN path (no token: the generic denial; valid token: `local_unlock`), in classic and streaming routes. This guards the face lookups only, not PIN storage, the policy audit or a whole-database outage. With `FACE_AUTHENTICATION_ENABLED` / `SPEAKER_AUTHENTICATION_ENABLED` on, `lifespan` now loads the matching model before reporting ready (`vision/faces.warm_up`, `voice/speaker_embedding.warm_up`); a failed warm-up logs a warning and falls back to the lazy load; with both flags off nothing heavy is imported. **Hardware sample (Pipec, 2026-10-01, same laptop, face and speaker flags on, robot sending a frame):** start-up took 9 s from `starting` to `ONLINE` (face model about 1 s, speaker model about 3 s, both inside start-up); the first protected turn after the restart (`face_only`; the speaker verdict was `unknown`) took 3.58 s end to end with no model-load line, against 8 to 13 s on 2026-09-30. One sample, not a controlled before/after: no run on `main` was made in the same session. `IdentitySource` is defined once in `schemas.py` and the cognition layer has one `utc_now` (`cognition/clock.py`); the generated OpenAPI is byte-identical. `just gate` and `just test-cov` passed on the branch (1607 tests, 91.43 % coverage). A static independent review (reported by Pipec) found one blocker, fixed in the last code commit: a consent-read error no longer erases another enrolled person's veto. The other-person veto is now pinned against real role and consent rows (adult and no-role, with and without consent or token, both routes); a face matched to an entity with no household role still vetoes (decision D-3). **Not defended:** a photograph identifies at `basic` (unchanged); a photograph plus a recording of the exact question would satisfy `strong` once a reserved capability exists — replay and liveness are measured, not defended. **Evidence so far:** each code task observed RED before GREEN; the last full `pytest -n auto` on the branch passed 1556 tests (baseline on `main`: 1529); `tests/integration/test_face_authenticated_turn.py` passes unedited. **Real hardware (Pipec, 2026-09-30, one owner, one laptop camera and microphone):** owner alone `face_and_voice`; face with a muffled voice `face_only`; a voice recording with no face, and a covered camera, `no_evidence` (denied, the speaker never consulted); two people `veto_multiple_faces`; speaker model files hidden `backend_unavailable` (answered at `basic`); a phone-screen photo (3 attempts) and video (2 attempts) did not identify (`no_evidence`, denied) — which is not a liveness defense; the optional PIN-token case was not run. |
| Longitudinal-memory benchmark (CM-0) | Benchmark implemented; runtime unchanged; measured RED | Plan 0046 (closed 2026-09-08) repaired the two stale evaluator entrypoints, added `scripts/eval_longitudinal_memory.py` (an out-of-runtime observation instrument: strict suite loader + privacy validator + current-capability driver + deterministic scorer + safe runner + report) and the synthetic 9-scenario suite `tests/evals/golden_longitudinal_memory.yaml`, and recorded the first reproducible RED baseline (report `source_commit` `38fa89c`, added in `ac43c58`; `just eval-longitudinal --runs 3`, exit `1`): extraction scored precision `0.25` and recall `0.25`; the full run recorded 75 steps, 3 failed and 72 unsupported; all four frozen gates `FAIL`. The measurement is historical: memory code changed afterwards (PR #131, Plan 0053). The production database was not touched. See [`docs/evals/0046-longitudinal-memory-baseline.md`](../evals/0046-longitudinal-memory-baseline.md). No memory capability, authorization, or runtime behaviour changed. |
| Robot client | Implemented/body adapter | PC microphone/webcam/speaker workflow; not cognitive logic. |

## Deliberately absent or deferred

- a generic `ToolRegistry`; P0 uses closed typed tools and does not justify a
  registry or framework;
- public consent input, name grounding, or any route to protected v4 data other
  than the child list/count after a PIN token (`/chat`, voice) or face/voice
  evidence (voice channels); no protected value reaches a prompt or the LLM;
- operation-bound PIN grants (accepted ADR-0015 decision 1, Plan 0051): today a grant is bound to a person, an expiry and one use, not to a named operation, and it proves the PIN, not the speaker (ADR-0008); Plan 0050's matrix pins both limits;
- diarization and a second enrolled speaker or face (PC-6);
- a reserved-data capability (`SECURITY`): the `strong` requirement exists in policy and is proven only by synthetic tests, because nothing reserved is stored or readable yet;
- liveness/anti-replay defense for face and voice evidence (Plans 0029, 0054): a
  photograph of the owner identifies at assurance `basic`, and a photograph plus a
  recording of the exact question would satisfy `strong` once a reserved capability
  exists; PC-4 measured this on real hardware (a phone-screen photo and video did not
  identify) but does not defend it — no plan closes it yet; real-camera calibration/acceptance closed 2026-09-01 as
  [Plan 0030](../plans/completed/0030-real-camera-face-acceptance.md);
- typed `SceneObservation`, `WorldState`, tracking, scene graph, and spatial
  memory;
- cognitive memory lifecycle, confirmation, reflection, and forgetting;
- cloud escalation gateway, ROS2, motors, and physical actions.

The next product target after P0-C is the personal Iroko-and-Pipec companion
defined in [ADR 0006](../adr/0006-personal-and-family-companion-profiles.md).
General UI and family onboarding are deliberately later work.

## Active hardening status

The P0-S audit is authoritative for immediate pre-controller work:

- Plan 0002a completed the direct-cloud-provider quarantine.
- Plan 0002b **completed** public biometric-enrollment quarantine: direct
  enrollment returns a fixed 503 before any upload read or biometric write, and
  conversational enrollment phrases provide fixed guidance without enrollment.
  Existing biometric data is preserved; P0.5 owns the future policy.
- Plan 0002c **completed** desktop hardening and guidance alignment: Python and
  sample configuration bind loopback by default, LAN exposure requires an
  explicit untracked override, stale `VOICE_CONVERSATION_ID` guidance is gone,
  and diagnostics no longer promise public memory recall, enrollment, or face
  identity. The face threshold values remain intentionally unchanged pending a
  reproducible calibration.
- P0-S and Plan 0003 are **Complete**. P0.3 pilots a bounded `/chat`
  controller with immutable response planning plus deterministic current-date
  and strict ISO-birth-date age tools. It does not alter P0.4/P0.5 boundaries.
- Plan 0004's relational-memory decision and Plan 0005's P0.4 foundation are
  **Complete**. PR #40 merged as `3b01b58` after the final 527-test quality
  gate: migration 4 is additive, v4 repositories and a dry-run-first local
  migration command exist, and the legacy runtime reader/writer remains
  unchanged. Plan 0007 P0.5-A passed its local 546-test gate on
  `feat/p05-household-authorization`: migration 5 adds local roles/audit, and
  protected `/chat` requests are denied and audited before legacy generation.
  GitHub CI passed and PR #42 merged as `960f160`. Authorization still owns
  any v4 runtime retrieval or writes.
- Plan 0009 P0.5-B1 is **Complete**. PR #45 merged as `a7550d0` after local
  `just lint`, `just typecheck`, `just test` (555 passed in 54.17s), `just
  audit`, and `just check`, plus green GitHub title, quality/security, test,
  Python analysis, and CodeQL checks. It adds an internal policy-gated v4
  reader and inverse target-ID filter only. B2 tools/controller wiring,
  public trusted identity, consent persistence, and P1 onboarding remain
  deliberately unimplemented.
- Plan 0010 P0.5-B2 is **Complete**. PR #48 merged as `0d16969` after local
  `just lint`, `just typecheck`, `just test` (571 passed), `just audit`, and
  `just check`, plus green GitHub title, quality/security, test, Python
  analysis, and CodeQL checks. It adds a closed internal tool seam only;
  public identity/consent, broader family queries, prompts/LLM retrieval, and
  P1 remain deliberately unimplemented.

See [P0-S hardening audit](../history/audits/p0-s-hardening-audit.md) for evidence and
[plans](../plans/README.md) for execution status.

## Latest verification evidence

- P0.3 implementation: `just lint`, `just typecheck`, final `just test` (514
  passed in 36.25s), `just audit`, and `just check` passed. Focused response-plan,
  calendar, controller, and `/chat` tests were run as a RED/GREEN sequence.
- P0-S2 historical evidence: `just lint`, `just typecheck`, `just test` (500
  passed), and `just audit` passed. `just services` reported the configured
  chat, embedding, consolidation, and enabled VLM models available through the
  local Ollama daemon.
- Earlier P0-S evidence remains historical: `just test` passed 496 tests before
  PR #32, and a local `text -> LLM -> Piper` pipeline completed through Piper.
- P0.4 implementation: observed RED tests for the missing registry,
  repository, and migration modules; then focused GREEN coverage for registry,
  schema, repository, migration, and legacy compatibility. Final `just gate`
  passed with 527 tests, Ruff, formatting, mypy, Pyright, security checks, and
  `pip-audit`. The local CLI help confirms dry-run is the default and `--apply`
  is explicit. PR #40 merged after its GitHub CI checks. No real household
  database migration, hardware, camera, microphone, or real Ollama chat request
  was performed in this slice.

- P0 closure revalidation on merged `main` (`0d16969`): the policy-gated
  household acceptance, reader, authorization-runtime, and chat suites passed
  20 tests in 0.91s. `just lint` passed with 211 files unchanged; `just
  typecheck` reported no issues in 75 sources and Pyright reported zero errors;
  `just test` passed 571 tests in 42.64s; `just audit` found no known
  vulnerabilities; and `just check` passed every configured pre-commit hook.

- Plan 0022 (P0-C6) closure on `1927912`: `just lint`, `just typecheck` (mypy
  81 files + pyright, 0 errors), `just test` (641 passed), `just audit`, and
  `just check` (17 hooks) all passed. A whole-plan review over the full
  8-commit range found no Critical issues and traced the "every `done` has
  prior audio" invariant true across all 6 named invalid-output cases plus
  mid-stream provider failure; 3 Important findings were fixed in one
  combined fix wave with a scoped re-review, and one residual TTS-double-failure
  edge case was explicitly parked (see the plan's Execution Evidence). Real
  `just run-server`/`just run-robot` acceptance on 2026-08-20 with a
  disposable local DB confirmed zero silent successes across 4 live turns,
  including one live reproduction of the 2026-08-17 hybrid-output failure
  mode ending in an audible fallback instead of silence, and one correct
  non-disclosing family denial with `llm_ms=0`.

- Plan 0029 (PC-2) closure, merged 2026-08-25 (PR #73, squash, commit
  `4633685`): the focused face-authentication scenario (161 tests:
  `test_biometric_consent_schema.py`, `test_active_person_identity.py`,
  `test_face_authentication.py`, `test_owner_face_enrollment.py`,
  `test_face_authenticated_turn.py`, `test_server_client.py`,
  `test_robot_app.py`, `test_robot_app_streaming.py`) and the PC-1 PIN
  regression (45 tests: `test_owner_authenticated_turn.py`,
  `test_owner_authenticated_stream.py`, `test_vision_enroll_service.py`,
  `test_cognitive_controller.py`) both passed with no failures — the PIN
  path is unmodified. Full repository gates: `just lint` (clean), `just
  typecheck` (mypy 89 files clean, pyright 0 errors), `just test` (905
  passed, 0 failed), `just audit` (clean), `just check` (16/16 hooks
  passed), and `git diff --check` (clean) all passed on 2026-08-25. Every
  named threat case (unknown face, ambiguous/2+ faces terminal denial,
  revoked consent, non-owner role, expired evidence, no frame supplied,
  flag-disabled parity with `main`, no face detection on non-protected turns,
  enrollment without a fresh token, enrollment non-loopback, and no
  secret/embedding/frame in any log or audit row) has a real, specific
  covering test, sampled and confirmed passing. **This plan has no
  liveness/anti-spoofing defense**: a photograph of the owner authenticates
  under this slice; PC-4 (Plan 0054) later kept that at assurance `basic` and added the
  `strong` requirement for reserved data, with no liveness defense. Calibrated real
  camera/hardware acceptance (threshold tuning,
  false-accept/false-reject rates, lighting, distance, glasses) closed
  2026-09-01 as
  [Plan 0030](../plans/completed/0030-real-camera-face-acceptance.md):
  36 real genuine samples (Pipec, 3 lighting × 2 distance × 2 glasses) and
  18 real impostor samples (3 unrelated household identities) held zero
  false accepts and zero false rejects at a measured
  `face_authentication_match_threshold = 0.5815` (up from the unvalidated
  `0.25`), confirmed by 3 accepted + 3 denied real turns through
  `just run-server` + `just run-robot`. Explicitly provisional — only 3
  impostor identities were measured; a wider round is welcome but not
  required to keep this closed.

- Plan 0054 (PC-4) implementation (2026-09-30): the
  baseline `just gate` on `main` (`35f9eb5`) passed 1529 tests; each of the five code tasks
  observed its new tests RED before GREEN, and a mutation of the veto ordering was caught
  by four fused-resolver tests; the last full `just gate` passed 1557 tests, `ruff`,
  `mypy` and `pyright` were clean, and `tests/integration/test_face_authenticated_turn.py`
  passes unedited (the face alone still answers ordinary private data). Two timeout tests in
  `tests/unit/test_speaker_embedding.py` failed on some full runs: `embed_wav` imports `torch`
  lazily inside its executor thread, so the first such test in a cold `xdist` worker paid the
  import inside a 0.2 s window (cold process alone: 3 of 3 failed; torch pre-imported: 3 of 3
  passed). A module-scoped warm-up fixture fixed it, test-only; the defect predates this plan.
  Pipec then ran the real-hardware matrix (2026-09-30): see the Identity fusion row.

R1 runtime proof is complete — see
[Plan 0013](../plans/completed/0013-p0-voice-controller-bridge.md); the
authenticated-owner acceptance gate is defined in
[Plan 0024](../plans/completed/0024-owner-authenticated-memory-mvp-design.md). Its
executable sequence is
[0025](../plans/completed/0025-personal-owner-bootstrap-and-pin-setup.md) (merged) →
[0026](../plans/completed/0026-one-use-owner-authenticated-classic-turn.md) (merged) →
[0027](../plans/completed/0027-one-use-owner-streaming-parity.md) (merged) →
[0028](../plans/completed/0028-owner-authenticated-memory-runtime-acceptance.md)
(executed 2026-08-21, **PASS**), which completed the formal repeated
real-runtime acceptance for 0026/0027's classic and streaming flows. It also
executed R1 (Plan 0013): R1-01/R1-02 passed and R1-03 initially failed on STT
accuracy. That independent finding was later traced to the stale "Omnibot"
Whisper prompt/hotwords and reconfirmed PASS on 2026-08-25, closing Plan 0013.

These checks do not prove a real Ollama `/chat` request, camera, microphone,
biometric, LAN, or physical hardware behavior.
