# The closing path and the path to the MVP, as of 2026-11-10

> **Status:** Preserved, non-authoritative context. On 2026-11-11 Pipec merged these two tables
> into one path to the finish line, in the
> [cognitive roadmap](../../roadmap/cognitive-roadmap.md#closing-path-of-conversational-memory).
> Older documents that cite «step N of the closing path» or «step N of the path to the MVP» refer
> to the numbers below; the current table keeps the first as its *Older step* column.

Decided by Pipec on 2026-10-30, after CM-4 closed, to finish memory without overbuilding it. This
order governs these rows; the numbers of the table stay as they were, so a reference to a row keeps
working. Queue rule 6 applies: rows are combined, and no outcome is removed.

| Step | Delivery | Rows | Size |
|---:|---|---|---|
| 1 | The household protection answers requests, not mentions (**closed 2026-11-02**) | The `—` row before row 9 | Small |
| 2 | **Block A, «it remembers»:** recall what I told you (search over the diary, dates, a fixed «no me acuerdo») and the `normal` relatives of the alta by voice — [ADR 0028](../../adr/0028-recall-what-the-owner-told.md) (**closed 2026-11-04**, Plan 0078) | Row 9 (CM-5b + R3) | Medium |
| 3 | **Block B, «it knows who is listening»:** the first sensitive read by voice (health, address, birthdays, the `SECURITY` datum) by levels, the replay decision, a silent camera check of who is listening and never keeping a spoken secret's value — [ADR 0029](../../adr/0029-it-knows-who-is-listening.md) (**`Accepted` 2026-11-06**), one plan: [0079](../../plans/completed/0079-block-b-sensitive-read-and-spoken-secrets.md) (**closed 2026-11-06**, accepted on hardware 10 of 10, [record](../../evals/0079-sensitive-read-acceptance.md)). `lives_in` and «no menciones X» by voice left the block (ADR 0029 decision 6); keeping a household secret with authorization and answering in company go to ADR 0030, written after CM-7 + PC-5 (decision 15), and recalling medical conversation units to a row of its own (decision 21, below) | The sensitive read of row 9; row 7b (emptied) | Medium |
| 4 | **Block C, «it corrects and forgets»:** the database hygiene first (C1, with the engine's guard test, its integrity checks and the measured SQLite tuning of [ADR 0031](../../adr/0031-the-memory-engine-boundary.md)), then correct and forget (C2) — ADR 0032 | Row 10 (CM-6); the database-hygiene row | Medium to large |
| 5 | **Block D, the final acceptance:** memory first, integrated after, on the home server (the deployment of ADR 0033 comes first) | Row 11–12 (CM-7 + PC-5) | Medium |

Regrouped into blocks on 2026-11-03 (Pipec, in the design of ADR 0028): each block is one ADR with
one or two small plans, the order does not change, and nothing is removed. The sensitive read,
liveness and «¿estás con alguien?» had no step (ADR 0026 decision 6 tied them to «the plan that opens
the first sensitive read») although CM-7 needs a `SECURITY` read at `strong`; they now belong to
block B.

- **CM-5b + R3.** Both search the same thing: without documents, R3's lexical and hybrid search is
  how the diary is searched, so it no longer waits for R2.
- **CM-7 + PC-5.** One acceptance with two parts in a fixed order. PC-5 builds no memory: it proves
  on the real path what the earlier steps built.
- **R2 leaves the path.** Memory does not need documents, so R2 is now
  [conditional](../../roadmap/cognitive-roadmap.md#cross-cutting-gates-and-conditional-work) and reuses the search of step 2 if it
  opens.
- **The generic prompt reads no household store** ([guardrails](../../architecture/implementation-guardrails.md),
  Plan 0077 D-21). Step 1 rests on it: a turn routed to the model by mistake can invent and
  cannot reveal a stored value. Steps 2 to 5 that add household data to that prompt first make
  the household rule broad again.

After the path the queue goes on as before: P2.1, P2.3, P2.4, P3, and then P4.2.

**The memory MVP Pipec wants before any electronics (2026-11-05).** The test is a conversation
on the laptop body in which the robot answers, coherently and without inventing, «¿quiénes son
mis hijos?», «¿cuál es el nombre de mi papá?» and «… de mi mamá?», «¿qué hice ayer?», «¿qué
hice la semana pasada?» and «¿cuándo fui a la playa?». Checked the same day against the intent
rules of `main` (a throwaway script, no database): the children's question and «¿qué hice
ayer / la semana pasada?» reach the right branch (with `RECALL_ENABLED`); «¿cómo se llama mi
papá?» reaches the relatives template but cannot tell the mother from the father; **«¿cuál es el
nombre de mi papá/mamá?» takes the protected «todavía no está conectada» answer, and «¿cuándo
fui a la playa?» is no recall cue at all, so it reaches the model, which holds no memory and can
invent**. The *MVP recall phrasings* item (now under *Closed foundations*) owned those three gaps; how much the robot can
recall also depends on how often the owner's voice verifies (35.5 % of real turns, Plan 0075),
which is the row *Voice calibration, short turns and the remaining biometric measurements*. Both are small and come before
step 5, so that the final acceptance runs on the MVP questions. **Update, 2026-11-10:** Plan 0080
closed the three gaps and the questions pass on real hardware (the day questions failed twice on
speech-to-text, not on the grammar); the voice calibration and the prompt are left before step 5.

**The path to the MVP and the final acceptance (Pipec, 2026-11-06 and 2026-11-09).** Decided in
two planning sessions after Plan 0079 closed. It orders the work that is left and does not remove
a row; plan numbers after 0080 are not reserved.

| # | Delivery | Size | ADR |
|---:|---|---|---|
| 1 | **Done: Plan 0080, the memory MVP (closed 2026-11-10, accepted on real hardware in two rounds, [record](../../evals/0080-mvp-recall-acceptance.md)).** Task 0 was a short real-speech session (about 20 of Pipec's phrases, outcomes only) that sorts each failure into speech-to-text, language understanding, retrieval or generation and feeds every closed grammar; then «¿cuál es el nombre de mi papá/mamá?», «¿cuándo fui …?» and the mother told from the father in the alta; it also fixes the recall delivery race of [ADR 0031](../../adr/0031-the-memory-engine-boundary.md) *Context* item 8 (the text is read without re-applying owner, sensitivity and expiry) | Medium (done) | Notes in ADR 0028, ADR 0024 and `seed-data-pool.md`; no migration and no new ADR |
| 2 | [ADR 0031](../../adr/0031-the-memory-engine-boundary.md), the memory engine boundary (documentation only) — **Accepted 2026-11-09** | Small | 0031 |
| 3 | Voice calibration at enrolment, as a tool (a short script, a level and distance check), with no new threshold | Small to medium | Note in ADR 0024 |
| 4 | The prompt that shows through the reply, the cold greeting and `usted`: one cross-cutting row, *The prompt, the card and the model's own answers*, holds the evidence and Pipec's proposal of 2026-11-10 (tastes only when relevant and never in the greeting; a greeting may pick up an open topic of the last one or two days, which needs remembering pending topics: a new design, not built) | Small | — |
| 5 | Block C: C1 hygiene, the engine's guard test and health checks, the embedding-model guard (no cross-model comparison, a verifiable re-index), the measured SQLite tuning; C2 CM-6. Forgetting one ordinary memory needs the owner's face and a closed spoken verb (the voice adds, it is not required); a sensitive or security memory, or «olvida todo», needs the PIN in `iroko-admin`. That supersedes ADR 0026 decision 4 and the forget part of ADR 0019, explicitly, in ADR 0032, which also decides the retention of memories for years | Medium to large | 0032 |
| 6 | The home-server deployment: the server in a container on the laptop, the robot as a separate client, `/health` reporting Ollama, an orderly shutdown. It amends ADR 0013 (LAN) and lifts Docker from the project's «future» list | Medium | 0033 |
| 7 | Block D: dataset v4 with LongMemEval's dimensions and an injected clock, a scale test, CM-7 + PC-5 measured in the container; the memory switches become default-on when it closes | Medium | — |
| 8 | After the final acceptance: extracting the memory engine (ADR 0031 decision 11), documents R2 (Markdown, text and PDF with text; ADR 0034), ADR 0030 (after CM-7 + PC-5), R4 (OCR) only by measurement | Medium each | 0034, 0030 |

ADR 0030 stays reserved for ADR 0029 decision 15, written after CM-7 + PC-5.
