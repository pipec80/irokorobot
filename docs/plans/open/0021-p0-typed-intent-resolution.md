# P0-C5 Typed Intent Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Status:** Ready for implementation after Plan 0022 and after PC-1 explicit
owner authentication (execution order revised 2026-08-20). Specify and test the
resolver against both an identified owner and an unknown speaker, not only
against a permanently anonymous one.

## Current code audit and reuse boundary

This plan has not been executed: `cognition/intent_resolution.py`, the reviewed
Spanish corpus, its dedicated unit suite, and recorded RED/GREEN/operator
evidence do not exist. The controller does already contain an inline
`_classify_information_need` function, NFD/casefold normalization, the
`InformationNeed` vocabulary, policy/tool dispatch, immutable response plans,
and shared classic/streaming/chat/vision controller composition.

Implementation must extract and inject the bounded resolver described here
while preserving those working seams. It must not rebuild the controller,
authorization policy, household tools, route adapters, or LLM path. Closure
requires the missing typed contract, normalization/precedence behavior,
privacy-safe `rule_id`, supervised corpus, route parity tests, and the real C5
operator rerun.

**Goal:** Replace the controller's growing inline phrase checks with one pure,
typed, supervised Spanish intent resolver that handles the transcripts observed
in operator QA without using an LLM, embeddings, fuzzy matching, or runtime
self-learning.

**Architecture:** A new cognition service owns normalization, precedence,
reviewed phrase rules, and non-sensitive rule identifiers. The
`CognitiveController` consumes an injected `IntentResolution` and remains the
sole owner of policy, tools, audit, response planning, and legacy delegation.
Classic, streaming, chat, and vision adapters keep their current composition;
there is no router-level classifier.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, existing FastAPI adapters and
`just` gates; no dependency, model, database, environment, audio, or HTTP
contract change.

## Global Constraints

- Read `AGENTS.md`, Plan 0020, the P0 runtime runbook, and every permitted file
  below before editing.
- Keep `InformationNeed` in `cognition/response_plan.py`; C5 adds no visual,
  identity, or biometric enum values.
- Resolution is deterministic and pure. No LLM, VLM, embedding, edit distance,
  fuzzy score, database query, cloud call, or runtime mutation is allowed.
- A supervised STT alias is a reviewed exact normalized phrase, not a claim of
  confidence and not learned automatically from household speech.
- Protected household and birth-data rules precede date and age rules so
  `fecha de nacimiento de mi hija` and `edad de mi hija` cannot bypass policy.
- `rule_id` must be a stable technical identifier and must never contain the
  original utterance, a person's name, a birth date, or another protected
  value.
- Preserve public unknown identity, policy-before-retrieval, audit-before-data,
  conversation-scope isolation, and WAV 16 kHz mono signed-int16 behavior.
- Do not touch streaming protocol/fallback code (C6) or visual routing/VLM
  grounding (C7).

## File Map

Create:

- `server/src/server/cognition/intent_resolution.py` — pure typed resolver and
  closed Spanish rules.
- `tests/fixtures/intent_resolution_es.json` — reviewed synthetic/approved
  corpus with expected need, match kind, and rule ID.
- `tests/unit/test_intent_resolution.py` — corpus, precedence, normalization,
  privacy, and purity tests.

Modify:

- `server/src/server/cognition/controller.py` — inject and consume resolver;
  retain tools/policy/plans.
- `server/src/server/cognition/__init__.py` — re-export the public resolver
  contracts.
- `tests/unit/test_cognitive_controller.py` — resolver seam and no-legacy
  assertions.
- `tests/unit/test_cognitive_models.py` — public export regression.
- `tests/integration/test_transcribe_pipeline.py` — classic date and ambiguous
  transcript regressions.
- `tests/integration/test_transcribe_stream.py` — streaming parity for the same
  transcripts.
- `docs/architecture/current-state.md`,
  `docs/architecture/p0-runtime-policy-audit.md`,
  `docs/plans/open/0014-p0-runtime-policy-hardening-design.md`,
  `docs/plans/README.md`, and `docs/runbooks/p0-runtime-acceptance.md` — only
  evidence actually observed after GREEN.

Conserve as regression suites without widening their responsibility:

- `tests/integration/test_chat_endpoint.py`
- `tests/integration/test_vision_dialog.py`

---

### Task 1: Add the typed resolver and supervised corpus

**Files:**

- Create: `server/src/server/cognition/intent_resolution.py`
- Create: `tests/fixtures/intent_resolution_es.json`
- Create: `tests/unit/test_intent_resolution.py`

**Interfaces:**

- Consumes: `InformationNeed` from `cognition.response_plan`.
- Produces:

  ```python
  class IntentMatch(StrEnum):
      EXACT = "exact"
      SUPERVISED_STT_ALIAS = "supervised_stt_alias"
      NONE = "none"


  class IntentResolution(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")

      need: InformationNeed
      match: IntentMatch
      rule_id: str | None


  def resolve_information_need(message: str) -> IntentResolution:
      """Resolve one bounded information need from reviewed Spanish rules."""
  ```

- [ ] **Step 1: Write the reviewed fixture.**

  Store objects with exactly `text`, `need`, `match`, and `rule_id`. Include at
  least this matrix:

  | Text | Need | Match | Rule ID |
  |---|---|---|---|
  | `¿Cómo se llaman mis hijos?` | `own_children_list` | `exact` | `own_children.list.v1` |
  | `¿Cuántos hijos tengo?` | `own_children_count` | `exact` | `own_children.count.v1` |
  | `¿Quiénes son mis niños?` | `protected_household` | `exact` | `household.protected.v1` |
  | `¿Cuándo nació Máximo?` | `protected_household` | `exact` | `birth.protected.v1` |
  | `fecha de nacimiento de mi hija` | `protected_household` | `exact` | `birth.protected.v1` |
  | `¿Qué edad tiene mi hija?` | `protected_household` | `exact` | `household.protected.v1` |
  | `¿Qué fecha es hoy?` | `current_date` | `exact` | `date.current.v1` |
  | `¿Qué día es hoy?` | `current_date` | `exact` | `date.current.v1` |
  | `Dime la fecha actual.` | `current_date` | `exact` | `date.current.v1` |
  | `Me dice la fecha actual.` | `current_date` | `supervised_stt_alias` | `date.current.stt.v1` |
  | `¿En qué fecha estamos?` | `current_date` | `exact` | `date.current.v1` |
  | `¿Qué día soy?` | `ambiguous_date_query` | `supervised_stt_alias` | `date.ambiguous.stt.v1` |
  | `¿Qué vía es hoy?` | `ambiguous_date_query` | `supervised_stt_alias` | `date.ambiguous.stt.v1` |
  | `¿Qué edad tengo?` | `explicit_birth_date_age` | `exact` | `age.explicit.v1` |
  | `Calcula mi edad desde 1980-08-17` | `explicit_birth_date_age` | `exact` | `age.explicit.v1` |
  | `¿Qué relación existe?` | `relationship_or_profile` | `exact` | `relationship.profile.v1` |
  | `Hola, ¿cómo estás?` | `generic_conversation` | `none` | `null` |

- [ ] **Step 2: Write failing parametrized resolver tests.**

  Load the JSON via `Path(__file__).parents[1] / "fixtures" /
  "intent_resolution_es.json"`, construct the expected enums, and assert the
  complete `IntentResolution`. Add explicit tests that accent/case/punctuation
  normalization is stable, `rule_id` never contains normalized input tokens
  such as `maximo`, and the frozen model rejects mutation.

- [ ] **Step 3: Run RED.**

  ```powershell
  uv run pytest -n0 tests/unit/test_intent_resolution.py -v
  ```

  Expected: collection fails because `cognition.intent_resolution` does not
  exist.

- [ ] **Step 4: Implement the minimal pure resolver.**

  Move the existing normalization and lexicons out of `controller.py`. Use
  immutable tuples/frozensets and small private predicates. Return through one
  helper so every branch supplies all three fields:

  ```python
  def _resolution(
      need: InformationNeed,
      match: IntentMatch,
      rule_id: str | None,
  ) -> IntentResolution:
      return IntentResolution(need=need, match=match, rule_id=rule_id)
  ```

  Apply precedence exactly as follows: own-child list/count; protected
  household/birth; ambiguous STT aliases; current date; any explicit age need
  containing normalized `edad` or `anos`; relationship/profile; generic. ISO
  strictness belongs to `_age_result()` in the controller: a non-ISO age
  request must remain a safe deterministic UNKNOWN, never generic LLM. Do not
  encode visual phrases in C5. Use closed rule helpers with these returns:

  ```python
  if _matches_own_children_list(normalized):
      return _resolution(InformationNeed.OWN_CHILDREN_LIST, IntentMatch.EXACT, "own_children.list.v1")
  if _matches_own_children_count(normalized):
      return _resolution(
          InformationNeed.OWN_CHILDREN_COUNT, IntentMatch.EXACT, "own_children.count.v1"
      )
  if _contains_protected_household_or_birth(normalized):
      return _resolution(
          InformationNeed.PROTECTED_HOUSEHOLD, IntentMatch.EXACT, _protected_rule_id(normalized)
      )
  if normalized in _AMBIGUOUS_DATE_ALIASES:
      return _resolution(
          InformationNeed.AMBIGUOUS_DATE_QUERY,
          IntentMatch.SUPERVISED_STT_ALIAS,
          "date.ambiguous.stt.v1",
      )
  if normalized in _CURRENT_DATE_STT_ALIASES:
      return _resolution(
          InformationNeed.CURRENT_DATE, IntentMatch.SUPERVISED_STT_ALIAS, "date.current.stt.v1"
      )
  if _is_current_date_request(normalized):
      return _resolution(InformationNeed.CURRENT_DATE, IntentMatch.EXACT, "date.current.v1")
  if "edad" in normalized or "anos" in normalized:
      return _resolution(
          InformationNeed.EXPLICIT_BIRTH_DATE_AGE, IntentMatch.EXACT, "age.explicit.v1"
      )
  ```

  Normalize only for classification: NFD-decompose, remove combining accents,
  casefold, replace each non-word run with one space, then collapse and trim
  whitespace. Store aliases in that punctuation-free canonical form (`me dice
  la fecha actual`, `que dia soy`, `que via es hoy`). The controller must still
  pass the original message to `_age_result()` so ISO extraction is unchanged.

- [ ] **Step 5: Run GREEN and commit.**

  ```powershell
  uv run pytest -n0 tests/unit/test_intent_resolution.py -v
  just lint
  git add server/src/server/cognition/intent_resolution.py tests/fixtures/intent_resolution_es.json tests/unit/test_intent_resolution.py
  git commit -m "feat(cognition): add typed intent resolution"
  ```

  Expected: all resolver cases pass and the commit contains only this task.

---

### Task 2: Inject the resolver into the controller

**Files:**

- Modify: `server/src/server/cognition/controller.py:1-300`
- Modify: `server/src/server/cognition/__init__.py`
- Modify: `tests/unit/test_cognitive_controller.py`
- Modify: `tests/unit/test_cognitive_models.py`
- Modify: `tests/integration/test_transcribe_pipeline.py`
- Modify: `tests/integration/test_transcribe_stream.py`
- Modify: `tests/integration/test_transcribe_memory.py`

**Interfaces:**

- Consumes: `resolve_information_need(message) -> IntentResolution`.
- Produces:

  ```python
  type IntentResolver = Callable[[str], IntentResolution]
  ```

  and an optional constructor dependency:

  ```python
  intent_resolver: IntentResolver = resolve_information_need
  ```

- [ ] **Step 1: Write failing injection tests.**

  Inject a resolver mock returning
  `IntentResolution(need=InformationNeed.CURRENT_DATE, match=IntentMatch.EXACT,
  rule_id="test.date")`; assert it receives the original transcript once and
  the legacy delegate is not awaited. Inject one returning
  `IntentResolution(need=InformationNeed.GENERIC_CONVERSATION,
  match=IntentMatch.NONE, rule_id=None)`; assert `decide()` returns `None` and
  `handle()` alone delegates. Add a non-ISO age test asserting the fixed
  exact `No puedo calcular la edad sin una fecha de nacimiento ISO válida.`
  response and no legacy call. Extend the public-export test with
  `IntentMatch`, `IntentResolution`, and `resolve_information_need`.

  Before implementation, also add named route regressions:

  - `test_transcribe_supervised_date_alias_avoids_llm`
  - `test_transcribe_ambiguous_date_alias_avoids_llm`
  - `test_stream_supervised_date_alias_avoids_llm`
  - `test_stream_ambiguous_date_alias_avoids_llm`

  Each freezes the date to `2026-08-17`, mocks STT with the exact operator
  transcript, asserts exact text/TTS, `llm_ms == 0`, and no legacy or streaming
  LLM call. Parametrize
  `test_transcribe_private_family_question_is_audited_before_memory_or_legacy`
  in `test_transcribe_memory.py` with `fecha de nacimiento de mi hija` and
  `qué edad tiene mi hija`; retain its no-reader/no-legacy/safe-audit asserts.
  Do not rely on a `-k` substring to select them.

- [ ] **Step 2: Run RED.**

  ```powershell
  uv run pytest -n0 tests/unit/test_cognitive_controller.py tests/unit/test_cognitive_models.py tests/integration/test_transcribe_pipeline.py tests/integration/test_transcribe_memory.py tests/integration/test_transcribe_stream.py -v
  ```

  Expected: constructor rejects `intent_resolver`, exports are missing, and the
  new route cases still fall through to the LLM or old ambiguity behavior.

- [ ] **Step 3: Wire the injected service.**

  Store `self._intent_resolver`; in `decide()` use:

  ```python
  resolution = self._intent_resolver(event.payload.message)
  need = resolution.need
  ```

  Delete the moved constants and `_classify_information_need`,
  `_normalize_message`, and `_is_current_date_request`. Keep
  `_ISO_DATE_PATTERN`, `_age_result`, response builders, policy, audit, and
  household tools in the controller. Re-export only the three public resolver
  names from `cognition/__init__.py`.

- [ ] **Step 4: Run controller GREEN and commit.**

  ```powershell
  uv run pytest -n0 tests/unit/test_intent_resolution.py tests/unit/test_cognitive_controller.py tests/unit/test_cognitive_models.py tests/integration/test_transcribe_pipeline.py tests/integration/test_transcribe_memory.py tests/integration/test_transcribe_stream.py -v
  just lint
  git add server/src/server/cognition/controller.py server/src/server/cognition/__init__.py tests/unit/test_cognitive_controller.py tests/unit/test_cognitive_models.py tests/integration/test_transcribe_pipeline.py tests/integration/test_transcribe_memory.py tests/integration/test_transcribe_stream.py
  git commit -m "refactor(cognition): inject intent resolver"
  ```

  Expected: controller behavior is unchanged except for the reviewed new
  phrases, and no adapter test is needed to instantiate the default resolver.

---

### Task 3: Prove shared-route parity and obtain independent review

**Files:**

- Test: `tests/integration/test_transcribe_pipeline.py`
- Test: `tests/integration/test_transcribe_stream.py`
- Test unchanged: `tests/integration/test_transcribe_memory.py`
- Test unchanged: `tests/integration/test_chat_endpoint.py`
- Test unchanged: `tests/integration/test_vision_dialog.py`

**Interfaces:**

- Classic `POST /transcribe` keeps the existing JSON response.
- Streaming `POST /transcribe/stream` keeps existing NDJSON.
- `Me dice la fecha actual.` must produce the deterministic date with
  `llm_ms == 0`; `¿Qué vía es hoy?` must produce the fixed clarification with
  `llm_ms == 0`; protected collisions must deny before legacy/memory.

- [ ] **Step 1: Run the complete shared-route regression.**

  The route tests were written before Task 2 implementation, so their RED and
  GREEN are already attributable to the resolver wiring. Run all listed files
  without `-k` so protected-collision cases cannot be skipped.

  ```powershell
  uv run pytest -n0 tests/unit/test_intent_resolution.py tests/unit/test_cognitive_controller.py tests/integration/test_chat_endpoint.py tests/integration/test_transcribe_pipeline.py tests/integration/test_transcribe_memory.py tests/integration/test_transcribe_stream.py tests/integration/test_vision_dialog.py -v
  ```

- [ ] **Step 2: Run the focused route selection.**

  ```powershell
  uv run pytest -n0 tests/integration/test_transcribe_pipeline.py tests/integration/test_transcribe_memory.py tests/integration/test_transcribe_stream.py -k "date or ambiguous or private_family" -v
  ```

  Expected: PASS if Tasks 1-2 are correct; any failure is a C5 routing defect
  and must be fixed in the resolver, never duplicated in a router.

- [ ] **Step 3: Request independent code and spec review.**

  Give the reviewer Plan 0020, this plan, the C5 commits, and exact RED/GREEN
  logs. Require an explicit PASS for precedence, privacy-safe `rule_id`, public
  unknown policy, route parity, and C6/C7 non-interference. Address every P0/P1
  finding with a new failing regression before continuing.

- [ ] **Step 4: Re-run shared-controller regression after review fixes.**

  ```powershell
  uv run pytest -n0 tests/unit/test_intent_resolution.py tests/unit/test_cognitive_controller.py tests/integration/test_chat_endpoint.py tests/integration/test_transcribe_pipeline.py tests/integration/test_transcribe_memory.py tests/integration/test_transcribe_stream.py tests/integration/test_vision_dialog.py -v
  ```

  Expected: all routes share controller outcomes; no visual behavior is added;
  reviewer PASS is recorded in this plan's execution evidence.

---

### Task 4: Verify, document, and perform the C5 operator rerun

**Files:**

- Modify only after evidence: `docs/architecture/current-state.md`
- Modify only after evidence: `docs/architecture/p0-runtime-policy-audit.md`
- Modify only after evidence: `docs/plans/open/0014-p0-runtime-policy-hardening-design.md`
- Modify only after evidence: `docs/plans/README.md`
- Modify only after evidence: `docs/runbooks/p0-runtime-acceptance.md`
- Modify: this plan's status/evidence section

- [ ] **Step 1: Run repository gates.**

  ```powershell
  just lint
  just typecheck
  just test
  just audit
  just check
  git diff --check
  ```

  Record exact counts and failures. Never call a timed-out or partial command
  green. If `just lint` or `just check` modifies a file, inspect it, include it
  in the appropriate code/test commit, and rerun the affected gate until clean.

- [ ] **Step 2: Run real classic and streaming acceptance.**

  On a disposable DB and loopback server, run `just services`,
  `just run-server`, and `just run-robot`. Test once with
  `ROBOT_STREAMING=false` for the full table. Then enable streaming only for
  deterministic, ambiguous, and protected cases; the generic streaming audio
  blocker belongs to C6 and cannot fail C5:

  | Spoken request | Required evidence |
  |---|---|
  | `Me dice la fecha actual.` | literal STT recorded; correct local date; audible; `llm=0` |
  | `¿Qué día es hoy?` | correct local date; audible; `llm=0` |
  | `¿Qué día soy?` | fixed clarification; audible; `llm=0` |
  | `¿Qué vía es hoy?` | fixed clarification; audible; `llm=0` |
  | `¿Cómo se llaman mis hijos?` | non-disclosing denial; audible; `llm=0` |
  | `Hola, Iroko.` | classic only: generic local LLM response; audible |

  If STT emits another phrase, record it literally and classify the case as a
  failure or new supervised sample; do not reinterpret it as a pass.

- [ ] **Step 3: Update evidence and commit.**

  Mark C5 implemented only after automated gates, independent review, and the
  scoped C5 real rerun pass.
  Keep P0 open for C6, C7, and the combined final acceptance.

  ```powershell
  git add docs/architecture/current-state.md docs/architecture/p0-runtime-policy-audit.md docs/plans/open/0014-p0-runtime-policy-hardening-design.md docs/plans/README.md docs/runbooks/p0-runtime-acceptance.md docs/plans/open/0021-p0-typed-intent-resolution.md
  git commit -m "docs(p0): record C5 verification"
  ```

  Then run:

  ```powershell
  uv run pre-commit run --files docs/architecture/current-state.md docs/architecture/p0-runtime-policy-audit.md docs/plans/open/0014-p0-runtime-policy-hardening-design.md docs/plans/README.md docs/runbooks/p0-runtime-acceptance.md docs/plans/open/0021-p0-typed-intent-resolution.md
  git diff --check
  git status --short
  ```

  The final status must be clean after the evidence
  commit; any hook modification requires inspection, a follow-up commit, and a
  rerun.

## Rollback and Stop Conditions

- Rollback is code-only: revert the C5 commits; there is no migration or data
  mutation.
- Stop for a new decision if correct routing requires probabilistic/fuzzy/LLM
  classification, dynamic corpus writes, a new `InformationNeed` outside C5,
  an API change, or policy weakening.
- A new observed STT phrase is evidence for review, not permission for runtime
  self-learning.

## Completion Criteria

- The resolver corpus, precedence, privacy, and immutability tests pass.
- Classic and streaming observed date/ambiguity phrases are deterministic and
  audible with `llm=0`.
- Protected household/birth collisions deny before legacy, memory, and LLM.
- Generic conversation still reaches the existing local LLM path.
- Full gates and real C5 acceptance are recorded.
- C6/C7 remain untouched and P0 remains open.

## Execution Evidence

- RED resolver and route commands: not run.
- Focused GREEN commands and counts: not run.
- Repository gates: not run.
- Independent review: pending implementation.
- Classic operator evidence: pending implementation.
- Streaming deterministic/protected evidence: pending implementation.
- Final commit and clean status: pending implementation.
