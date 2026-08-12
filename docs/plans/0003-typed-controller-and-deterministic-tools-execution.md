# Plan 0003 — Typed controller and deterministic tools: execution runbook

**Status:** Complete — merged to `main` as `a80dd2d` through PR #37, after the
P0-S2 baseline `5f1971c`.

**Prerequisites:** Plans 0002, 0002a, 0002b, and 0002c are Complete with
recorded validation. This runbook and its canonical plan were re-read against
the current chat router, `text_turn`, `CognitiveEvent`, P0.2 tests, P0-S
outcomes, and Ollama-only provider boundary.

## Outcome

`POST /chat` creates a typed `CognitiveEvent` and delegates it to a small
`CognitiveController`. It answers current-date and explicit ISO birth-date age
questions through deterministic Python, without an LLM or memory read. Other
safe text continues through the existing `process_text_turn` behavior.

The external chat request and response models remain compatible. This is an
adapter-first migration, not a rewrite.

## Deliberate boundary

This PR does not infer identity, inspect relationships, retrieve family facts,
authorize household data, or allow an LLM to choose a tool. Clearly protected
household requests return a safe `unauthorized`/unavailable response and never
enter legacy memory retrieval. Those capabilities belong to P0.4 and P0.5.

## Files and ownership

| File | Change |
|---|---|
| `server/src/server/cognition/response_plan.py` | Typed response-plan, source, and information-need contracts. |
| `server/src/server/cognition/calendar_tools.py` | Pure `calculate_age` and current-date helpers. |
| `server/src/server/cognition/controller.py` | Small orchestrator with explicit branch ordering. |
| `server/src/server/cognition/__init__.py` | Export only the necessary public cognition contracts. |
| `server/src/server/routers/chat.py` | Construct the event and adapt `ResponsePlan` to unchanged route response. |
| `tests/unit/test_response_plan.py` | Validate the response-plan contract. |
| `tests/unit/test_calendar_tools.py` | Test date/age calculation as pure deterministic logic. |
| `tests/unit/test_cognitive_controller.py` | Test selection, safety gates, and legacy delegation. |
| `tests/integration/test_chat_endpoint.py` | Test `/chat` compatibility and observable deterministic behavior. |

Do not modify `text_turn.py`, database schema, memory repositories, robot
client, vision routes, or prompt templates unless a re-audit demonstrates a
minimal compatibility fix. That needs a documented plan amendment.

## Contracts

Keep types beside the existing `server.cognition.models` vocabulary. Do not add
a tool framework or registry in this PR. Two closed deterministic tools do not
justify a registration abstraction; reconsider only when a later plan has
multiple tools that need shared metadata or dispatch.

```python
class TextTurnPayload(BaseModel):
    message: str
    conversation_id: str | None


class InformationNeed(StrEnum):
    GENERIC_CONVERSATION = "generic_conversation"
    CURRENT_DATE = "current_date"
    EXPLICIT_BIRTH_DATE_AGE = "explicit_birth_date_age"
    PROTECTED_HOUSEHOLD = "protected_household"


class CognitiveController:
    async def handle(
        self,
        event: CognitiveEvent[TextTurnPayload],
    ) -> ResponsePlan: ...
```

`ResponsePlan` carries a typed `KnowledgeStatus`, text, source (deterministic
or legacy), and response metadata needed by the route adapter. It does not
expose raw memory or prompt text. If `CognitiveEvent` is non-generic today, use
composition rather than changing a stable contract merely for this work.

## Classification and branch ordering

Only narrow patterns are in scope:

1. Protected household requests (children, names of children, preferences, or
   family facts) return a non-disclosing result before memory or LLM calls.
2. A direct current-date request calls an injected date provider.
3. A request with an explicit ISO `YYYY-MM-DD` birth date and an age question
   parses the date and calls `calculate_age`.
4. Every other request delegates to the existing `process_text_turn` path.

Do not parse names, resolve people, derive age from a stored static fact, or
accept ambiguous date formats. Malformed, future, or insufficient dates return
`unknown` with a clarification; they are never guessed.

## TDD execution sequence

1. Re-audit Git, route models, `CognitiveEvent`, `process_text_turn`, and chat
   tests; confirm Plan 0002a completion evidence.
2. Add pure calendar tests and observe Red before adding the functions.
3. Implement date helpers with an injected `today` boundary; do not read the
   system clock directly in the core.
4. Add controller branch tests using a fake legacy turn processor; observe Red.
5. Implement the smallest controller. Protected requests must short-circuit
   before the fake memory/LLM delegate could be called.
6. Add the route adapter and chat integration coverage.
7. Add P0.2 regression tests for unknown identity and generic conversation.
8. Complete static analysis and full test suite, then update completion record.

## Required behavior tests

| Case | Expected result |
|---|---|
| `today=2026-08-11`, birth date `2017-12-29` | Exact deterministic age. |
| Birthday today / day before birthday | Correct boundary age. |
| Leap-day birth date | Defined and tested leap-year behavior. |
| Future, malformed, or ambiguous date | `unknown`, never a guessed age. |
| “What date is it?” | Deterministic result; no legacy/LLM call. |
| Guest asks private family fact | `unauthorized`; no memory/LLM call. |
| Unknown speaker asks generic non-private question | Existing P0.2 isolation behavior. |
| Generic safe request | Existing response schema and TTS fields retained. |

The supported phrase patterns must remain deliberately narrow and documented.
They are not a substitute for P0.4/P0.5 data and authorization work.

## Acceptance criteria

- Every chat request has a fresh event ID, timestamp, source, and unknown
  active-person context unless a future approved adapter provides evidence.
- Deterministic date/age branches never call LLM, memory repository, or prompt
  construction code.
- Protected household intents fail closed before legacy retrieval.
- ISO calculation is correct at birthday boundaries; invalid input returns
  uncertainty.
- `/chat` request and response JSON is backward compatible.
- Controller core depends on neither FastAPI, SQLite, Ollama, nor Anthropic and
  is testable with fakes.
- No third-party dependency is added.

## Validation gates

```powershell
just lint
just typecheck
just test
just audit
```

Run the new unit tests and chat integration test first, recording Red/Green.
Then run the commands above, `git diff --check`, and the P0.2 regression subset.
Do not call the full suite green unless `just test` completes.

## Demonstration

With a controlled clock, submit a chat request containing an ISO birth date and
verify the exact age. Submit a current-date request and verify the same provider
is used. Submit a private-family query as an unknown person and verify a safe
response without retrieval. Finally, submit a generic request and verify the
existing response envelope is unchanged.

## Completion record

Merge commit: `a80dd2d` (PR #37).

The recorded RED/GREEN sequence is in the canonical Plan 0003 completion
evidence. Final implementation gates passed: `just lint`, `just typecheck`
(`mypy` 67 source files and `pyright` 0 errors), final `just test` (514 passed
in 36.25s), `just audit`, and a clean `just check`. The controller remains a
`/chat`-only adapter; no database, policy, audio, robot, vision, provider, or
dependency scope amendment occurred.

No real Ollama request or hardware acceptance was run. The next candidate is
P0.4 relational integrity/cardinality; it remains Draft until separately
revalidated and promoted.
