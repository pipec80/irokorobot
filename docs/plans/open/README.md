# Open plan index

> **Status:** Work not yet closed. A plan can be implemented, partially
> implemented, deferred, or only designed and still belong here. Presence in
> this directory does not grant permission to implement.

For daily work do not choose a plan from this directory. Follow the single-WIP
[operational board](../README.md#operational-board): it lists the `NOW` item and every
closed plan with its evidence. The
[personal-companion delivery map](../../roadmap/personal-companion-delivery-map.md) and the
[conversational-memory delivery map](../../roadmap/conversational-memory-delivery-map.md) show the
code, tests, verified gaps and the delivery sequence.

| Plan | Implementation reality | Reuse | Remaining closure |
|---|---|---|---|
| [0084](0084-pending-topics-and-the-greeting.md) | **Implemented, acceptance in progress** (merged 2026-11-13, `6a17e38`): ADR 0037 decision 2 (pending topics kept from the owner's verified words and picked up once by a greeting; migration 016) behind `PENDING_TOPICS_ENABLED`; day 1 on hardware passed | The one reader of spoken time (Plan 0083), the memory offer's slot (ADR 0021 decision 9), the conversation job, the recall sensitivity classifier | The greeting days on hardware, 2026-11-16 to 2026-11-19; then the close (ADR 0037 `Accepted`) |
| [0085](0085-database-good-practices.md) | **Draft** (2026-11-13): block C1 of ADR 0032 (decision 1), the database with good practices; nothing implemented | `db.run_migrations`, the store guards of `test_architecture_guards.py`, `recall_store`/`recall_index`, `iroko-admin` | Waits for [ADR 0038](../../adr/0038-the-memory-engines-storage-foundation.md) (Proposed): rewritten on it once Pipec answers its questions, then Pipec's review and the promotion to `Ready`; its real migration waits for Plan 0084's close; next free plan number **0086** |
| [0015](0015-personal-companion-design.md) | Approved product design; PC-1 to PC-4 are closed (PC-2 and PC-3A with provisional calibrations); reference only, never an executable batch | Controller, policy/audit, V4 household tools, identity/session seam, short-term continuity, the conversation record and recall index, STT/TTS, face engine | CM-6 and CM-7 (block C, then block D), PC-5 integrated personal acceptance and PC-6 family remain open |

Existing components named under **Reuse** must not be rebuilt by a later plan.

## Status rule

- `implemented` describes code, not product acceptance;
- `partial` means some named slices are reusable and others remain open;
- `design` or `ready` is not implementation evidence;
- a plan moves to `completed/` only when its own automated, review, and real
  runtime completion criteria are recorded.

The former body of this index (per-plan closing paragraphs, the Step 0 status of 2026-10-28, the
0049 audit note and the server-capsule notes) is archived in
[`docs/history/plans-open-readme-archive.md`](../../history/plans-open-readme-archive.md).
