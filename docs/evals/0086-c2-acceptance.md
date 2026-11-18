# 0086 — Block C2, correct, archive and delete: acceptance

> **Status:** **accepted 2026-11-18 by Pipec** on real hardware, the four cases of his model of
> forgetting, one sitting, streaming route. Code of
> [Plan 0086](../plans/completed/0086-c2-correct-archive-delete.md) (PR #285, `fac1817`) and the
> three fixes the sitting found (PR #286, #287, #288), under
> [ADR 0039](../adr/0039-c2-the-cheapest-forms-of-correct-archive-and-delete.md) and
> [ADR 0032](../adr/0032-block-c-hygiene-correct-forget-and-years.md) decisions 2 to 6. Pipec
> started the server and the robot, spoke every phrase and typed the PIN; the agent ran every
> backup, `iroko-admin` count and log reading. **Outcomes, counts and the robot's fixed wording
> only:** no value of the database, no household datum and nothing the owner said is recorded
> here; the names were invented canaries.

## Setup

- `pre-0086` backup of the real database (server stopped), opened and checked: integrity ok,
  schema version 20, no foreign-key violation.
- PR #285 merged; the first start ran migration 21 («Schema up-to-date (version 21)»).
- Memory, the conversation record, recall, pending topics and the memory candidates on (the
  settings of the earlier plans).

## Case 2 — a taste that changed

| # | Step | Result |
|---|---|---|
| 1 | A taste stated, offered and confirmed | **Pass** (one voice retry on a short clip, then «Listo, lo guardé.») |
| 2 | «Ya no me gusta …» | **Pass**: «Tenía guardado que te gusta …. ¿Lo cambio? Dime: sí, autorizo.» (`memory.change proposed`) |
| 3 | «Sí, autorizo.» with the face only | **Pass**: «Listo, lo cambié.» (`memory.change correct`, 3.0 s) |
| 4 | «¿Qué sabes de mí?» | **Pass**: the corrected taste is gone |
| 5 | A correction with a new value | **Pass**: the read-back names both, then «Listo, lo cambié.»; the new value shows on the card |

## Case 3 — a refinement, not a correction

| # | Step | Result |
|---|---|---|
| 6 | A taste with its restaurant, offered and confirmed | **Pass**: confirmed against the taste already stored (`already_present`), no duplicate |
| 7 | «… y me gustó más» | **Pass**: an ordinary reply, `candidate.proposal dropped (gate_no_match)`, no read-back |
| 8 | «¿Qué sabes de mí?» | **Pass**: the original taste is still there |

## Case 1 — a plan that did not happen

| # | Step | Result |
|---|---|---|
| 9–10 | A plan for tomorrow, then its cancellation | **Pass**: ordinary replies |
| 11 | «¿Cuándo jugué …?» | **Pass**: «No tengo registrado cuándo fue.» and the plan quoted as told today; never «jugaste» |

## Case 4 — a person the owner wants gone

| # | Step | Result |
|---|---|---|
| 12–13 | Two stories that name the canary, voice verified | **Pass** |
| 14 | «… no quiero saber nunca más de ella.» | **Pass**: «Encontré 2 recuerdos de …», the pronoun resolved |
| 15 | «Sí, autorizo.» (voice `unknown`, face only) | **Pass**: «Listo, lo dejé de lado.» (`memory.change archive`) |
| 16 | «¿Qué te conté de …?» | **Failed, fixed**: the archive request itself had been indexed as a recall unit after the archive and was read back. PR #286: a spoken change is never a memory (RED test first) |
| 14b | The same request heard with a final «s» | **Failed, fixed**: nothing found. PR #287 and #288: a name is tried with and without one final «s» (RED tests first) |
| 14c | Repeated after the fixes | **Pass by design**: the remaining units naming the canary had been raised to `private` by the diary, and a voice change reads and archives `normal` units only, so they are never said by voice either; the robot says «No tengo nada guardado de …» and reveals nothing |
| 18 | `iroko-admin archive list` (PIN) | **Pass**: one group, 2 units, short texts under the PIN only |
| 18b | `iroko-admin archive restore --at …` (PIN, `SI`) | **Pass**: «Recuperado: 2 filas.»; 0 archived afterwards |
| 21 | `iroko-admin forget person --name …` (PIN, `SI`), twice (the second after PR #288) | **Pass**: 16 register lines in all (8 turns, 4 units, 4 episodes), each `seq`, `kind`, `id`, `at` only; 0 units, turns, episodes and topics name the canary; marker 16, nothing waiting; one `delete` audit row applied per command |
| 22 | «¿Qué te conté de …?» after a restart | **Pass for this plan**: nothing of the deleted person was said. The answer was an unrelated story found by meaning alone (distance 0.368 under the 0.43 gate, no lexical hit): a limit of recall, recorded as a follow-up |
| 24 | Restore: a copy taken before the deletion, opened with the current register beside it | **Pass**: the copy held 4 units and 8 turns naming the canary; after the replay, 0; marker 16; `iroko-admin health` «Resultado: sana.» |
| 25 | `iroko-admin health` on the real database; `post-0086` backup | **Pass**: exit 0; the backup (database and register) restored into a copy and opened sane; the copies deleted |

## Automated

CI selection **8397 passed** on the code of PR #285 (baseline 8291 on `main` before the plan);
`pyright`, `mypy`, `ruff`, the format check, the reserved-terms guard and the five GitHub checks
green on #285, #286, #287 and #288. Three read-only reviews (database, security, code and tests)
and the automated security review found one critical defect (a deletion a key refused poisoned the
register and stopped every start) and the important ones; each was fixed with its test first.

## Close

- Accepted by Pipec on 2026-11-18. The `post-0086` backup (the database and its deletion
  register) was opened, restored into a copy and checked: integrity ok, schema version 21; the
  copy was deleted.
- The `pre-0086` backup was deleted after the acceptance.

## Open points, kept for the review of all plans (Pipec, 2026-11-18)

Pipec's rule for the MVP: a wide margin of error; these edges are not fixed now.

- **Speech-to-text variants of a name** beyond one final «s» («Canadia» for «Canaria»), and other
  speakers with another way of speaking: they need real audio of several people.
- **Recall precision for a named person**: with no unit holding the name, recall may answer an
  unrelated story found by meaning alone (ADR 0028's gate).
- **Short clips in a memory offer** ask to repeat because the voice does not verify (known since
  Plan 0068); a correction or an archive needs the face only.
- **«No tengo nada guardado de …» when only `private` rows name the person**: by design (no
  oracle at `basic`); `iroko-admin` reaches them.
