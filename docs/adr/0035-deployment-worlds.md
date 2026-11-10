# 0035 — Deployment worlds: the ESP32 body, the server board, the remote dashboard

- **Status:** Accepted (2026-11-10, decided by Pipec in the documentation review of that day;
  it has no implementing plan of its own: it fixes the vocabulary and the placement that later
  plans build against)
- **Date:** 2026-11-10
- **Builds on:** [ADR 0002](0002-server-robot-separation.md),
  [ADR 0013](0013-local-http-network-posture.md),
  [ADR 0024](0024-seed-load-senses-secrets-and-channels.md),
  [ADR 0025](0025-remote-administration-backup-updates-and-telemetry.md)
- **Amends:** the wording of ADR 0002 («compute a Raspberry Pi cannot provide») and the mentions
  of the Raspberry Pi as the body in ADRs 0001, 0003, 0023, 0024 and 0025; each carries a
  one-line note. No decision of those ADRs changes. ADR 0025's decisions on the remote half stay
  the authority of the third world.
- **Delivers:** no roadmap slice. It reframes the physical track of the
  [roadmap](../roadmap/cognitive-roadmap.md) (P4.2 and electronics track 1).

## Context

Until now the documents said that the robot is a Raspberry Pi 5 and that a homelab server does
the heavy work. That was a planning assumption of August 2026, never measured. Pipec decided
otherwise on 2026-11-10, and the ADRs, the roadmap and `AGENTS.md` still carry the old picture:

- The body is not a Raspberry Pi. It is an **ESP32 board** with the sensors, the microphone, the
  speaker and the camera. Today the PC's microphone, webcam and speakers are a provisional body.
- The brain does not need a second computer in the house to exist. The **laptop is the home
  server** now (the deployment of ADR 0033 is planned); later a board able to run the language
  model replaces it (Raspberry Pi or Jetson class, not chosen).
- A **remote dashboard** is a third thing, later: it administers the robot from outside the
  house (ADR 0025, remote half), and it is not a local web interface of the server.
- An ESP32 cannot run the Python `robot/` client. A body on an ESP32 needs its own client, which
  no plan lists.

## Decision

### 1. Three worlds

| World | What it is | Today | Later |
|---|---|---|---|
| **Body** | An ESP32 board with the microphone, the speaker, the camera and the sensors; it captures and plays, it does not decide | The PC's microphone, webcam and speakers, driven by the Python `robot/` client | The ESP32 board |
| **Server** | Everything that thinks: speech to text, identity, memory engine, controller, language model, speech synthesis | This laptop, as the home server (ADR 0033) | A board that can run the language model (Raspberry Pi or Jetson class) |
| **Remote dashboard** | Administration from outside the house: VPN, admin web, support session, backups, updates, telemetry | Nothing; the local command-line tool `iroko-admin` is ADR 0025's local half | Later work; ADR 0025 decides it, this ADR adds no new rule |

The hard boundary of ADR 0002 does not move: the server is a generic audio API that does not
know a robot exists, and the body is a generic client that does not know that speech to text, a
language model or speech synthesis exist. The three worlds are three places for the same two
halves, plus the administrator.

### 2. Local first, and the robot runs without a PC

The body talks to the laptop first and to the server board later, over the home network
(ADR 0013). The target is a robot that runs without a PC: no step of the pipeline may need a
developer machine, an IDE or a cloud account. This is the same direction as ADR 0004, applied to
the hardware.

### 3. The ESP32 needs its own client

The current Python `robot/` client cannot run on an ESP32. A client for the body is **a future
work item with two possible shapes**: firmware that speaks the API contract directly, or a thin
gateway (a small board or the server itself) that speaks it for the ESP32. The choice is not made
here. Until it is made, the Python client is the provisional body's client and stays as it is.

### 4. Thresholds belong to the device

The face threshold (0.5815), the voice threshold (0.4834) and the speech-to-text profile were
measured on this laptop's camera and microphone. They are **device-specific**: a new body means
a new calibration (re-enrol, re-measure, recheck the false accept and false reject rates). Nothing
in the code changes by this decision; the roadmap row about recalibration on a new device is its
home.

## Pipec's decisions

| # | Decision | Date |
|---|---|---|
| 1 | The body is an ESP32 board, not a Raspberry Pi | 2026-11-10 |
| 2 | The laptop is the home server now; a Raspberry Pi or Jetson class board later, undecided | 2026-11-10 |
| 3 | The remote dashboard is a third world, later work | 2026-11-10 |
| 4 | The ESP32 talks to the laptop first, to the server board later; the robot must eventually run without a PC | 2026-11-10 |
| 5 | The wording that made the Raspberry Pi the body is corrected by note, the decisions stay | 2026-11-10 |

## Not decided here

| Subject | Owner |
|---|---|
| Firmware client or thin gateway for the ESP32, and its transport | A plan of the electronics track, when the body is bought |
| Which board becomes the server (Raspberry Pi, Jetson or another), and its model budget | A measurement on the candidate board; ADR 0033 for the deployment |
| The remote dashboard itself | ADR 0025 (remote half); no plan yet |
| The sensors, motors and the physical safety layer | P2.1 and P4.2 of the roadmap |
| Whether the ESP32 also hosts a local wake word or voice activity detection | The electronics plan |

## Alternatives considered

- **Keep the Raspberry Pi as the body.** Rejected by Pipec: the body is an ESP32 with the senses,
  and the heavy work stays in the server world.
- **Put the server on the ESP32.** Rejected: the language model, the memory engine and the speaker
  verification need far more compute and memory than a microcontroller has.
- **One document for each board.** Rejected: the boards change, the three worlds do not.

## Consequences

### Positive

- The documents describe one placement of the halves instead of two competing ones.
- The missing ESP32 client is a named work item, not a surprise at the day the board arrives.
- The new-device recalibration is attached to the body, where the measurement changes.

### Negative

- Until the ESP32 client exists, the provisional body (the PC) is the only way to run the robot.
- Wording notes in seven older ADRs; a reader of those must follow the note.

## Docs to update

`AGENTS.md` and `CLAUDE.md` (hardware line), [`implementation-guardrails.md`](../architecture/implementation-guardrails.md),
[`cognitive-architecture.md`](../architecture/cognitive-architecture.md),
[`personality-and-interaction.md`](../architecture/personality-and-interaction.md), the
[roadmap](../roadmap/cognitive-roadmap.md) (P4.2, electronics track 1), the [docs index](../README.md), the
robot's description strings and `.env.example`. Done in the documentation change that adds this ADR.

## Review

Revisit when the ESP32 is bought, when the server board is chosen, or when the remote dashboard
gets a plan.
