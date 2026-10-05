# Open plan index

> **Status:** Work not yet closed. A plan can be implemented, partially
> implemented, deferred, or only designed and still belong here. Presence in
> this directory does not grant permission to implement.

## Audited disposition

The following status was checked against the executable code, tests, current
Git ancestry, and recorded runtime evidence on 2026-08-25 (updated after the
combined P0-C operator runbook passed and Plan 0013's STT-accuracy debt
closed), re-audited 2026-09-01 after Plan 0030 closed, aligned on
2026-09-07 with the longitudinal-memory design and its first two bounded
plans, updated 2026-09-08 after Plan 0046 closed CM-0, and again 2026-09-25
after Plan 0047 (PC-3A) closed with a provisional PASS and moved to
`completed/`, and again 2026-09-25 when the PC-3B re-audit produced
[Plan 0053](../completed/0053-consented-speaker-runtime-evidence.md), which closed 2026-09-29.
Existing components named under **Reuse** must not be rebuilt by a later plan.

For daily work, do not choose a plan from this inventory. Follow the
single-WIP [operational board](../README.md#operational-board) — **CM-0
(Plan 0046) closed 2026-09-08, PC-3A (Plan 0047) closed 2026-09-25 with a
provisional PASS, and PC-3B ([Plan 0053](../completed/0053-consented-speaker-runtime-evidence.md))
closed 2026-09-29, and PC-4 ([Plan 0054](../completed/0054-face-default-identity-fusion.md))
closed 2026-09-30; `NOW` is empty.** Use the
[personal-companion delivery map](../../roadmap/personal-companion-delivery-map.md)
and [conversational-memory delivery map](../../roadmap/conversational-memory-delivery-map.md)
to see the code, tests, verified gaps, and future delivery sequence.

| Plan | Implementation reality | Reuse | Remaining closure |
|---|---|---|---|
| [0015](0015-personal-companion-design.md) | Approved product design; PC-1 to PC-4 are closed (PC-2 and PC-3A with provisional calibrations) | Controller, policy/audit, V4 household tools, identity/session seam, working memory, legacy extraction/vector storage, STT/TTS, face engine | CM-1…CM-7 longitudinal memory, PC-5 integrated personal acceptance and PC-6 family remain open (CM-0 closed) |

## Propuesta de auditoría — no ejecutable

[0049 — conformidad de server con sus objetivos](0049-server-objective-conformance-audit.md)
es un **Draft** solicitado el 2026-09-22: contiene un diagnóstico inicial,
inventario de lectura y una campaña de revisión independiente propuesta.
No reemplaza al plan NOW (0047 cerró el 2026-09-25) ni autoriza reparaciones de código. Su revisión
independiente del 2026-09-23 y 2026-09-24 está en su §13.

[0050 — server audit repairs](../completed/0050-server-audit-repairs.md) **cerró el 2026-10-01** y ya vive en
`completed/`: ejecutó las doce tareas que cierran los hallazgos reproducidos de 0049
(ciclos de importación, un solo punto de salida a Ollama, límite de imagen antes
de decodificar, clasificación almacenada en el lector V4, readiness por dueño,
contrato de entrada del setup, settings muertos, nombres fuera de los logs,
guardas de arquitectura, matriz dueño → desconocido y reglas de intención por
palabra completa). `just gate` verde con 1695 tests y aceptación en hardware de
Pipec, salvo el veto de dos caras, que no se corrió. Ya no hay un plan `NOW`;
Pipec elige el siguiente.

[0056 — voice-pipeline reliability and diagnostics](../completed/0056-voice-pipeline-reliability-and-diagnostics.md)
**cerró el 2026-10-02** (PR #159, `4d62f26`) y ya vive en `completed/`: nueve tareas que reparan lo determinista (parser clásico,
`just test-pipeline`, guarda contra el eco del prompt de Whisper), amplían los evaluadores
(`eval-chat --mode stream`, veredictos por etapas con dataset versión 2) y **miden** lo que no se
conoce (fallback del protocolo de streaming, eco y alucinaciones sobre ruido sintético, primer turno
tras reiniciar), con la regla de decisión fijada antes de medir. Sus decisiones D-1 a D-8 están
confirmadas (la D-8: cada etapa se juzga con las compuertas que sus escenarios alimentan); se ejecutó el 2026-10-02 (Tareas 0 a 8; `just test` 1807). Las
mediciones abrieron un seguimiento (respaldo del streaming, 29,17 %) y cerraron dos (ruido y
primer turno). Pipec la aceptó en hardware real ese mismo día (el modo clásico no se corrió). Ya no hay un plan `NOW`; Pipec elige el siguiente.

[0057 — diagnóstico del respaldo del protocolo de streaming](0057-stream-protocol-diagnosis.md)
es un **Draft** escrito el 2026-10-05, a la espera de su turno y de que Pipec lo promueva; el orden
confirmado por Pipec el 2026-10-05 es CM-1 (Plan 0051) primero y esta reparación después, antes de CM-2;
hasta entonces no se ejecuta y `NOW` sigue vacío. Solo diagnostica y no toca `server/src`: clasifica las formas de
fallo (enum cerrado, sin texto), hace una ablación por factor (contexto de memoria, persona,
historial, posición del contrato, pregunta), mide si la validación del cuerpo depende de cómo
llegan los tokens (defecto confirmado por lectura del código y fijado por un test) y comprueba
si Ollama emite en incremental una respuesta con esquema JSON. Las reglas de lectura quedan fijadas
antes de medir. La reparación que le sigue sigue siendo `Unplanned`. El siguiente número libre es 0058.

[ADR-0015](../../adr/0015-owner-grant-scope-and-speaker-binding.md) (**Accepted**, 2026-09-25)
liga el grant PIN a una operación (hoy incumple ADR-0009) y, por etapas, a la
evidencia del hablante; el Plan 0051 lo implementa como primer plan de CM-1.

[0051 — grants del dueño con alcance](0051-scoped-owner-grants.md) está **Ready y es el plan `NOW`**
desde el 2026-10-05 (Pipec lo promovió y confirmó D-1 a D-7; va primero en la cola, antes de la
reparación del streaming). Implementa la decisión 1 de ADR-0015: cada grant queda ligado a una operación
(`personal_protected_read` por defecto, `biometric_admin` para enrolar o revocar cara y voz); un grant
presentado a otra operación se rechaza **sin gastarse**; «¿Quién soy?» y la respuesta «todavía no está
conectada» observan al actor y dejan de gastar el grant. El cambio de contrato es aditivo
(`scope` opcional en `POST /auth/owner/unlock`), el robot no cambia y no hay migración. Incluye la
aceptación en hardware, con el caso opcional del PIN que el Plan 0054 dejó sin correr.

[0053 — consented speaker runtime evidence](../completed/0053-consented-speaker-runtime-evidence.md)
(PC-3B) **cerró el 2026-09-29** y ya vive en `completed/`: enrolamiento consentido, revocación que
purga los voiceprints y evidencia `VOICE` tipada que **no concede nada** (sigue fuera de
`_RESOLVABLE_SOURCES`), detrás de `SPEAKER_AUTHENTICATION_ENABLED=false`. Aceptado en hardware real
y revisado de forma independiente; el replay no está defendido y la fusión es PC-4.

[0054 — face-default identity fusion](../completed/0054-face-default-identity-fusion.md) (PC-4)
**cerró el 2026-09-30** y ya vive en `completed/`, sobre
[ADR-0016](../../adr/0016-face-and-voice-identity-fusion.md) (**Accepted**): la cara identifica por
defecto (`basic`), la voz de la misma persona sube a `strong`, los datos reservados (`SECURITY`)
exigen `strong`, y otra persona enrolada o dos caras vetan. Aceptado en hardware real por Pipec; el
replay no está defendido y aún no existe ninguna capacidad reservada.

[0055 — PC-4 identity fusion follow-ups](../completed/0055-pc4-identity-fusion-followups.md) **cerró el 2026-10-01** y ya vive en `completed/`: un error de base de datos al reconocer la cara degrada a desconocido en vez de fallar el turno, los modelos de cara y voz se precargan al arrancar (una muestra en hardware: primer turno protegido 3,6 s, antes 8 a 13 s), una sola definición de `identity_source` y del reloj, y el veto de otra persona queda probado contra filas reales. No cambió la regla de identidad ni el OpenAPI. No hay plan `Ready` ni `NOW`: el siguiente (0050, voz-pipeline, CM-1/0051) lo promueve Pipec.

**Paso 0 — carga inicial (sin numerar, decidido 2026-09-24, reubicado 2026-09-30).**
Un plan futuro que carga los datos base del dueño y su hogar de forma presencial
desde un archivo local (o formulario). Va después de CM-3 porque es el segundo
canal de entrada del escritor canónico de CM-3; hasta entonces el setup sigue
siendo `just setup-personal` y `just onboard`. Sus reglas —la seguridad no depende
del canal de carga, y lo que el robot aprende después refina datos sin pisar los
cargados— están en el *Non-goals* de 0050. El orden único y las tres vías de la
compra de electrónica están en el
[portafolio](../../roadmap/cognitive-roadmap.md#canonical-pre-electronics-delivery-portfolio)
y en la [puerta previa a la compra](../../roadmap/cognitive-roadmap.md#pre-purchase-readiness-gate--plug-it-in-and-it-works).

## Server-production capsule — CLOSED 2026-09-03

[Plan 0031](../completed/0031-server-production-baseline-design.md) locked
the execution order of its children; all of them (0032–0045,
including Plan 0043's dependency refresh which ran first, and Plan 0045, a
test-isolation gap Plan 0042's own gate found) are closed. Full per-plan
evidence lives in each plan's own file under [`completed/`](../completed/)
and in the [dependency-order table](../README.md#dependency-order) — not
duplicated here, since nothing in this capsule is still open. **No child
plan remains queued.**

Plans 0014 (P0 runtime-policy umbrella), 0020 (operator-QA remediation
umbrella), and 0024 (owner-authenticated memory MVP design) closed with no
remaining code or gates of their own — each was reference material for
already-completed slices — and moved to `completed/`; see
[completed/0014](../completed/0014-p0-runtime-policy-hardening-design.md),
[completed/0020](../completed/0020-p0-operator-qa-remediation-design.md), and
[completed/0024](../completed/0024-owner-authenticated-memory-mvp-design.md).
Plans 0025, 0026, 0027, and 0028 (all merged/executed, PC-1 accepted
2026-08-21) closed with no remaining acceptance debt of their own — see
[completed/0025](../completed/0025-personal-owner-bootstrap-and-pin-setup.md),
[completed/0026](../completed/0026-one-use-owner-authenticated-classic-turn.md),
[completed/0027](../completed/0027-one-use-owner-streaming-parity.md), and
[completed/0028](../completed/0028-owner-authenticated-memory-runtime-acceptance.md).
Plans 0021 (C5, operator-confirmed 2026-08-21), 0023 (C7, operator-confirmed
2026-08-25), and 0013 (voice-controller bridge, R1 complete 2026-08-25 after
fixing the Whisper prompt's stale "Omnibot" name) closed the same way — see
[completed/0021](../completed/0021-p0-typed-intent-resolution.md),
[completed/0023](../completed/0023-p0-grounded-visual-dialogue.md), and
[completed/0013](../completed/0013-p0-voice-controller-bridge.md).

Plans 0029 (consented local face evidence, merged PR #73, 2026-08-25) and
0030 (real-camera face acceptance, executed 2026-09-01 — **provisional
PASS**: 36 genuine + 18 impostor real samples, zero false accepts/rejects,
threshold `0.5815` confirmed by 3 accepted + 3 denied live turns) closed
PC-2 completely — see
[completed/0029](../completed/0029-consented-local-face-evidence.md) and
[completed/0030](../completed/0030-real-camera-face-acceptance.md).

Plan 0046 (CM-0 reproducible longitudinal-memory baseline) closed 2026-09-08 —
the benchmark harness is GREEN and the measured baseline is a reproducible
cognitive RED (`ac43c58`, exit 1); it changed no runtime memory. See
[completed/0046](../completed/0046-reproducible-longitudinal-memory-baseline.md).

Canonical execution order: **`NOW` is empty; Plan 0054 (PC-4) closed 2026-09-30.** Plan 0053 (PC-3B)
closed 2026-09-29, and Plan 0047 (PC-3A) closed 2026-09-25 with a provisional PASS
(see [completed/0047](../completed/0047-speaker-evidence-calibration-study.md)); the
queue-rule-4 re-audit of the next row ran the same day, produced Plan 0053, and
Pipec answered its decisions and promoted it. The server capsule (Plan
0031, children 0032–0045) is fully closed.

[Plan 0048](../completed/0048-fastapi-baseline-final-hardening.md) closed
2026-09-07: a bounded follow-up to a second independent audit of the server
(semantic `max_length` on free-text fields, a real one-terminal-event
guarantee in `guarantee_terminal_event`, the `/transcribe/stream` 200
documented as `application/x-ndjson`, `/health` wording + a
settings-injectable `create_app`). 1073 tests, 90.10% coverage, all gates
green. The "how should FastAPI do this?" phase is over; the server baseline
is done. Only Uvicorn concurrency calibration remains; since 2026-09-30 it is measured on the homelab server inside PC-5 (portfolio row 12), not in a separate `perf(...)` plan.

## Status rule

- `implemented` describes code, not product acceptance;
- `partial` means some named slices are reusable and others remain open;
- `design` or `ready` is not implementation evidence;
- a plan moves to `completed/` only when its own automated, review, and real
  runtime completion criteria are recorded.
