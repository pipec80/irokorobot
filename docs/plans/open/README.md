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
closed 2026-09-30, Plan 0061 (CM-2) closed 2026-10-13, [Plan 0062](../completed/0062-cm3a-memory-candidates-and-writer.md) (CM-3a, primer corte) closed 2026-10-15, [Plan 0063](../completed/0063-cm3a-memory-dialogue.md) (CM-3a, segundo corte) closed 2026-10-16, [Plan 0065](../completed/0065-cm3b-a-channel-neutral-writer-core.md) (CM-3b, tramo A) closed 2026-10-22, and Plans 0064, 0066 and 0067 closed 2026-10-19, and [Plan 0069](../completed/0069-stt-owner-voice-audit.md) closed 2026-10-21; [Plan 0068](../completed/0068-short-clip-speaker-measurement.md) closed 2026-10-21 with Tasks 7 and 8 deferred; `NOW` is empty and [Plan 0065](../completed/0065-cm3b-a-channel-neutral-writer-core.md) closed 2026-10-22.** Use the
[personal-companion delivery map](../../roadmap/personal-companion-delivery-map.md)
and [conversational-memory delivery map](../../roadmap/conversational-memory-delivery-map.md)
to see the code, tests, verified gaps, and future delivery sequence.

| Plan | Implementation reality | Reuse | Remaining closure |
|---|---|---|---|
| [0015](0015-personal-companion-design.md) | Approved product design; PC-1 to PC-4 are closed (PC-2 and PC-3A with provisional calibrations) | Controller, policy/audit, V4 household tools, identity/session seam, working memory, legacy extraction/vector storage, STT/TTS, face engine | CM-1…CM-7 longitudinal memory, PC-5 integrated personal acceptance and PC-6 family remain open (CM-0 closed) |

## Plan en curso (`NOW`)

**`NOW` está vacío.** El [Plan 0072](../completed/0072-commissioning-session.md) (Paso 0, tercer plan: la sesión de alta) **cerró el 2026-10-27**, ensayado de punta a punta por Pipec con cámara, micrófono y servidor reales: `just commission` guía el alta con una máquina de estados, enrola cara y voz (el PIN antes de cada toma), registra los consentimientos y los respaldos, emite el informe de preparación de las capacidades que existen y cierra la ventana con el acta; el [ADR 0024](../../adr/0024-seed-load-senses-secrets-and-channels.md) pasó a `Accepted`. Su alta real con los datos de Pipec se hizo ese mismo día (2026-10-27) y quedó registrada. El Plan 0073 sigue en `Draft`. El [Plan 0071](../completed/0071-seed-load-file-importer.md) (Paso 0, segundo plan: el importador por archivo) **cerró el 2026-10-26**, aceptado por Pipec en una base aparte: `just seed-import` carga el expediente desde un TOML local (prueba en seco por defecto, la revisión de la persona titular y `SI` para aplicar, una sola transacción con el acta, `--replace` solo mientras dura la puesta en marcha y sin memoria aprendida por voz). (Entonces los planes 0072 y 0073 seguían en `Draft`.) El [Plan 0070](../completed/0070-seed-load-data-pool-storage.md) (Paso 0, primer plan: el almacenamiento del pozo de datos y la procedencia de una entrevista asistida) **cerró el 2026-10-23**: migración 011, los predicados del pozo, el secreto guardado por referencia, el hijo adulto y los parientes en el escritor, la política de rechazar el conflicto, los contactos con teléfono y el registro de la puesta en marcha; el 0071 lo carga y nada lo lee por voz todavía. (Entonces los planes 0072 y 0073 seguían en `Draft`.) El [Plan 0065 — CM-3b, tramo A: el núcleo escritor neutral al canal](../completed/0065-cm3b-a-channel-neutral-writer-core.md) **cerró el 2026-10-22**: hay un solo escritor de memoria para todos los canales, la migración 010, la validez de las relaciones, el par de capacidades del hogar (solo política) y el dataset v3 del benchmark; `just gate` 4179 pasaron y el [ADR 0022](../../adr/0022-household-rules-and-third-party-memory.md) pasó a `Accepted`. Siguió el Paso 0, cuyo primer plan es el 0070. El [Plan 0068 — respuestas cortas y la verificación de voz](../completed/0068-short-clip-speaker-measurement.md) **cerró el 2026-10-21**: el código está mergeado (PR #201, `917deec`; la corrección de «a guardarlo» es el PR #203) y los conteos de hardware de la tarea 6 se tomaron ese día con el perfil adoptado ([ADR 0023](../../adr/0023-speech-to-text-model-and-decoding.md)): 7 ofertas, 1 promovida, 1 rechazada, 1 reintento y ninguna promoción equivocada. **Las tareas 7 y 8** (grabaciones de clips cortos e informe, que necesitan al menos tres adultos que consientan, o la Pi) **quedaron diferidas por Pipec** y siguen nombradas en la fila «Remaining biometric measurements» del roadmap.

**Cerrado:** el [Plan 0069 — el reconocimiento de voz con la voz real del dueño](../completed/0069-stt-owner-voice-audit.md), el 2026-10-21 (PR #202): el STT se midió por primera vez con la voz de Pipec, `medium` en GPU es el perfil recomendado (WER 15,4 % a 6,8 % en la mitad de prueba) y el corpus privado se borró. Antes ocupó `NOW` el [Plan 0067](../completed/0067-reply-listening-mode.md), que **cerró el 2026-10-19** (PR #199).


### Lo que queda antes de escribir el plan del Paso 0

Estado al 2026-10-22, con el Plan 0065 cerrado y `NOW` vacío. El orden y las compuertas
siguen siendo los del [roadmap](../../roadmap/cognitive-roadmap.md); esta lista solo dice qué falta.

**Bloquea el plan del Paso 0 (la carga de datos):**

1. ~~Ejecutar el Plan 0065~~ **Hecho el 2026-10-22.** Entregó el escritor neutral al canal que el importador
   del Paso 0 usa. La corrida del benchmark v3 con el Ollama de Pipec (2026-10-22) dio 90 pasos: 0 pasan, 3 fallan (la extracción, igual que antes) y 87 no soportados.
2. ~~ADR 0022~~ **`Accepted` el 2026-10-22.** El Paso 0 depende de sus reglas y debe decidir lo que el ADR
   deja abierto: dónde se guarda un valor `security` en reposo, la regla del hijo adulto, y si un
   representante o un segundo adulto puede afirmar o confirmar en nombre del dueño.

**Estado del Paso 0 (2026-10-23):** el [ADR 0024](../../adr/0024-seed-load-senses-secrets-and-channels.md)
(`Proposed`, revisado tras dos revisiones independientes) decide el pozo de datos, el secreto guardado por
referencia, los contactos con teléfono, la confirmación de una entrevista asistida y el orden de la puesta en
marcha; el catálogo de campos está en [`seed-data-pool.md`](../../architecture/seed-data-pool.md). El
[Plan 0070](../completed/0070-seed-load-data-pool-storage.md) (cerrado el 2026-10-23) es el almacenamiento y la procedencia; el
[Plan 0071](../completed/0071-seed-load-file-importer.md) (cerrado el 2026-10-26) es el importador por archivo, y el
[Plan 0072](../completed/0072-commissioning-session.md) (cerrado el 2026-10-27) es la sesión de puesta en marcha: enrolar cara y
voz en un solo flujo (`just commission`), la sesión de voz (tres referencias; los ajustes de voz por persona quedaron fuera), el informe de preparación por capacidad,
el cierre de la ventana y el acta; la alta real de Pipec se hizo el 2026-10-27. El
[Plan 0073](0073-local-admin-crud.md) (`Draft`, un esquema) es la administración local (un CRUD por línea de comandos
sobre SSH, sin servicio web nuevo) que cierra la fase 0 y es la vía de enmienda de contactos y medicamentos tras el cierre; su mitad remota (VPN, sesión de soporte, respaldo,
actualizaciones, telemetría) es el [ADR 0025](../../adr/0025-remote-administration-backup-updates-and-telemetry.md)
(`Proposed`), sin plan. Ninguno está `Ready`: los promueve Pipec. **Siguen sin plan:** la lectura estructurada del perfil
por voz (primera porción de CM-5) y la escalada «¿estás con alguien?» (CM-5, necesita la audiencia del turno).

**No bloquea, pero queda abierto** (cada uno con su fila en el roadmap):

- **Latencia del modelo de lenguaje** junto a la extracción de memoria: turnos de 20 a 40 s que, además,
  se comen la ventana de 60 s de una oferta. Pipec la mira en la aceptación; el plan chico, si hace
  falta, puede ir ya (el 0065 cerró).
- **Respuesta dicha junto a otra frase** («no acepto» y luego una oración): hoy va al modelo; Pipec decide
  si un verbo cerrado que abre un enunciado más largo debe contar.
- **Tareas 7 y 8 del Plan 0068** (clips cortos de la verificación de voz, con tres adultos que consientan
  o con la Pi): fila «Remaining biometric measurements».
- **Micrófono de la Pi**, ruido con voces y GPU frente a la VRAM de Ollama: se vuelven a medir con el
  cuerpo definitivo.

El `NOW` anterior a ese fue [0062 — candidatos de memoria y escritor canónico, primer corte (CM-3a)](../completed/0062-cm3a-memory-candidates-and-writer.md), que **cerró el 2026-10-15** (PR #183) y vive en `completed/`: la tabla de candidatos (migración 009), el escritor canónico `promote`, la puerta de preferencias, el extractor que solo ve las palabras del usuario, el clasificador, la política auditada antes del efecto y la propuesta en segundo plano que exige la cara **y** la voz de la misma persona en el propio clip, detrás de `MEMORY_CANDIDATES_ENABLED=false`. Retiró `consolidate_turn`, `PROPOSE_MEMORY` y `COMMIT_MEMORY`. `just gate` 2972 tests (filtro de CI 2955; línea base 2597 / 2580).

El `NOW` anterior a ese fue [0061 — continuidad de corto plazo para la persona identificada (CM-2)](../completed/0061-cm2-generic-turn-continuity.md), que **cerró el 2026-10-13** y vive en `completed/`: la ranura de continuidad (3000 caracteres, 180 s, una sola persona, generación), la identificación de los turnos genéricos sin voz y sin gastar el grant, su cableado en las tres rutas, una frase del prompt con compuerta medida (fallback 0,00 % en `history` en dos corridas), las guardas, `just chat-test` con el token del dueño y la aceptación en hardware de Pipec. El [ADR 0020](../../adr/0020-authorized-actor-in-the-conversation.md) quedó `Accepted`; no abre memoria durable ni cambia el cable.

## Auditoría 0049 (archivada)

El registro de la auditoría [0049 — conformidad de server con sus objetivos](../completed/0049-server-objective-conformance-audit.md) vive desde el 2026-10-19 en `completed/`: sus reparaciones las ejecutó y cerró el Plan 0050 (2026-10-01) y ya no es una propuesta pendiente. Su revisión independiente del 2026-09-23 y 2026-09-24 está en su §13.

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

[0057 — diagnóstico del respaldo del protocolo de streaming](../completed/0057-stream-protocol-diagnosis.md)
**cerró el 2026-10-06** y ya vive en `completed/`: promovido por Pipec ese día con las decisiones D-1 a D-7
confirmadas tal cual, solo diagnostica y no tocó `server/src`. Midió, con reglas de lectura fijadas antes
(820 streams con dos semillas, solo el generador), que la forma de fallo dominante es una etiqueta que comparte
línea con el texto (`tag_same_line`), que quitar el bloque de memoria baja la tasa de respaldo (señal exploratoria
confirmada por una segunda semilla, no una causa), que una respuesta con esquema JSON llega de forma incremental
al cliente y que el defecto de fragmentación no apareció en salida real (0 de 820) pero sigue fijado por un test.
La regla de orden de ejecución saltó en la segunda corrida y queda sin resolver. Ver
[el registro](../../evals/0057-stream-protocol-diagnosis.md). La reparación empieza por el defecto de
fragmentación y está escrita como [Plan 0058](../completed/0058-stream-protocol-repair.md) (ver abajo).

[0058 — reparación del protocolo de respuesta del streaming](../completed/0058-stream-protocol-repair.md) **cerró el 2026-10-07 sin cumplir su compuerta** y ya vive en `completed/`: su código (una gramática tolerante de la etiqueta `EMOTION:` más rescatar como texto plano una respuesta sin etiqueta) quedó solo en la rama `feat/0058-stream-protocol-repair`, sin mergear. Pipec midió que seguían cayendo al respaldo 21 de 60 turnos con contexto en la semilla 57 (35,00 %, compuerta 5 %), 20 de ellos por una etiqueta en la misma línea cuya palabra siguiente no es una emoción. La evidencia está en `docs/evals/0058-stream-protocol-repair.md` (PR solo de documentos, #170, sin mergear).

[0059 — la emoción del usuario se decide aparte](../completed/0059-user-emotion-apart.md) **cerró el 2026-10-08**: Pipec la promovió ese día con sus decisiones D-1 a D-8. El modelo responde en texto plano y la emoción del turno la decide una función pura y prudente sobre lo que dijo el usuario (`user_emotion.classify_user_emotion`; sin segunda llamada al LLM, sin cambio de cable, robot intacto), con las guardas que sobreviven (una etiqueta nunca se habla; un inicio indeciso espera). La compuerta se cumplió en las dos semillas con el código final: 0 de 60 turnos con contexto y 0 de 60 públicos cayeron al respaldo ([registro](../../evals/0059-user-emotion-apart.md)); `just gate` 2315 tests. Una auditoría independiente (dos agentes de solo lectura) no halló nada crítico y sus arreglos están dentro. El [ADR 0018](../../adr/0018-user-emotion-decided-apart.md) quedó `Accepted` y el 0017 `Superseded`. Pipec la aceptó en hardware real el 2026-10-08 (el caso de la memoria no se puede ejercer antes de CM-2). **Pendiente:** el idioma de la respuesta (un turno salió en francés; ningún contrato de streaming pide español y el instrumento no lo mide), la *expresión* facial del robot, un clasificador basado en modelo cuando haya uno mayor, la tasa de extremo a extremo. Al cerrar, `NOW` quedó vacío y CM-2 quedó desbloqueado.

[0060 — capacidades de memoria personal (CM-1)](../completed/0060-cm1-personal-memory-capabilities.md) **cerró el 2026-10-09** y ya vive en `completed/` (se promovió y se ejecutó el mismo día). Es solo política pura y nadie la consume: cinco acciones cerradas, solo dueño y solo datos propios, una garantía mínima por capacidad (`confirm` y `forget` `strong`; `biometric`, `medical` y `location` `strong`; `forget` con un grant PIN gastado y sin consentimiento), dos scopes de grant nuevos y el scope y el estado «gastado» en la evidencia. El [ADR 0019](../../adr/0019-personal-memory-capabilities.md) quedó `Accepted`; al cerrar, `NOW` quedó vacío.

[ADR-0015](../../adr/0015-owner-grant-scope-and-speaker-binding.md) (**Accepted**, 2026-09-25)
liga el grant PIN a una operación (incumplía ADR-0009 hasta el Plan 0051) y, por etapas, a la
evidencia del hablante; el Plan 0051 implementó la decisión 1 como primer plan de CM-1 (cerrado el 2026-10-06).

[0051 — grants del dueño con alcance](../completed/0051-scoped-owner-grants.md) **cerró el 2026-10-06**
(primer plan de CM-1; mergeado como PR #164, `1ecd63c`). Implementa la decisión 1 de ADR-0015:
cada grant queda ligado a una operación (`personal_protected_read` por defecto, `biometric_admin` para
enrolar o revocar cara y voz); un grant presentado a otra operación se rechaza **sin gastarse**;
«¿Quién soy?» y la respuesta «todavía no está conectada» observan al actor y dejan de gastar el grant.
El cambio de contrato es aditivo (`scope` opcional en `POST /auth/owner/unlock`), el robot no cambia y no hay
migración. Pipec lo aceptó en hardware real ([registro](../../evals/0051-scoped-grant-acceptance.md)), con
el caso del PIN que el Plan 0054 dejó sin correr; revocar la cara con un token administrativo (204) no se
corrió. `NOW` quedó vacío hasta que Pipec promovió el Plan 0057 (diagnóstico, 2026-10-06); la reparación del
streaming viene después.

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

Canonical execution order: **`NOW` is empty; [Plan 0065](../completed/0065-cm3b-a-channel-neutral-writer-core.md) closed 2026-10-22 (CM-3b tranche A); [Plan 0068](../completed/0068-short-clip-speaker-measurement.md) closed 2026-10-21 (Tasks 7 and 8 deferred) and [Plan 0069](../completed/0069-stt-owner-voice-audit.md) closed the same day; [Plan 0067](../completed/0067-reply-listening-mode.md) closed 2026-10-19, [Plan 0066](../completed/0066-verb-only-answer.md) closed 2026-10-19, [Plan 0064](../completed/0064-speech-and-dialogue-quality.md) closed 2026-10-19, [Plan 0063](../completed/0063-cm3a-memory-dialogue.md) closed 2026-10-16, [Plan 0062](../completed/0062-cm3a-memory-candidates-and-writer.md) closed 2026-10-15, Plan 0061 closed 2026-10-13 and Plan 0054 (PC-4) closed 2026-09-30.** Plan 0053 (PC-3B)
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
