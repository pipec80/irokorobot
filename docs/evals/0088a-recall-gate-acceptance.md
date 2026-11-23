# Plan 0088 Part A — hardware acceptance of the relevance gate (ADR 0040)

> **Status:** run by Pipec on 2026-11-23, streaming route, branch `feat/0088a-recall-gate` (PR #306),
> `RECALL_ENABLED=true`, `RECALL_MAX_DISTANCE` 0.43, `RECALL_WORD_MAX_DISTANCE` 0.464 (default).
> Outcomes only: no transcript, story, name or reply text is recorded here. The counts come from the
> `recall.read` lines of `logs/server.log` (`outcome`, `hits`, `best_distance`, `rejected`,
> `specific`, `lexical_only`, `gate` = `G3`).

## Two sittings

1. **The diary as it was.** Few stories were told before today, so the cases had little to find or
   to confuse. Cases 1, 2 and 5 were run there; case 3 was not reached («¿qué te conté?» with no
   topic is the profile summary, not a recall cue).
2. **Seed, then ask** (the protocol below). Pipec told six real stories of his last month, one per
   turn, each 5 to 25 s; all six were captured with his voice `verified`. After the indexing delay
   (about two minutes) the D-7 cases were asked about them.

## The cases (D-7)

| # | Case | Sitting | `recall.read` | Expected | Result |
|---|---|---|---|---|---|
| 1 | A person never told | 1 | `nothing_found`, specific 1, rejected 20, nearest 0.397 | «No me acuerdo de eso.» | **pass** |
| 1 | A person never told | 2 | `nothing_found`, specific 1, rejected 20, nearest 0.414 | «No me acuerdo de eso.» | **pass** |
| 2 | A story asked by its words | 1 | `found`, 2 hits | the story | **pass** |
| 2 | A story asked by a told name | 2 | `found`, 2 hits, specific 1 | the story | **pass** |
| 3 | A story asked by its meaning (no shared word) | 2 | `found`, 2 hits, best 0.407 | the story | **pass** |
| 4 | A weak cue sharing one common word, far in meaning | 2 | `found`, 3 hits, best **0.426**, specific 0 | converses | **fail — the meaning threshold, not the word gate** |
| 5 | «¿Qué te conté ayer?» / «¿qué te conté hoy?» | 1 / 2 | windowed, date-only path (no gate) | unchanged | **pass** |
| 6 | The embedding model stopped, an exact number asked | 2 | `found`, 1 hit, `lexical_only`, specific 1 | the story | **pass** |
| extra | A story asked by a number in it («la línea N») | 2 | `found`, 2 hits, specific 1 | the story | **pass** |

Before the change, with today's rule, case 1 would have answered a wrong story in both sittings:
the nearest unit lay under 0.43 (0.397 and 0.414). The gate refused it because the unit does not
hold the named person.

## Case 4, read

The hits qualified by their **vector distance** (0.426 < `T_v` 0.43), not by the shared word, so
the old rule would have returned them too. This is the meaning threshold, the problem ADR 0040
records apart from the gate, and it is new evidence for it. The same `T_v` is too tight for some
questions asked by meaning (the bench: 6 of 8 above 0.43) and too loose for an unrelated weak cue
(0.426 here). In sitting 1 a weak cue showed the same shape (hits at 0.402).

Also observed, older than this plan: with hits in front of it, the recall wording answered a weak
cue with a denial-like sentence of its own («No, no me acuerdo de…»); ADR 0028 A4's guard catches
only the exact fixed phrase. Recorded, not changed here.

## The protocol: seed, then ask (reusable)

Use it whenever recall or the gate changes. The examples are invented; the owner tells their own.

**Seed** — one story per turn, each 5 to 25 s (a short clip seldom verifies the voice; above about
28 s it is cut), alone in front of the camera; wait about two minutes after the last one. Between
them, the stories should hold:

| A story with… | Invented example | For case |
|---|---|---|
| A person's name | «El sábado almorcé con mi amigo Anselmo y comimos ceviche.» | 2 |
| A number or code | «Compré el filtro ZX-41 para la lavadora.» | 6 and the extra |
| Something askable in other words | «Fui a la feria y compré paltas y tomates.» | 3 («¿qué te conté del mercado?») |
| A common word | «Llevé el auto al taller porque sonaba raro.» | 4 |

Avoid the words that raise a turn above `normal` and hide it from recall: health (doctor, dolor,
remedio, examen), secrets (clave, código, pin, contraseña), address (calle, dirección, «vivo en»)
and legal ones (abogado, juicio).

**Ask** — 1 a name never told; 2 a told name; 3 the meaning question; 4 a general weak cue sharing
one common word («¿te acuerdas del auto fantástico?»); 5 «¿qué te conté hoy?»; 6 with Ollama
stopped, the exact number or code. Read `recall.read` for each.

## Verdict

**Accepted by Pipec on 2026-11-23** («Sí, acepto»), with case 4 recorded as the meaning
threshold's, apart from the gate. ADR 0040 is `Accepted`; Part B of Plan 0088 may start.
