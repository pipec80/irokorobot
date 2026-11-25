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
| [0015](0015-personal-companion-design.md) | Approved product design; PC-1 to PC-4 are closed (PC-2 and PC-3A with provisional calibrations); reference only, never an executable batch | Controller, policy/audit, V4 household tools, identity/session seam, short-term continuity, the conversation record and recall index, STT/TTS, face engine | CM-6 and CM-7 (block C, then block D), PC-5 integrated personal acceptance and PC-6 family remain open |
| [0089](0089-vision-model-and-streaming-scene.md) | Draft, for Pipec's review (2026-11-24); no code | The vision calls (`vision/describe.py`, `vision/read_text.py`), the turn's frame on both voice routes, Plan 0088's reading and record markers | Pipec's eight decisions, then `Ready` |

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
