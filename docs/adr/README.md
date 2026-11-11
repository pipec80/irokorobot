# Architecture Decision Records

This directory records significant architecture decisions for Iroko / OMNiBot 2000
using lightweight [ADRs](https://adr.github.io/).

An ADR is immutable once accepted. To change a decision, add a new ADR that
supersedes it and update the old one's status.

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-use-uv-workspace.md) | Use uv with a workspace | Accepted |
| [0002](0002-server-robot-separation.md) | Separate server (brain) and robot (senses) | Accepted |
| [0003](0003-python-312-minimum.md) | Require Python 3.12+ | Accepted |
| [0004](0004-local-first-cognitive-policy.md) | Adopt a local-first cognitive policy | Accepted; escalation clause under review by [0036](0036-model-providers-local-first.md) (Proposed) |
| [0005](0005-small-typed-cognitive-controller.md) | Evolve a small typed cognitive controller | Accepted |
| [0006](0006-personal-and-family-companion-profiles.md) | Support personal and family companion profiles | Accepted |
| [0007](0007-first-boot-and-default-posture.md) | First boot and local-channel default posture | Accepted; local-owner presumption superseded by 0008 |
| [0008](0008-progressive-owner-authentication.md) | Progressive owner authentication | Accepted; partially supersedes 0007 |
| [0009](0009-locked-posture-and-scoped-capabilities.md) | Locked posture and scoped capabilities | Accepted |
| [0010](0010-fastapi-asgi-runtime-baseline.md) | Standardize the FastAPI/ASGI runtime baseline | Accepted |
| [0011](0011-sqlite-transaction-ownership.md) | Give each SQLite write transaction one coroutine owner | Accepted |
| [0012](0012-line-delimited-stream-terminal-events.md) | Require a terminal event in the line-delimited stream | Accepted |
| [0013](0013-local-http-network-posture.md) | Keep the HTTP server local-first by default | Accepted; amended by 0025 (remote access, not built) |
| [0014](0014-orthogonal-social-and-responsibility-profiles.md) | Keep social and responsibility profiles orthogonal | Accepted |
| [0015](0015-owner-grant-scope-and-speaker-binding.md) | Bind the owner grant to a named operation and to speaker evidence | Accepted; decision 2 refined by [0016](0016-face-and-voice-identity-fusion.md) |
| [0016](0016-face-and-voice-identity-fusion.md) | Identify the owner by face; require more assurance for reserved data | Accepted |
| [0017](0017-streaming-reply-protocol.md) | Speak what the model means: a tolerant, bounded streaming reply protocol | Superseded by [0018](0018-user-emotion-decided-apart.md); never Accepted |
| [0018](0018-user-emotion-decided-apart.md) | Decide the user's emotion apart from the streamed reply | Accepted (Plan 0059's measurement met its gate) |
| [0019](0019-personal-memory-capabilities.md) | Authorize personal memory by named capability, assurance and grant scope | Accepted (2026-10-09); implemented as policy by Plan 0060; `propose`, `read` and `confirm` are consumed by CM-3a since Plans 0062 and 0063 |
| [0020](0020-authorized-actor-in-the-conversation.md) | Identify the speaker on every turn and keep short-term continuity for the identified person | Accepted (2026-10-13); implemented by Plan 0061; partially supersedes 0016 §5 and amends 0016 §8 |
| [0021](0021-memory-candidates-and-the-canonical-writer.md) | Keep what the owner says as a candidate, and let one deterministic writer promote it | Accepted (2026-10-16; proposed 2026-10-14, amended 2026-10-15); implemented by Plan 0062 (closed 2026-10-15) and Plan 0063 (closed 2026-10-16); refines 0019 §6 and §1 |
| [0022](0022-household-rules-and-third-party-memory.md) | Household rules: whose data a third party's fact is, and one writer for every channel | Accepted (2026-10-22; proposed 2026-10-16); implemented by Plan 0065 (tranche A of CM-3b, closed 2026-10-22) |
| [0023](0023-speech-to-text-model-and-decoding.md) | Speech-to-text: the model, the decoding and the turn closing, measured on the owner's voice | Accepted (2026-10-21); implemented by Plan 0069 |
| [0024](0024-seed-load-senses-secrets-and-channels.md) | The seed load: the data pool, secrets at rest, contacts, the confirmation of an assisted interview, identity modalities and the order of the commissioning | Accepted (2026-10-27; proposed 2026-10-22, revised 2026-10-23); implemented by Plans 0070 (the storage, 2026-10-23), 0071 (the importer, 2026-10-26) and 0072 (the session, 2026-10-27); amends 0022 decisions 1, 2 and 9 |
| [0025](0025-remote-administration-backup-updates-and-telemetry.md) | Administering a local-first robot: the surfaces, support sessions, backup, updates and telemetry | Accepted (2026-10-28, local half: Plan 0073 closed — the command-line tool `iroko-admin` over SSH); the remote half has no plan yet; amends 0013 |
| [0026](0026-owner-profile-card-and-the-read-side-of-memory.md) | Read the owner's profile back: a small card in every identified turn, and nothing sensitive in it | Accepted (2026-10-28); implemented and accepted on hardware by Plan 0074; splits CM-5 in two, amends 0020 §7 |
| [0027](0027-conversation-record-and-the-diary.md) | Keep the whole conversation as a record, and build the diary from the owner's part of it | **Accepted** (2026-10-30); replaces the diary rule of ADR 0026's decision 3 and answers ADR 0025 decision 5; implemented by [Plan 0076](../plans/completed/0076-cm4-conversation-record-and-diary.md), accepted on hardware |
| [0028](0028-recall-what-the-owner-told.md) | Recall what the owner told: search the diary on a recall cue, and answer only from what was found | Accepted (2026-11-04, Plan 0078 closed, with amendments A1–A5); CM-5b + R3, block A of the closing path; amends 0027 decision 5 and 0026 decision 5 |
| [0029](0029-it-knows-who-is-listening.md) | It knows who is listening: read the owner's sensitive data by voice, by levels, and never keep a spoken secret | **Accepted** (2026-11-06, Plan 0079 closed, accepted on hardware 10 of 10; proposed 2026-11-04, amended 2026-11-05, decisions 8 to 21); block B of the closing path, one plan (0079); amends 0019 §3, 0026 decisions 6 and 9, 0027 decision 1 |
| 0030 | *Reserved* — keeping a household secret with authorization and answering in company (ADR 0029 decision 15) | Not written; after CM-7 + PC-5 |
| [0031](0031-the-memory-engine-boundary.md) | The memory engine: one boundary, swappable policies | **Accepted** (2026-11-09, on Pipec's review after two external reviews); the engine is extracted only after CM-7 + PC-5; constrains ADRs 0032 (block C), 0033 (deployment) and 0034 (documents) |
| [0032](0032-block-c-hygiene-correct-forget-and-years.md) | Block C: a clean database, correcting and forgetting, and memories that last for years | **Proposed** (2026-11-11); row 8 of the path to the finish line; would supersede ADR 0026's Pipec decision 4 and the forget row of ADR 0019 for ordinary memories, and amend ADR 0027 |
| [0033](0033-the-home-server-in-a-container.md) | The home server: the brain in a container on the laptop, the body a client | **Proposed** (2026-11-11); row 10 of the path to the finish line; would amend ADR 0013 and lift Docker from the «Future» list |
| [0034](0034-documents-and-reading-through-the-camera.md) | Documents in the memory engine, and reading through the camera | **Proposed** (2026-11-11); row 9 of the path to the finish line; would amend ADR 0031 decision 13 |
| [0035](0035-deployment-worlds.md) | Deployment worlds: the ESP32 body, the server board, the remote dashboard | **Accepted** (2026-11-10, decided by Pipec); amends in wording ADRs 0001, 0002, 0003, 0023, 0024 and 0025 (a note each, no decision changes) |
| [0036](0036-model-providers-local-first.md) | Model providers: local by default, a cloud provider only as an explicit opt-in | **Proposed** (2026-11-10); open questions for Pipec; would amend the escalation clause of 0004, which stays Accepted until then |
| [0037](0037-the-time-of-memories-and-a-contacts-phone.md) | The time of memories and the alta by voice: when it happened, what is pending, and every loaded datum reachable | **Proposed** (2026-11-11); row 7 of the path to the finish line; would amend ADR 0024 decision 5, ADR 0029 decision 1 and ADR 0031 decision 5 |

New ADRs start from [`0000-adr-template.md`](0000-adr-template.md).
