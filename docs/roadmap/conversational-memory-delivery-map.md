# Mapa de entrega de memoria conversacional

**Estado:** diseño canónico; CM-0 tiene Plan 0046 `Ready`
**Última revisión:** 2026-09-07

## Objetivo

Conectar la visión de memoria autobiográfica longitudinal con el código, las
pruebas y los vacíos observados, sin abrir un segundo sistema de memoria ni
confundir documentación con implementación.

Este mapa profundiza P2.2 del
[roadmap cognitivo](cognitive-roadmap.md) y constituye una dependencia de PC-5
en el [Plan 0015](../plans/open/0015-personal-companion-design.md). No es un plan
ejecutable: cada incremento requiere su propio plan `Ready` y se ejecuta uno a
la vez.

## Resultado deseado

```text
conversación o percepción
          ↓
candidato de memoria
          ↓
atribución, clasificación y política
     ┌────┼─────────┐
  aceptar confirmar rechazar
     ↓
memoria canónica V4
     ↓
recuperación autorizada
     ↓
respuesta con evidencia
     ↓
corrección, historial u olvido completo
```

Recordar más texto no es el objetivo. Cada recuerdo durable debe poder explicar
de quién es, quién lo afirmó, cuál fue su fuente, cuándo fue válido, cuál es su
estado de verdad, quién puede verlo, si es sensible, qué corrige y qué debe
eliminarse al olvidarlo.

## Fractura vigente

El repositorio contiene piezas valiosas, pero las consultas familiares
protegidas y la conversación genérica recorren rutas distintas:

```text
consulta familiar protegida
  -> identidad -> autorización -> memoria V4 -> respuesta determinista

conversación genérica
  -> text_turn legacy -> memoria legacy/semántica -> LLM
```

Evidencia vigente al redactar este mapa:

- `cognition/controller.py` invoca el turno legacy con mensaje y conversación,
  sin transportar el actor resuelto;
- `text_turn.py` habilita memoria persistente legacy solo con evidencia
  `MANUAL`; cara y desbloqueo local no habilitan por sí mismos ese acceso;
- `memory/consolidation.py` escribe episodios y hechos por las APIs legacy, no
  mediante hechos literales o relaciones V4;
- `memory/semantic.py` recupera por archivo, tipo opcional y distancia, sin
  filtros previos por persona, visibilidad, sensibilidad o autorización, ni un
  umbral mínimo de relevancia.

La barrera manual actual contiene accidentalmente parte del riesgo, pero no es
una política suficiente para una memoria personal conversacional.

## Capacidades reutilizables

No debe rehacerse lo que ya existe:

- identidad separada de autorización;
- desconocido como estado válido;
- evaluador de políticas y auditoría;
- hechos y relaciones V4 con estado y vigencia;
- lectura familiar autorizada;
- memoria de trabajo acotada por identidad y sesión;
- extracción local mediante Ollama;
- almacenamiento episódico y búsqueda vectorial SQLite/sqlite-vec;
- pruebas de aislamiento que impiden memoria legacy cuando falta la evidencia
  actualmente exigida.

## Secuencia de entrega

Esta tabla gobierna solamente el subprograma CM-0…CM-7. Su posición entre
biometría, aceptación personal, percepción, RAG, familia y P4.2 está definida
una sola vez en el
[portfolio canónico pre-electrónica](cognitive-roadmap.md#canonical-pre-electronics-delivery-portfolio).

| Etapa | Resultado verificable | Dependencias | Plan ejecutable |
|---|---|---|---|
| CM-0 | Benchmark longitudinal versionado y una corrida RED reproducible | especificación de evaluación | [Plan 0046](../plans/open/0046-reproducible-longitudinal-memory-baseline.md) — `Ready`, no iniciado |
| CM-1 | Capacidades explícitas `read`, `propose`, `confirm`, `correct` y `forget` para memoria personal | política e identidad actuales | no escrito |
| CM-2 | El actor autorizado llega al flujo conversacional sin interpolar nombres ni ampliar permisos implícitos | CM-1 | no escrito |
| CM-3 | La extracción crea candidatos; confirmación/promoción escribe hechos y relaciones canónicos V4 | CM-0, CM-1, CM-2 | no escrito |
| CM-4 | Episodios declaran propietario, visibilidad, sensibilidad, consentimiento y retención | CM-3 | no escrito |
| CM-5 | Recuperación filtra autorización y vigencia antes del prompt y aplica umbral de relevancia | CM-4 | no escrito |
| CM-6 | Corrección y olvido alcanzan hechos, relaciones, episodios, embeddings, resúmenes y cachés derivados | CM-3 a CM-5 | no escrito |
| CM-7 | Escenario real aprende, reinicia, recuerda, corrige, olvida y no divulga | CM-0 a CM-6, PC-3, PC-4 | no escrito |

El orden de producto queda así:

```text
CM-0 benchmark RED (puede ejecutarse primero; no cambia runtime)
  -> PC-3 hablante
  -> PC-4 fusión multimodal
  -> CM-1..CM-7 / P2.2 longitudinal
  -> PC-5 aceptación personal integrada
  -> continuar en P2.1 según el portfolio canónico pre-electrónica
```

Plan 0046 materializa CM-0. La numeración de CM-1 a CM-7 no se reserva: cada
etapa se redactará solamente después de cerrar y reauditar su predecesora.
Las etapas documentales R2/R3 y la familia P3.1/P3.2 no forman parte de esta
subsecuencia de memoria; aparecen en el portfolio maestro y no deben insertarse
como planes CM implícitos.

## Contratos que deberán quedar explícitos

### Lifecycle

`proposed -> confirmed|rejected -> corrected|revoked|expired`, con historial y
procedencia. La extracción automática nunca equivale por sí sola a verdad
personal confirmada.

### Autorización

Las capacidades mínimas son:

- `read_personal_conversation_memory`;
- `propose_personal_memory`;
- `confirm_personal_memory`;
- `correct_personal_memory`;
- `forget_personal_memory`.

La resolución facial, vocal, por PIN o manual aporta evidencia; la política
decide cada capacidad y alcance.

### Recuperación

Persona, visibilidad, sensibilidad, consentimiento, estado y vigencia se filtran
antes de aportar evidencia al LLM. La similitud semántica solo ordena candidatos
ya autorizados y suficientemente relevantes.

### Olvido

Olvidar debe alcanzar el registro canónico y todas sus proyecciones: embeddings,
resúmenes, cachés y material de recuperación. Los logs de seguridad que deban
retenerse conservarán solo la evidencia mínima permitida y no el contenido
olvidado.

## Fuera de alcance

- entrenamiento neuronal propio, JAX o aprendizaje online de pesos;
- DuckDB, microservicios o frameworks de agentes;
- ampliar automáticamente los tokens o permisos vigentes;
- copiar conversaciones completas como verdad durable;
- implementar `care` o `education`;
- usar nube en el camino de runtime.

## Criterio para abrir planes

El primer plan es Plan 0046 para CM-0 y debe observar un fallo reproducible
antes de cambiar el runtime. Cada plan posterior debe tener alcance pequeño,
pruebas RED/GREEN,
comandos de verificación, no-objetivos y revisión independiente. PC-5 permanece
abierto hasta superar CM-7 y su aceptación física completa.
