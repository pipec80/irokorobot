# 0074 — CM-5a: the profile card and the explicit «what do you know about me»

> **Status:** `Draft` (outline, 2026-10-28). Not `Ready`, not `NOW`: it is neither executable nor
> authorization. It becomes executable only after [ADR 0026](../../adr/0026-owner-profile-card-and-the-read-side-of-memory.md)
> is read and accepted by Pipec, the roadmap amendment of the same change is merged, and queue rule
> 4 is applied (re-audit the tasks below against the merged code and rewrite them in the format of
> [Plan 0073](../completed/0073-local-admin-crud.md), with exact signatures and RED tests, before
> any code). Pipec's rules win over any skill: one plain branch from `main`, never a worktree,
> subagents only if Pipec asks, one commit per task, every test seen RED for the stated reason
> first, the processes started by Pipec, never by the agent.

**Goal.** For the first time the robot reads back what it holds about the person it is talking to:
a small **card** (preferred name, form of address, tastes) is in the prompt on every identified
generic turn, and the question «¿qué sabes de mí?» is answered by the controller with a fixed
template. Nothing sensitive is in the card, the voice is not consulted, and a stranger learns
nothing. The language model is not asked to decide anything about memory.

**Why this first.** It is the smallest slice that makes Iroko *feel* like it remembers, it needs no
new table and no model, and it unblocks the rest of CM-5 without waiting for episodes (ADR 0026
decision 1). It is the milestone «se acuerda de mí» of the closing plan of conversational memory.

## Required reading (when it is rewritten)

ADR 0026; ADR 0019 §3 and §6; ADR 0020 §1, §4 and §7; ADR 0021 decisions 3 and 13;
[`seed-data-pool.md`](../../architecture/seed-data-pool.md); `memory/candidate_policy.py` (the
pattern *evaluate, audit, then act*); `text_turn.prepare_text_turn`; `characters/__init__.py`
(`_MEMORY_DISCIPLINE`, `_format_memory_block`); `cognition/intent_resolution.py` and
`cognition/controller.py` (how `MEMORY_ANSWER` is resolved and injected).

## Outline of tasks (to be detailed at promotion)

- **Task 0 — Re-audit.** Confirm on `main` what ADR 0026 *Context* claims (no personal reader, the
  name written by `_format_memory_block`, one caller of the read capability). Stop and report if
  evidence contradicts it.
- **Task 1 — The card, pure.** `memory/profile_card.py`: the closed allow-list (`preferred_name`,
  `address_form`, `likes`, `dislikes`, `prefers`), the caps (600 characters, 12 tastes), the order
  and a renderer with no entity name, id or role. Tests: the allow-list is closed; the cap and the
  order; a property test that no person identifier appears in the output.
- **Task 2 — The reader.** One function in the V4 repository (the only place with SQL on those
  tables; an architecture guard already enforces it) that returns the owner's active `personal` /
  `normal` rows of the allow-list and nothing else. Tests: a row of another sensitivity, another
  visibility, another person or a revoked lifecycle never comes back.
- **Task 3 — Policy and audit.** `authorize_card_read(actor, now, correlation_id)`: evaluates
  `read_personal_conversation_memory` for the person's own data, writes one audit row **before**
  the effect and denies if the audit fails, requires the kill-switch and an identified actor at
  `basic`. A token-free face actor is enough; the voice composite is not required (the difference
  from `candidate_policy`). Tests: allowed, denied, audit failure, switch off.
- **Task 4 — The prompt.** `PreparedTextTurn` carries the rendered card; both prompt builders
  (`llm.py`, `llm_streaming.py`) place it; `_MEMORY_DISCIPLINE` names it as a source; with the
  switch off the prompt is byte-identical to today's. Tests: classic/stream parity, a suspended
  session gets no card, the language rule is still the last block.
- **Task 5 — The explicit question.** `InformationNeed.PROFILE_SUMMARY`, a pure rule for «¿qué
  sabes de mí?» / «¿qué te he contado?», a controller branch with an injected collaborator
  (present only on the routes that resolve a speaker), a fixed template, a fixed empty-card
  phrase and the existing generic denial for an unidentified speaker. Tests: the owner hears the
  list, a stranger hears the denial, a non-matching sentence is the ordinary turn.
- **Task 6 — Guards and the matrix.** The owner → stranger matrix gains the card; architecture
  guards: the card module is the only caller of the reader, nothing outside it names the allow-list,
  no prompt builder interpolates `entity.name`.
- **Task 7 — Truth, settings and acceptance.** `PROFILE_CARD_ENABLED` in `settings.py` and
  `.env.example`, the operator manual, `current-state.md` and its diagram, the roadmap rows, the
  plan indexes. `just gate`. **Acceptance by Pipec on real hardware** (outcomes only, never the
  values): (1) after a confirmed taste, «¿qué sabes de mí?» lists it; (2) a reply uses the
  preferred name; (3) a second face in frame gets no card; (4) an unknown speaker gets the denial,
  not the list; (5) the switch off behaves as before; (6) the median latency added by the card is
  recorded; (7) `usted` is tried once.

## Non-goals

No episodes, no diary, no search, no embeddings, no summaries (CM-4, CM-5b). No sensitive or pool
read, no «¿estás con alguien?», no liveness (ADR 0026 decision 6). No correcting or forgetting
(CM-6). No change to the writer, the policy table, the wire, the robot or the schema (no
migration). No retirement of `build_context` or the `memories` table. No greeting first, no
reminders.

## Verification

`MEMORY_ENABLED=false uv run pytest` on the CI selection; `just gate`; `ruff` and `mypy`/`pyright`
over the whole project; `uv run python scripts/check_reserved_terms.py`; every relative link of
the changed documents resolves. Hardware acceptance as in Task 7.

## Exit criteria

The card is read on identified turns with the switch on and never otherwise; nothing above
`normal` or outside the allow-list reaches a prompt; no person identifier is in any prompt; the
explicit question is answered deterministically and a stranger gets the denial; the acceptance of
Task 7 is recorded; ADR 0026 moves to `Accepted`.

## Open points for the rewrite

Where the card sits in the prompt relative to the persona and the language rule; whether the audit
row per turn should become one per session if it grows; how `address_form = usted` is worded to the
model; whether `/chat` should read the card for a token-bearing speaker (ADR 0026 decision 3 says
yes; confirm against the bearer limit of ADR 0008 when detailing).
