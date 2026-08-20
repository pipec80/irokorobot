# P0-C4 — Bounded protected-request recognition

> **Status:** Implemented in the current feature branch — automated gates
> green; operator acceptance pending.
> **Scope:** deterministic text classification at the controller boundary. This
> does not authorize data, identify speakers, retrieve memory, or add an LLM
> classifier.

## Objective

Close the confirmed wording gap in the current public-request classifier.
Plausible requests for household relationships, spouses, parents, children, or
birth information must enter the existing protected policy path before legacy
generation. The known STT corruption `"¿Qué día soy?"` must get a neutral
clarification rather than either an incorrect date claim or an LLM prompt.

## Evidence revalidated

- The prior classifier used a small closed set that missed `esposa` and
  birth-date wording such as `nació`; C4 expands only the documented terms.
- The static P0 runtime audit records these as confirmed coverage gaps; it also
  records the reported STT output `"¿Qué día soy?"` as a case that must not
  fall into legacy generation.
- Existing protected handling is correct once classification reaches it:
  deterministic policy decision, safe audit, non-disclosing response, and no
  legacy delegate for unknown public actors.

## Bounded vocabulary and behavior

The following normalized substrings are protected household requests in P0:

| Category | Terms/forms |
| --- | --- |
| Children/family | `hijo`, `hija`, `familia` |
| Household relationships | `padre`, `madre`, `papa`, `mama`, `hermano`, `pareja`, `esposa`, `esposo`, `marido`, `mujer`, `abuelo`, `abuela`, `tio`, `tia`, `primo`, `prima` |
| Preferences | `preferencia`, `le gusta` |
| Birth information | `nacio`, `nacimiento` |

Normalization stays case- and accent-insensitive. This is intentionally a
closed, conservative P0 guard, not an attempt to understand all Spanish. A
message containing a term may be denied rather than sent to a general LLM
turn; this is preferable to disclosure while public identity is UNKNOWN.

`"que dia soy"` is a documented ambiguous STT form. It receives the fixed
clarification:

> `No entendí si preguntas por la fecha actual o por información personal. ¿Podrías reformularlo?`

It is not treated as the date, not sent to legacy generation, and does not
retrieve or audit household data.

## Invariants

1. The classifier remains deterministic local Python; no model/classifier is
   consulted for authorization.
2. Protected classification happens before current-date and age routing.
3. Every protected variant retains authorization-before-retrieval and a safe
   audit outcome; it must not call the legacy text path for an UNKNOWN actor.
4. Strict normal date forms, explicit ISO-date age calculations, and ordinary
   unrelated conversation keep their current behavior.
5. No personal name is a classifier key and no identity is inferred from text.

## TDD slices

### 1. RED — variants and ambiguity

Add parametrized controller tests for:

- `¿Cómo se llama mi esposa?`
- `¿Cuándo nació Máximo?`
- `¿Quién es mi mamá?`
- `¿Qué preferencias tiene mi hija?`

Each must produce an `UNAUTHORIZED` plan for the public actor, audit once, and
never await legacy generation. Add a test for `¿Qué día soy?` expecting the
fixed clarification, no audit, and no legacy generation. Retain a generic
conversation control test to prove ordinary conversation still defers.

### 2. GREEN — one explicit information need

Add a narrowly named ambiguous-date information need and its fixed
deterministic `ResponsePlan`. Expand only the documented constant vocabulary,
then order classification as:

```text
own child tools -> protected household/birth -> ambiguous date -> exact date -> age -> relation -> generic
```

No regex/NLU framework, fuzzy matching, model call, database lookup, or
identity lookup is permitted.

### 3. Route regression

Run existing classic, stream, and visual protected-denial tests. They must all
use the same controller classification and remain free of legacy generation
for protected text.

## Verification

```powershell
uv run pytest -n0 tests/unit/test_cognitive_controller.py tests/integration/test_transcribe_memory.py tests/integration/test_transcribe_stream.py tests/integration/test_vision_dialog.py -v
just lint
just typecheck
just test
just audit
just check
git diff --check
```

## Rollback

The change is classifier-only and data-free. Revert the C4 commit if the
bounded vocabulary causes a demonstrable public API regression; no schema or
stored data requires repair.

## Execution evidence

Observed on 2026-08-14 before merge or operator-acceptance claims:

- **RED:** `esposa`, `nació`, `mamá`, and `qué día soy` reached the legacy
  path. The already-covered `hija` preference case passed, demonstrating the
  original vocabulary was incomplete rather than universally broken.
- **GREEN:** the controller suite passed `16` tests, including the documented
  protected forms and ambiguity clarification. Cross-route controller, classic
  audio, streaming, and visual tests passed `55` cases; the final full suite
  passed `589` tests.
- **Static gates:** final `just lint`, `just typecheck`, `just audit`, and
  `just check` passed. `git diff --check` passed.

Still required: record literal real STT transcripts in the combined P0-C
operator run. The vocabulary is deliberately bounded and is not a general
Spanish authorization model.
