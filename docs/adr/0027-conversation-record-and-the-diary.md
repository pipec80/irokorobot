# 0027 — Keep the whole conversation as a record, and build the diary from the owner's part of it

- **Status:** Proposed (2026-10-28). Written after Pipec reshaped the diary of CM-4 in the same day's
  conversation (see *Pipec's decisions and where they land*). It becomes `Accepted` when the first plan
  that implements it closes. Every decision below is the author's recommendation unless it says
  *Confirmed by Pipec*.
- **Date:** 2026-10-28
- **Builds on:** [ADR 0019](0019-personal-memory-capabilities.md),
  [ADR 0020](0020-authorized-actor-in-the-conversation.md),
  [ADR 0021](0021-memory-candidates-and-the-canonical-writer.md),
  [ADR 0024](0024-seed-load-senses-secrets-and-channels.md),
  [ADR 0025](0025-remote-administration-backup-updates-and-telemetry.md),
  [ADR 0026](0026-owner-profile-card-and-the-read-side-of-memory.md)
- **Amends:** the diary rule of Pipec's decision 3 recorded in ADR 0026 («summaries only, 90 days, only
  turns whose voice was verified»), which this ADR replaces (decisions 1 to 3); [ADR 0025](0025-remote-administration-backup-updates-and-telemetry.md)
  decision 5, whose open question («storing conversation text is a decision of its own, taken with CM-4»)
  it answers; [ADR 0026](0026-owner-profile-card-and-the-read-side-of-memory.md) decision 8 (the legacy
  `build_context` path is retired, decision 9).
- **Implemented by:** [Plan 0076](../plans/open/0076-cm4-conversation-record-and-diary.md) (code on 2026-10-29; `Accepted` after its hardware acceptance). See *Implementation notes*.

## Context

CM-4 was designed as a diary: one short summary per conversation, written only from turns whose voice
was verified, kept 90 days, with no transcript. Pipec's objection on 2026-10-28 is that this keeps too
little and decides too early. The goal is a robot that remembers what its owner tells it, and nearly
anything the owner says can matter later; a summary is a lossy copy that cannot be recomputed once the
text is gone, and a better model or a better rule tomorrow would have nothing to read.

What holds today (verified in code on `main` at `d1a5abe`, 2026-10-28):

1. A face-identified person has a short-term session in process memory (3000 characters, 180 s of
   idle, 20 messages); an unknown or ambiguous speaker suspends it and nothing is kept
   (ADR 0020). Two faces in frame suspend it too.
2. Nothing is stored of a conversation. The facts that exist are confirmed tastes (CM-3a), the loaded
   pool (Step 0) and what the card reads back (CM-5a). The legacy `memories` table and `build_context`
   are unreachable and nothing writes to them.
3. Speech-to-text transcribes every sound the microphone gives it. It does not tell speakers apart. The
   voice check (ADR 0016) compares one clip with the owner; a short clip often comes back `unknown`
   (Pipec's hardware run of 2026-10-28: 1.9 s `unknown`, 1.6 s `verified`).
4. The silence that ends a clip is the robot's (Silero, 1.2 s). A pause inside a thought splits it in
   two clips; that is a capture problem with its own plan, not a memory one.
5. ADR 0025 decision 5 allows conversation text to be stored only if it is local, never leaves the
   device, has a consent from the alta, a retention window, can be deleted and sits under the disk
   encryption floor. ADR 0024 decision 3 keeps raw audio and frames out of storage.
6. Pipec's rule for who counts: only the owner's voice makes something memory; a stranger's words are
   not a contribution to the owner's memory.

## Decision

### 1. Two layers: the record is the archive, memory is derived from it

The **conversation record** is the archive: the text of what was heard and said, kept as it came.
**Memory** (the diary, the candidates for facts, later the search index) is computed from the record by
background jobs and can be recomputed. The record is the source of truth; nothing derived is.

### 2. Everything is recorded; only the owner's part feeds memory

Every conversation is recorded as text, including what an unidentified person said, because the
speech-to-text transcribes everything and the record is meant to be complete. A record has a flag:
**eligible** when at least one of its turns was verified as the owner's voice, **not eligible** when none
was. Inside an eligible record each turn also carries its own verdict.

Memory reads **only** the owner's verified turns and the robot's replies to them. A visitor's words, a
mixed clip, a short clip that came back `unknown`, or a record with no verified turn at all stay in the
record and are **never** summarized, turned into candidates, indexed or read by any memory path. A
conversation held only with strangers is therefore archived but contributes nothing. *Confirmed by
Pipec (2026-10-28).*

### 3. How a turn becomes the owner's

A turn is the owner's when the voice of its own clip verifies against the owner (the check the
candidate path already runs in the background, with the clip held only in memory). The fraction of
real turns that pass is **measured first**, in the implementing plan, with Pipec's own conversations. If
it is too low to be useful, the plan proposes a rule per conversation (for example, most clips) before
anything is built on the per-turn rule. *Measured on 2026-10-29 by [Plan 0075](../plans/completed/0075-cm4-pre-measurement.md)
([record](../evals/0075-cm4-pre-measurement.md)): 22 of 62 real turns verified (35.5 %), driven by clip
duration (over 3 s 58 %, under 1.5 s 0 %; short answers 7 %, questions 0 %). A per-conversation
«most clips» rule is fragile (50 % in one conversation, 18 % in the other); **Confirmed by Pipec
(2026-10-29): the rule is per turn.** Lowering the 1.5 s floor recovers nothing (0 of 12 would match).*
Face alone never makes a turn the owner's for memory, because a
photograph would then write into the owner's diary.

### 4. A conversation ends by silence, and a long one is cut into segments

A conversation ends after the idle time of the session (180 s, a setting) and, at most, after a maximum
length (a setting). A longer conversation becomes consecutive **segments**, each a record of its own
linked to the previous one, so no record is huge and each is summarized from its own raw text (never a
summary of summaries). A pause shorter than the idle time continues the same record: stopping and
resuming a thought stays in one place. How the robot decides a clip has ended, and how fragments of one
sentence are joined, is the turn-taking plan, separate from this ADR; the record does not depend on it.

### 5. Format, size and how to read it

Plain text, never audio or frames. One database row per segment with its turns as JSON (who, text,
time, the voice verdict), in the same SQLite file as the rest, so retention, deletion, encryption and
backup are the ones the database already has. A segment is capped (turns and bytes, both settings) so a
file stays readable; a local space limit (a setting) purges the not-eligible records first and then the
oldest. Reading is by an administration command that writes a readable file per conversation, under the
owner's PIN; no voice path and no prompt ever reads a record.

### 6. Retention is configurable, with two clocks

Two settings: how long an eligible record is kept and how long a not-eligible one is kept. Proposed
defaults: **one year** and **30 days**. The stranger-only text exists for completeness and for the
owner's own audit; it has no use for memory, so it expires sooner. A purge job reuses the existing
retention loop. *Configurable: confirmed by Pipec; the defaults are the author's proposal.*

### 7. Consent, notice and the switch

The alta records a new consent, `conversation_storage`, next to the biometric ones, and the notice
states that **what anyone who speaks near the robot says is transcribed and stored**. Without the
consent nothing is recorded. A kill-switch, `CONVERSATION_RECORD_ENABLED`, is off in the code and on in
a delivered robot, like `PROFILE_CARD_ENABLED`. *Confirmed by Pipec.*

### 8. What memory builds from the record

After a record closes, one background job at a time, with the budget of the extraction job:

- an **episode** (the diary): a short summary of the owner's part, with owner, visibility `personal`,
  sensitivity from a classifier, `source_record_id` and the same expiry as its record;
- **candidates** for facts (ADR 0021): the job proposes, never writes (ADR 0025 decision 5), and the
  owner confirms by voice as today.

Every derived row names its source record, so it can be recomputed and so CM-6 can delete the
cascade. The summary is read back only on a recall cue and only by the identified owner (CM-5b); this
ADR does not open that read.

### 9. Deleting, and the legacy path

Deleting a record deletes every row derived from it; forgetting a single fact does not delete the
record unless the owner asks. The voice commands for this are CM-6. The legacy path, `build_context`,
the `MANUAL` gate and the `memories` table, is **retired** in the implementing plan after counting what
the table still holds; it is not patched.

### 10. What stays in the record, said honestly

Whatever is said aloud is stored as said: a health detail, a name, even a code. Nothing is filtered on
the way in. The mitigations are the ones above: local only, under disk encryption, with a retention
window, deletable, behind the notice and the consent, and never readable by the voice path. The record
is part of the database, so the **encrypted backup** (ADR 0025 decision 6) copies it; whether backups
exclude it is a setting decided in the backup plan. A redaction filter is out of scope.

### 11. Embeddings

Whether the current embedding model suits Spanish is measured with Pipec's phrases before any episode is
indexed (Pipec's decision 6). It changes the index, not the record. *Measured on 2026-10-29 by
[Plan 0075](../plans/completed/0075-cm4-pre-measurement.md) on invented Spanish phrases: `nomic-embed-text`
separates paraphrases from unrelated phrases (ROC-AUC 0.98) and is adequate for the first episodes; two
768-d multilingual drop-ins, `granite-embedding:278m` (185 MB) and `embeddinggemma:300m` (1.1 GB), reach
1.00. A swap re-embeds the whole index, so it is a follow-up in the roadmap, not part of this ADR.*

## Pipec's decisions and where they land

Confirmed on 2026-10-28:

| # | Decision | Where it is written |
|---|---|---|
| 1 | Replace «summaries only, 90 days, only verified turns» by «keep the whole conversation if the owner's voice was detected» | Decisions 1 to 3 |
| 2 | Retention configurable, to be tuned later; text only, files kept small enough to open and read; a space limit is possible | Decisions 5 and 6 |
| 3 | A consent in the alta and a notice that nearby speech is transcribed | Decision 7 |
| 4 | Record everything the speech-to-text hears, but let only the owner's identified part feed memory | Decision 2 |
| 5 | Keep it simple: the owner's voice decides; silences and the end of a session are handled; no speaker separation | Decisions 3 and 4 |

## Not decided here

| Subject | Why not now | Owner |
|---|---|---|
| How a clip ends and how fragments of one sentence are joined | Capture, not memory | A turn-taking plan |
| Recall cues, dates, the fixed «no me acuerdo» and the search | CM-5b | Its plan |
| Correcting and forgetting by voice | CM-6 | Its ADR |
| Several enrolled speakers in one conversation, speaker separation | The family stage (P3) | Its ADR |
| Exact defaults of the caps, the space limit and the job budget | Measured with real conversations | The implementing plan |
| Whether backups exclude the record | The backup plan | ADR 0025's plan |
| The embedding model | Measured first | The implementing plan |

## Alternatives considered

- **Summaries only, no transcript (the previous rule).** Rejected by Pipec: lossy, cannot be recomputed,
  and decides too early what matters.
- **Record only what the owner said.** Simpler to defend, but drops the context of a conversation and
  hides a visitor's words that the owner may later want to audit. The record keeps them apart from memory
  instead.
- **Record the voice (audio).** Rejected: ADR 0024 decision 3 keeps audio out, and text is enough.
- **Separate files per conversation on disk.** Rejected: retention, deletion, encryption and backup would
  each need their own mechanism; one database and a readable export give the same reading.
- **Speaker separation now.** Rejected as over-engineering for the personal stage; a stranger's words
  are archived, not attributed.
- **A language model decides what to remember on every turn.** Rejected for a 3B model (research of
  2026-10-28): costly and lossy; the job proposes candidates and the owner confirms.

## Consequences

### Positive

The robot can come to remember what the owner tells it, not only tastes; nothing is lost to an early
summary, and a better rule or model can reprocess old records; the owner-only rule stays simple (the
voice decides) and strangers never reach memory; one place for retention, deletion and encryption.

### Negative

Raw conversation text is the most sensitive thing the robot holds, so the notice, the encryption floor
and the deletion path stop being optional; a visitor's words are stored (archived, unused); the deletion
cascade of CM-6 gets larger; the backup grows and carries the text; the owner-only rule depends on the
voice check passing often enough, which is a measurement and not a promise; the legal reading of storing
third-party speech (Law 21.719) is still pending advice.

## Test consequences

A record is written only with consent and the switch on; an eligible record has at least one verified
turn and a not-eligible one has none; memory jobs never read a turn without an owner verdict (a property
test over the job's input); a stranger-only conversation produces no episode, candidate or index row; a
segment never exceeds its cap; the purge removes each class at its own age and the derived rows with
their record; no route, prompt or voice answer ever carries record text; the legacy path is gone; a
kill-switch off writes nothing.

## Docs to update

With `Proposed`: the ADR index, the roadmap (the CM-4 row) and the memory map. With `Accepted`:
`current-state.md` and its diagram, the operator manual (the settings, the export, the retention),
`seed-data-pool.md` (the new consent), ADR 0025 (decision 5 answered) and ADR 0026 (decision 8).

## Implementation notes (Plan 0076, 2026-10-29)

Confirmed by Pipec before the plan was written, and how the code reads them:

- **Decision 3, «whose turn».** A turn is the owner's only when the **face** names the owner **and**
  the voice of that clip verifies (the check of the memory candidates, `verify_face_and_voice`).
  Voice alone does not count, so a recording of the owner cannot write into the diary.
- **Decision 8, amended.** The job writes **only the episode**. Candidates keep coming from the live
  path (ADR 0021); every recorded exchange keeps its `correlation_id`, which joins it to that turn's
  candidates and audit rows for CM-6.
- **Decision 7, revocation.** Revoking `conversation_storage` stops the record and deletes every
  record and episode.
- **Decision 9, the legacy path.** Retired completely, including the prompt surface it fed
  (`MemoryContext`, the memory block, the onboarding interview). `vec_memories` is dropped; the
  `memories` table stays **empty and refuses any row**, because four tables still name it in a
  nullable foreign key and SQLite cannot drop such a parent without rebuilding every child. The chat
  evaluations keep their synthetic memory in an evaluation-only model and pass it through the
  profile card slot (Pipec's choice).

The author's calls the plan records (D-5 to D-12): one JSON entry per **exchange**
`{at, heard, said, voice, cid}` written at the moment in a background task; the two voice routes are
recorded (a fixed reply with the speaker the controller resolved, `not_checked` when none), unclear speech, the camera cue, `/vision/respond`,
`/chat` and the memory offer are not; a conversation ends after the session's idle time; caps of 60
exchanges / 64 KiB per segment, 365 / 30 days, 200 MB; the diary is written only while nobody is
talking, under the extraction limiter, and gives up after 3 failures; the consent is a grant row
with the notice version (`docs/legal/conversation-notice-v1.md`), asked at the alta close or with
`iroko-admin`; no policy row for an episode (a derived row); `iroko-admin` operations are audited.

## Review

Revisit when the measurement of verified turns is known, when the first conversations show how large the
records grow, when the legal advice on stored third-party speech arrives, when several enrolled
speakers are in scope (P3), or when the backup plan decides what a backup carries.

## Follow-up

- The measurement of verified turns and of the embedding model is done
  ([Plan 0075](../plans/completed/0075-cm4-pre-measurement.md), 2026-10-29). The implementing plan,
  [Plan 0076](../plans/open/0076-cm4-conversation-record-and-diary.md), is coded (2026-10-29); its
  hardware acceptance moves this ADR to `Accepted`.
- The next free ADR number is 0028.
