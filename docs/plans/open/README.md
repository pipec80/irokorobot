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
| [0085](0085-database-good-practices.md) | **Ready** (promoted by Pipec on 2026-11-16; trimmed the same day on Pipec's scope rule; [ADR 0038](../../adr/0038-the-memory-engines-storage-foundation.md) as amended): block C1, the storage foundation in its minimum version (A safety with no table change, B four small migrations, the dictionary and a health check); in execution: Part A on PR #279, its hardware check passed 2026-11-16 | `db.run_migrations`, the store guards of `test_architecture_guards.py`, `conversation_record`'s public functions, `recall_store`/`recall_index`, `iroko-admin` | Part B on its branch; both parts may merge now that Plan 0084 is closed, and the real migration runs at the first start; next free plan number **0086** |
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
