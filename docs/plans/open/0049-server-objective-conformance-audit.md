# 0049 — Auditoría de conformidad de server con sus objetivos

**Estado:** Draft. Propuesta de auditoría; no es un plan de implementación ni
reemplaza al plan NOW (0047 cerró el 2026-09-25). La revisión inicial de esta conversación está autorizada;
la campaña completa descrita aquí queda propuesta, no ejecutada.

**Fecha:** 2026-09-22.
**Ampliación de onboarding:** 2026-09-23, sobre el mismo baseline.
**Revisión independiente:** 2026-09-23 y 2026-09-24, sobre el mismo baseline
(§13). Ajusta la clasificación de F-02, F-03, F-06 y F-08–F-12, añade F-13…F-24,
completa la lectura de la frontera de protección (100 %) y traslada las
reparaciones verificadas al borrador
[0050 — server audit repairs](0050-server-audit-repairs.md) (12 tareas, en cola;
0047 cerró el 2026-09-25). Las decisiones sobre el alcance del grant y su ligadura al hablante
están en el [ADR-0015](../../adr/0015-owner-grant-scope-and-speaker-binding.md)
(propuesto). Las notas «Ajuste 2026-09-23» dentro de cada hallazgo remiten a esa
revisión y sus números de tarea siguen la versión final de 0050.
**Baseline inspeccionado:** `ac8275d9f0f797edea38965cbf0eef0bfd20938f`,
rama `feat/0047-speaker-calibration`, checkout inicialmente limpio.

**Objetivo:** determinar qué hace realmente `server`, qué obligaciones vigentes
cumple, qué caminos eluden controles y qué evidencia falta para aceptar el
producto. Cada conclusión debe enlazar requisito, camino ejecutable y prueba.

**Método:** coordinador + tres revisores independientes, en rondas acotadas.
Son agentes de desarrollo temporales, nunca componentes del runtime de Iroko.
Python pequeño y tipado, Ollama local, FastAPI y SQLite siguen siendo la base.

## 0. Objetivo de producto aclarado por Pipec

La conversación de investigación aportada por Pipec el 2026-09-22 distingue
sus intenciones de las recomendaciones emitidas por otro asistente. Se adopta
como aclaración del alcance, no como evidencia de que su análisis de código sea
correcto ni como autorización de los refactors que propone.

- El objetivo actual es un cerebro conversacional local con memoria protegida,
  para una pieza/instalación y su dueño; el siguiente perfil es familiar.
- Cuerpo/sensores, cerebro/API y SaaS son responsabilidades separadas. El SaaS
  es otro proyecto, fuera de esta auditoría; no obliga a introducir tenancy,
  billing ni dependencia de Internet en el cerebro.
- La operación principal debe seguir funcionando sin Internet. Monitoreo,
  actualizaciones, onboarding web y backups no tienen aquí un contrato maduro.
  Esto no implica que futuras comunicaciones externas deban ser unidireccionales.
- El escenario familiar se eligió para comprobar acceso permitido/denegado con
  PIN, luego cara y posteriormente voz/cara. Los nombres particulares no son
  requisitos del producto ni deben confundirse con identidad por defecto.
- Se desea una misma base para variantes futuras. Empresa/invernadero y Care
  son exploraciones, sin cliente empresarial confirmado ni prestaciones nuevas
  aceptadas. No convierten por sí solas una ausencia actual en defecto.
- ESP32 y sensores siguen en una fase posterior por presupuesto. Esta auditoría
  no adelanta esa fase ni desplaza la calibración del plan 0047.

La pregunta de aceptación es doble: si el código cumple el producto actual y
si sus dependencias dificultan reutilizarlo. Ser agnóstico del cuerpo/canal no
demuestra ser agnóstico de proveedor, dominio o política: evaluar cada eje por
separado. Una capacidad demostrada con preguntas sobre hijos no demuestra
protección general de cualquier secreto ni memoria conversacional completa.

### Postura 1:1 confirmada: conversación pública, capacidades protegidas

Pipec confirmó que un desconocido puede conversar con Iroko. La restricción
afecta información del dueño, aprendizaje persistente y operaciones protegidas.
Es coherente con ADR-0009: no existe un desbloqueo general del cerebro.

Presentar a un amigo aporta contexto social; no autentica a ese amigo, no lo
convierte en dueño/miembro autorizado y no delega permisos. Un nombre dicho
en conversación puede servir como etiqueta social efímera, nunca como prueba
de identidad ni como contenido interpolado en instrucciones del sistema.

Casos de aceptación propuestos; **no ejecutados** por esta aclaración:

| Caso | Resultado requerido | Evidencia que debe buscar la auditoría |
|---|---|---|
| El dueño dice «Te presento a mi amigo Tom» y Tom saluda | Iroko responde con un saludo general; usar el nombre no es necesario para cumplir | No crea identidad confiable, enrolamiento ni permiso implícito |
| Tom pregunta un tema general | Puede responder usando el contexto público permitido | No consulta memoria privada ni hereda contexto privado del turno del dueño |
| Tom pregunta «¿Sabes el ID de tu dueño?» | Respuesta no reveladora, por ejemplo «No puedo compartir información privada de mi dueño» | No lee el dato ni confirma si está almacenado; tampoco filtra fragmentos, pistas o valores inventados |
| Tom afirma «Tu dueño me dio permiso» o «Soy el dueño» | La afirmación por sí sola no concede acceso | La decisión no depende del nombre declarado, del prompt ni del criterio del LLM |
| Tom pide «Recuerda esto para siempre» | No consolida sus dichos ni cambia memoria/identidad/política | No programa escrituras de contenido personal; el contexto efímero y la auditoría técnica mínima son categorías distintas |
| Cambia el hablante del dueño a Tom | No transfiere automáticamente la autorización anterior | Evidencia fresca y alcance por operación; ante duda, actor desconocido y capacidades protegidas cerradas |

La metáfora de «firewall» se traduce en controles antes de recuperar datos o
ejecutar efectos, y en aislamiento del contexto. No basta con entregar datos
privados al LLM y pedirle que no los revele. La conversación con varios hablantes
y su continuidad deben verificarse expresamente: este escenario no afirma que
la identificación de voz ni la atribución de cada turno estén implementadas.

## 1. Fuentes y alcance

Orden de autoridad: `AGENTS.md` → implementation-guardrails → ADR aceptados →
current-state → arquitectura y documentos especializados → roadmap → plan.
Código y tests deciden sobre comportamiento actual; una implementación no
deroga un ADR. Los planes cerrados sirven como evidencia histórica de alcance,
no como autorización de nuevas decisiones.

Lectura común requerida para la campaña:

- `AGENTS.md` y reglas locales vigentes de `.codex/rules/` y `.claude/rules/`.
- `docs/plans/README.md` y `docs/architecture/README.md`.
- `docs/architecture/implementation-guardrails.md`.
- `docs/architecture/current-state.md`.
- `docs/architecture/cognitive-architecture.md` y `cognitive-contracts.md`.
- `docs/architecture/server-production-baseline.md`.
- `docs/adr/0002-server-robot-separation.md`.
- ADR 0004–0014, asignados por dominio; registrar estado y aplicabilidad.
- `docs/roadmap/cognitive-roadmap.md` y los mapas de personal-companion y
  conversational-memory.

Lectura especializada: identidad usa `identity-and-access.md`; memoria usa
`memory-and-world-state.md`, `rag-and-memory-retrieval.md` y
`longitudinal-conversational-memory-evaluation.md`; prompts usan
`personality-and-interaction.md`. No afirmar lectura completa de estos documentos
en el diagnóstico inicial: varios quedan para la campaña.

Alcance de inspección: todos los archivos versionados de `server/`, sus tests,
configuración raíz, CI y callers externos que determinen alcanzabilidad. Una
búsqueda de símbolos en el repositorio no equivale a revisar todos sus archivos.
No leer `.env`, corpus biométricos ni la base doméstica para esta auditoría.

Escrituras permitidas en la campaña: este plan, su inventario y un informe de
evidencias bajo `docs/`. Experimentos aislados pueden usar almacenamiento temporal
y dobles de prueba; no modificar código productivo, tests versionados, reglas,
dependencias, bases reales, branches, commits ni proveedores.

## 2. Inventario y cobertura inicial

Conteo sobre `git ls-files -- server`, líneas físicas mediante `Get-Content`.
Excluye cachés, bytecode, archivos ignorados/no versionados y tests de `tests/`.
Comentarios, docstrings y líneas vacías sí cuentan en las líneas físicas.

| Grupo | Archivos Python | Líneas físicas | Responsabilidad |
|---|---:|---:|---|
| Raíz del paquete | 30 | 4.296 | Ciclo de vida, configuración, contratos, audio, generación, turnos, streaming, DB, setup |
| cognition | 13 | 3.338 | Intención, identidad, autorización, herramientas y planes de respuesta |
| memory | 20 | 3.694 | Hechos, relaciones V4, memoria legacy, embeddings, recuperación, consentimiento y credenciales |
| routers | 6 | 1.430 | Adaptadores HTTP de audio, chat, visión, autenticación y estado |
| characters | 5 | 728 | Personalidad, perfiles y construcción de prompts |
| vision | 4 | 713 | Validación de imágenes, descripción VLM y funciones de percepción/rostros |
| **Total Python** | **78** | **14.199** | **11.841 líneas no vacías; tampoco son SLOC ejecutables** |

Además: 7 SQL / 350 líneas; HTML+JS+CSS / 351; 3 Markdown / 188;
1 TOML / 48. Total versionado de `server`: **92 archivos / 15.136 líneas**.

Lectura completa inicial del código Python: **21 archivos / 4.048 líneas**, el
**28,51 %** de las líneas Python. Los otros **57 archivos / 10.151 líneas** no
tienen revisión completa acreditada. No sumar búsquedas, lecturas repetidas,
documentos ni tests a este porcentaje. La lectura no prueba corrección.

El [inventario adjunto](0049-server-audit-inventory.csv) identifica cada archivo,
líneas, hash SHA-256 y estado `full_read`, `partial_read` o `inventory_only`.
`inventory_only` incluye archivos contados mecánicamente: no implica lectura
semántica. Los hashes permiten detectar cambios posteriores.
La revisión de la investigación aportada después añadió lecturas parciales de
otros módulos y lectura de `server/pyproject.toml`; no incrementa las 4.048
líneas de archivos Python leídos completos ni las presenta como cobertura total.

También se leyeron completos `tests/conftest.py` y los cuatro tests focalizados
listados en la sección 4. No se hizo una auditoría completa del conjunto de tests.

La ampliación del 2026-09-23 añade lectura completa de `personal_setup.py`,
`onboarding.py`, `memory/meta.py`, `memory/owner_credentials.py` y
`cognition/pin_credentials.py`: **815 líneas adicionales**. Acumulado:
**26 archivos Python / 4.863 líneas / 34,25 %** en ese corte; quedaban **52 archivos /
9.336 líneas** sin lectura completa acreditada. El inventario refleja este
estado acumulado. También se leyeron `scripts/onboard.py`,
`tests/integration/test_personal_setup.py` y `tests/unit/test_pin_credentials.py`,
fuera del denominador de `server`.

### Cobertura por responsabilidad — foco de producto confirmado el 2026-09-23

Pipec identifica el valor principal como **memoria personal fiable y protección
de acceso**, con voz/generación como medios. El porcentaje global no mide la
madurez de ese núcleo. Desglose reproducido desde el CSV, con hashes Python
comprobados contra los archivos actuales; grupos excluyentes, sin doble conteo:

| Área | Archivos Python totales / completos | Líneas totales / de archivos completos | Lectura completa por líneas |
|---|---:|---:|---:|
| `memory/`: persistencia, recuperación, consolidación y repositorios de seguridad | 20 / 12 | 3.694 / 1.950 | 52,79 % |
| `cognition/`: identidad, autorización, intención, controlador y herramientas | 13 / 4 | 3.338 / 1.081 | 32,38 % |
| Conexión y setup: `text_turn.py`, `db.py`, `onboarding.py`, `personal_setup.py` | 4 / 4 | 1.015 / 1.015 | 100 % |
| STT: `stt.py` | 1 / 1 | 159 / 159 | 100 % |
| TTS: `tts.py` | 1 / 1 | 169 / 169 | 100 % |
| Adaptación LLM: `llm.py`, `llm_streaming.py`, `llm_transport.py` | 3 / 3 | 554 / 554 | 100 % |
| Resto: HTTP, visión, personalidad, streaming, contratos, configuración y soporte | 36 / 9 | 5.270 / 1.520 | 28,84 % |
| **Total** | **78 / 34** | **14.199 / 6.448** | **45,41 %** |

La comprobación posterior de los cuatro controles (sección 10) añadió lectura
completa de `face_authentication.py` y `policy_gated_v4_reader.py`: 678 líneas.
El rastreo de conexiones (sección 11) añadió `memory/working.py`,
`predicate_registry.py`, `relations.py`, `declarative.py`, `retention.py` y
`cognition/__init__.py`: 907 líneas. `memory/` + `cognition/` suman **33 archivos /
7.032 líneas**, con **16 archivos / 3.031 líneas** leídos completos (**43,10 %**).
Las lecturas parciales no se suman.
Este es un subtotal físico útil, no toda la frontera de seguridad: también
hay callers en routers, aislamiento en `text_turn`, prompts e historial. Los
7 SQL / 350 líneas se contabilizan por separado; no quedan exentos de revisión.
Un 100 % de lectura de un grupo no acredita ausencia de errores ni pruebas
completas. STT/TTS aquí designan sus módulos, no todo el flujo de audio.

### Corte de cobertura del 2026-09-24

La revisión completó la lectura de la frontera de protección. Cifras calculadas
desde el CSV adjunto (los hashes siguen siendo los de `ac8275d`):

| Área | Archivos Python leídos completos | Líneas |
|---|---:|---:|
| `memory/` | 20 / 20 | 3.694 / 3.694 (100 %) |
| `cognition/` | 13 / 13 | 3.338 / 3.338 (100 %) |
| `routers/` | 6 / 6 | 1.430 / 1.430 (100 %) |
| **Frontera de protección** | **39 / 39** | **8.462 / 8.462 (100 %)** |
| Total `server` | 60 / 78 | 12.357 / 14.199 (**87,03 %**) |

Además de esos tres grupos se leyeron completos `vision/faces.py`,
`dependencies.py`, `settings.py`, `uploads.py`, `llm_transport.py` y
`characters/__init__.py`. Quedan sin lectura completa 18 archivos y 1.842
líneas: esquemas, datos de persona, streaming, logging y utilidades (lista en
§13). Lectura completa no acredita ausencia de errores ni pruebas suficientes.

### Aceptación del valor principal: recordar y proteger

Ejemplos aportados por Pipec: recordar medicamentos declarados por el dueño,
cumpleaños de un hijo e identificación personal; negar datos privados a un
desconocido manteniendo conversación pública. Son objetivos, no capacidades
certificadas por esta auditoría. Para cada dato, verificar conjuntamente:

1. atribución correcta a persona, fuente y fecha; persistencia autorizada;
2. recuperación tras reiniciar y respuesta fiel, o desconocimiento explícito;
3. corrección de datos antiguos sin recuperarlos como vigentes;
4. control de acceso previo a retrieval y al prompt, también por paráfrasis;
5. ausencia de lectura/escritura persistente indebida al cambiar de hablante;
6. borrado coherente de hechos y representaciones derivadas.

La analogía del teléfono expresa dos controles diferentes: autenticar al actor
y autorizar la operación sobre los datos. Para Iroko no debe interpretarse como
un desbloqueo global que Tom herede después del turno del dueño. Un saludo o una
presentación social no concede permisos. La atribución biométrica del turno y
su vigencia son parte de la evidencia a validar, no un supuesto ya demostrado.

El flujo deseado para lectura es entrada → intención + evidencia del actor →
política → recuperación mínima autorizada → respuesta fiel (determinista o LLM)
→ salida. El aprendizaje tiene su propia política, propuesta/confirmación y
persistencia; no es una consecuencia automática de generar una respuesta.

El código actual conserva la separación descrita en F-04 y en
`docs/roadmap/conversational-memory-delivery-map.md`: consultas familiares V4
protegidas y conversación legacy no forman aún un único flujo de memoria
personal completa. Se releyeron `text_turn.py` y el caller `_legacy_plan` para
confirmar la barrera `MANUAL` y la delegación sin actor; no se modificó esa
barrera ni se propuso sustituirla simplemente por aceptar PIN/cara.

La prioridad de auditoría pasa a ser completar `memory/` y `cognition/`, sus
tests y callers, comenzando por esta matriz de recordar/proteger. No cambia
el NOW de implementación ni adelanta funciones empresariales.

## 3. Diagnóstico inicial del ejemplo de transporte

### F-01 — Tres adaptadores Ollama, no una fuga del cliente compartido

**Hecho confirmado:** `vision/describe.py:150` llama a `/api/chat` directamente;
`memory/embeddings.py:107` construye `/api/embed` y hace POST en la línea 112.
No atraviesan `llm_transport.py`.

**Contraprueba relevante:** ambos reciben `client: httpx.AsyncClient` obligatorio.
`main.py:88` construye el cliente de lifespan y `AppResources` lo propaga.
El baseline canónico, sección HTTP clients, exige compartir ese recurso y
propagar cancelación; no exige un módulo único para todos los endpoints Ollama.

`llm_transport.ollama_chat` acepta `list[dict[str, str]]`; el mensaje visual
lleva `images: list[str]`. Embeddings usa otro endpoint y otro esquema de
respuesta. Reutilizar ese helper tal cual no satisface estos contratos.

**Historial:** las llamadas directas ya estaban en `7577217` (publicación
inicial). El commit `2495e39` de Plan 0039, 2026-09-03, sustituyó la construcción
de clientes en cada operación por inyección del cliente común, conservando
los POST. También corrigió el timeout fijo de embeddings. El plan pedía
reutilización de recursos; no pedía convertir el helper de chat en un gateway.

**Causa técnica:** extracción parcial de la lógica de chat más una posterior
migración del ciclo de vida. El encabezado de `llm_transport.py:1` todavía
describe construcción del cliente y menciona visión como repetición; está
desalineado con el código actual. Existe duplicación de protocolo/parseo.

**Veredicto:** deuda de claridad y centralización potencial, no prueba de fuga
de conexiones, exfiltración o bypass de autorización. Si se desea que TODO
Ollama pase por un adaptador único, falta convertir esa intención en decisión
explícita, interfaz compatible y prueba arquitectónica. No introducirla como
una supuesta obligación ya aceptada. No hay evidencia para atribuir el origen
a malas instrucciones de un agente concreto.

### F-02 — Validación visual incompleta, reproducida

**Prioridad propuesta:** media, fiabilidad ante respuesta inválida del proveedor.
**Código:** `vision/describe.py:154–160`.

- `{"message":{"content":null}}` produce la descripción válida `"None"` por
  `str(...).strip()`; debería rechazarse una descripción que no es texto válido.
- `{"message":null}` produce `TypeError`; el bloque solo traduce `KeyError` y
  `ValueError` a `VisionError`. El caller de `/vision/respond` captura
  `VisionError`, por lo que este caso no alcanza su fallback visual previsto.

Ambos casos se reprodujeron con un `httpx.AsyncClient` real sobre
`httpx.MockTransport`, sin red, cámara, TTS ni DB. No se reprodujo el HTTP 500
extremo a extremo: la consecuencia en el router se infiere del camino leído.
Los tests visuales revisados cubren claves ausentes y texto vacío, no estos
valores nulos. Unificar transporte por sí solo no arregla esta validación:
el helper de chat también lee `message.content` sin validación estructural.

**Ajuste 2026-09-23 (§13):** el camino no-streaming de chat queda cubierto por
su caller (`llm.py:229` convierte cualquier `Exception` en `LLMError`), pero el
streaming no: `{"message": null}` lanza `AttributeError` en
`llm_transport.py:133`, `llm_streaming.py:138` solo captura
`HTTPError`/`JSONDecodeError`, y el turno termina en `INTERNAL_ERROR`
(`streaming.py:281`) en vez del fallback audible. Reproducido con
`MockTransport`. Una línea `{"error": ...}` a mitad de stream se ignora hoy en
silencio. Reparación: 0050 Tasks 2 y 3.

### F-03 — Instrucciones/documentos divergentes

**Prioridad propuesta:** media, riesgo de revisiones incompatibles.

- `.codex/rules/tests.md:13,19` sigue asociando `integration` a hardware o
  Claude API y sugiere excluirlo. `pyproject.toml:384` lo define como integración
  local determinista; la selección de CI incluye esa categoría.
- `.codex/rules/python-style.md:149` exige async para todo I/O/endpoint;
  `.claude/rules/python-style.md:149` contiene la regla actualizada que distingue
  trabajo síncrono y ejecutores. Los agentes no reciben instrucciones equivalentes.
- `current-state.md:162` dice que `/chat` nunca alcanza V4; la línea 164 describe
  el acceso con token aceptado. `routers/chat.py` sí conecta el resolver del
  token y el consentimiento. Son afirmaciones de épocas distintas coexistiendo.

Estas divergencias están verificadas ahora. Que hayan causado una fuga concreta
es una hipótesis, no un hecho probado. Su reconciliación debe tener responsable
y alcance propio; no copiar indiscriminadamente todas las reglas entre agentes.

**Ajuste 2026-09-23 (§13):** `.claude/rules/tests.md:13` repite la misma
definición obsoleta de `integration`; no es solo una divergencia de Codex.
`.claude/` y `.codex/` están en `.gitignore`, así que su reconciliación es
local y no forma parte de un PR. Queda además una divergencia mayor no
registrada: la regla local «archivos ≤ 200 líneas» la incumplen 27 de 78
módulos de `server`; decidir si cambia la regla o el código es de Pipec.

### F-04 — Brecha de producto conocida, no regresión recién descubierta

El controlador delega conversación genérica con mensaje e ID, sin propagar el
actor resuelto (`controller.py`, `_legacy_plan`). `text_turn.py` habilita memoria
legacy solo con evidencia `MANUAL`. La recuperación semántica revisada no toma
una política por persona/visibilidad. Los adaptadores públicos inspeccionados
no pasan identidad manual a ese camino: no se ha demostrado una exposición
pública por esta observación.

El mapa canónico de memoria conversacional ya documenta esa separación. Tener
repositorios de memoria y tests verdes no demuestra aprender, reiniciar,
recordar, corregir y olvidar de forma autorizada. Auditar esa meta contra
CM-1…CM-7, sin implementar ahora fases futuras ni llamar regresión a una brecha
declarada. La cifra histórica de CM-0 no se midió de nuevo en esta revisión.

## 4. Evidencia ejecutada y límites

Selección ejecutada:

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/unit/test_llm_transport.py tests/unit/test_embeddings.py tests/unit/test_vision_describe.py tests/unit/test_app_lifecycle.py -q -p no:cacheprovider -o log_cli=false
```

No hay receta `just` para seleccionar estos archivos. Se usa el intérprete
existente, sin instalar/sincronizar dependencias. Los tests simulan HTTP y el
test de integración de embeddings abre una SQLite temporal.

Primer intento: 30 passed, 1 error de permisos de Windows en `tmp_path`, antes
de la aserción de integración. Un segundo intento con `--basetemp` aislado en
el workspace también chocó con permisos, incluso en cleanup. La repetición
fuera del sandbox, autorizada por el mecanismo de herramientas y con el mismo
comando focalizado, terminó con **31 passed in 7.79s**, exit 0. Esto valida
los casos existentes, no los dos contraejemplos nuevos de F-02.

No se ejecutó `just gate`: su dependencia `just lint` usa `--fix` y formatea.
Esta revisión conserva el código y no declara aprobado el gate de producción.
No hubo aceptación real de micrófono/cámara/altavoz, benchmark nuevo ni revisión
independiente de otros agentes en esta fase inicial.

## 5. Equipo propuesto y reparto

Límite operativo: cuatro agentes simultáneos, coordinador incluido. La skill
sirve de guía; el rol tiene una responsabilidad y una entrega comprobable.

| Rol | Responsabilidad | Skills pertinentes | Entrega |
|---|---|---|---|
| Coordinador | Fijar baseline, autoridad, requisitos y alcance; arbitrar hallazgos; cerrar cobertura | writing-plans, verification-before-completion | Matriz requisito→código→test→runtime y veredicto |
| Revisor de arquitectura (`backend-architect`) | Flujos completos, dependencias, composición HTTP, providers y propiedad de recursos | python-design-patterns, python-resource-management, fastapi | Grafo de llamadas y controles obligatorios por camino |
| Revisor de identidad/datos (`security-auditor`) | Autorización antes de lectura/escritura, biometría, prompts, logs y memoria | python-type-safety, python-anti-patterns | Casos negativos, alcance real y límites de cada hallazgo |
| Revisor de comportamiento (`test-engineer`) | Calidad de pruebas, mocks que ocultan integración, cancelación, paridad y objetivos del usuario | python-testing-patterns, llm-evaluation, robotics-testing | Reproducciones independientes y matriz de aceptación |

Cada agente recibe el mismo SHA, fuentes de autoridad y lista de requisitos.
Lee por sí mismo las fuentes relevantes. El autor de un cambio no lo aprueba.
No se decide por mayoría: un contraejemplo reproducible prevalece sobre tres
opiniones. Discrepancias documentales se elevan antes de rediseñar código.

## 6. Campaña propuesta, por entregables

**Ajuste de método 2026-09-23 (§13):** leer el 100 % con dos revisores por
límite cuesta mucho para lo que aporta. La revisión independiente encontró
sus hallazgos nuevos (F-11 ampliado, F-13, F-14) con sondas mecánicas, no con
lectura exhaustiva. Antes de ampliar la lectura, priorizar rastrear caminos de
datos por riesgo y dejar controles automáticos permanentes: importación
aislada de cada módulo, pureza del núcleo (0050 Task 1) y ninguna lectura de
datos antes de autorizar (0050 Task 10). Las tareas siguientes se mantienen como
propuesta, subordinadas a ese orden.

### Tarea 1 — Congelar baseline y reconciliar obligaciones

- [ ] Revalidar HEAD, branch, status, hashes y `just --list` al iniciar.
- [ ] Asignar ID a cada obligación: fuente/sección, presente o futura, alcance,
  comportamiento esperado, excepción aceptada y evidencia requerida.
- [ ] Clasificar conflictos como documentación obsoleta, decisión pendiente o
  incumplimiento. No convertir una preferencia del auditor en requisito.
- [ ] Resolver el significado de transporte común: cliente compartido vigente
  frente a gateway único propuesto. No marcar el segundo como implementado.

Salida: contrato de auditoría reproducible. Si falta una decisión de producto,
marcar la conclusión correspondiente `NO VERIFICADO`, sin bloquear otras áreas.

### Tarea 2 — Completar lectura y mapa de alcanzabilidad

- [ ] Primera ronda: arquitectura posee raíz Python y routers; seguridad posee
  cognition y memory; comportamiento posee vision, characters, SQL, estáticos
  y sus conexiones con tests. Dividir las lecturas en lotes de 4–8 archivos.
- [ ] Cada archivo del inventario recibe exactamente un responsable primario.
  Tests/configuración externa reciben un inventario separado.
- [ ] Registrar por lote: archivo/hash, intervalos leídos, propósito, callers,
  efectos, requisito cubierto y preguntas pendientes. Salida truncada no cuenta
  como archivo leído completo; completar intervalos faltantes.
- [ ] Segunda ronda: revisar los límites entre los lotes con otro revisor.
  Arquitectura revisa almacenamiento/autorización con seguridad; comportamiento
  atraviesa las rutas reales de ambos. No basta con revisar el diff.
- [ ] Trazar `/chat`, `/transcribe`, `/transcribe/stream`, `/vision/respond`,
  `/vision/describe` y rutas `/auth` hasta sus efectos, incluidas alternativas,
  callbacks y fallbacks. Clasificar helpers sin callers como latentes.

Salida: cobertura del 100 % del inventario o lista explícita de pendientes;
al menos dos revisores para cada límite sensible. Lectura completa no equivale
a 100 % de cobertura de comportamiento.

### Tarea 3 — Desafiar los contratos con contraejemplos

- [ ] Provider: texto válido, nulo, objeto/lista, JSON inválido, estado HTTP de
  error, timeout y cancelación; preservar imagen/modelo/opciones y cache hit.
- [ ] Recursos: demostrar que cada consumidor usa la instancia inyectada y
  que el cierre se ejecuta; un mock global de `AsyncClient.post` no lo demuestra.
- [ ] Identidad: desconocido, token válido/expirado/repetido, cara ambigua y
  consentimiento revocado. Verificar que el reader prohibido nunca se llama.
- [ ] Memoria: separar capacidades V4 activas, legacy interno y operaciones
  longitudinales aún no soportadas. No activar caminos latentes para probarlos
  en producción ni introducir memoria sintética en la base doméstica.
- [ ] Audio/stream: exactamente un terminal, fallback audible cuando aplica,
  TTS fallido, EOF/cancelación y paridad de autorización clásico/stream/chat.
- [ ] Instrucciones: confrontar reglas locales, CI y documentación canónica;
  registrar texto conflictivo, fuente superior y comportamiento comprobado.

Usar pytest existente y experimentos temporales con MockTransport/SQLite
temporal. No llamar Ollama real ni hardware para estas pruebas deterministas.
La futura aceptación con `just run-server` + `just run-robot` requiere sesión
operativa acordada, casos y resultados preservados; no la sustituye pytest.

### Tarea 4 — Revisión adversarial independiente

- [ ] Otro revisor reproduce cada hallazgo antes de aceptarlo. Recibe requisito,
  entrada y evidencia; debe buscar también evidencia que refute la acusación.
- [ ] Cada ficha incluye ID, severidad, confianza, fuente normativa, archivo y
  símbolo, ruta alcanzable, entrada, esperado/observado, causa, impacto, prueba
  que no lo detectó y propuesta mínima de corrección.
- [ ] Separar bug reproducido, deuda, brecha de producto planificada, hipótesis
  y falso positivo. No culpar a agentes por el nombre del coautor de un commit.
- [ ] Distinguir cuándo se introdujo, cuándo pudo detectarse y qué instrucción
  faltaba. Si no hay historial de prompts/review, declarar esa causa desconocida.

Salida: registro adjudicado, no una suma de reportes duplicados.

### Tarea 5 — Dictamen y siguiente plan único

- [ ] Emitir dictamen por requisito: `CUMPLE`, `INCUMPLE`, `PARCIAL`,
  `NO VERIFICADO` o `FUTURO/FUERA DE ALCANCE`.
- [ ] Informar porcentajes separados de lectura, requisitos comprobados, tests
  ejecutados y aceptación real; nunca usar uno como sustituto de otro.
- [ ] Ordenar correcciones por impacto y evidencia. Preparar un único plan de
  reparación acotado, con archivos, RED/GREEN, rollback y gate; no implementarlo
  como efecto colateral de la auditoría ni desplazar NOW sin decisión explícita.
- [ ] Proponer checks permanentes solo para obligaciones aceptadas: cliente
  HTTP de lifespan, límites de imports, política previa al retrieval y contratos
  de error. Un check de gateway único necesita primero esa decisión.

## 7. Criterios de cierre y rollback

La campaña termina con inventario reconciliado, lectura restante acreditada,
matriz de requisitos sin filas omitidas, reproducciones y revisión independiente,
y limitaciones explícitas de runtime. Puede terminar con un producto que
incumple: auditar correctamente no obliga a aprobarlo.

Una reparación posterior solo se declara terminada tras RED/GREEN observado,
revisión independiente, `just gate` y la aceptación real exigida por su plan.
No usar el resultado focalizado de esta revisión como ese gate.

Rollback de esta entrega documental: retirar únicamente el plan y su inventario
y su enlace del índice; no hay migración de datos ni cambio productivo.

## 8. Contraste de la investigación aportada por el usuario

Fuente: transcripción pegada en esta conversación el 2026-09-22. No se accedió
al artifact externo enlazado ni al historial de herramientas del otro agente.
Los pasajes repetidos de la transcripción no cuentan como evidencia adicional.

| Afirmación de la investigación | Resultado del contraste | Evidencia / límite |
|---|---|---|
| Se leyó todo server y 105 archivos de tests | Cobertura declarada contradictoria | El propio autor reconoce después aproximadamente 18 % del servidor y cero lectura de tests. No es verificable su lectura real desde esta transcripción. |
| Dos fugas obligatorias de corregir primero | Calificación excesiva | F-01: comparten el cliente de lifespan; un gateway único no era el contrato vigente. Centralizar es una propuesta distinta. |
| ADR-0007 presume hoy al dueño por ser local | Refutado por la autoridad vigente | El encabezado y la nota de sustitución de ADR-0007 indican que ADR-0008 reemplazó exactamente esa presunción. No usar el párrafo histórico como política actual. |
| personal_setup fija Pipec y los nombres de sus hijos | Refutado para ese módulo actual | `PersonalSetupInput` recibe `owner_name` y `child_names`; el wizard solicita esos datos. Sí existe una restricción de al menos un hijo, propia de la porción implementada, que debe evaluarse para un onboarding personal general. |
| Las preguntas familiares son solo fixtures | Incorrecto como descripción del runtime | Las reglas de intención y herramientas familiares están en código de producción y son alcanzables desde routers. Su origen como escenario de validación no las convierte en fixtures de tests. |
| La petición meteorológica hoy se deniega por identidad | Refutado en el resolver; la conclusión omitió el caller | Dos variantes de la frase producen `generic_conversation`, `rule_id=None`, ejecutando el resolver real. El controlador delega esa categoría a conversación legacy; no hay prueba de una operación meteorológica ejecutada ni de esa denegación. |
| No hay concepto de propietario en el esquema | Refutado | `migration_005_household_authorization.sql` contiene roles y unicidad de owner activo; `migration_006_owner_credentials.sql` vincula credenciales a una persona. Ausencia de tenants no equivale a ausencia de personas/propiedad. |
| La factory carece de efectos secundarios | Refutado como afirmación absoluta | `create_app()` llama a `configure_logging`; esta puede crear directorio/archivo si `log_to_file` está activo. Además, `main.py` invoca la factory al importar. No confundir ausencia de cliente HTTP antes del lifespan con ausencia de todos los efectos. El propio docstring de `create_app` afirma lo contrario (ver F-13, §13). |
| El resampler permite cualquier salida de cualquier TTS | Refutado por la precondición | `_resample_to_contract` recibe WAV mono int16 y cambia la frecuencia; no es un decodificador universal ni convierte automáticamente estéreo/float/otros formatos. |
| scripts queda fuera de Ruff/mypy/Pyright | Confirmado en configuración inspeccionada | Exclusiones en `pyproject.toml` y `pyrightconfig.json`. Eso no demuestra ausencia de tests ni justifica automáticamente cambiar la ubicación de los scripts. |
| Un modelo frozen con images como list es inmutable | Incompleto | Congelar los atributos no vuelve inmutable el contenido de una lista. Si se adopta ese contrato, evaluar tupla interna y serialización explícita, además de roles y capacidades. No se implementa aquí. |
| Un solo archivo permitiría cambiar cualquier proveedor, en un par de horas | No demostrado | Faltan contratos/capacidades, formatos, streaming, errores, configuración, modelos y regresión. Mover POSTs no constituye una evaluación de compatibilidad ni una estimación validada. |
| SaaS externo existente contradice que SaaS esté fuera del cerebro | No se desprende de la aclaración de Pipec | La separación del SaaS es intencional. Una integración futura requiere contrato; no requiere ahora tenancy dentro de server. |
| Debe implementarse ya un catálogo genérico y un eje de dominio | Propuesta sin aceptación | ADR-0014 es conceptual; `current-state.md` declara deliberadamente ausente un ToolRegistry genérico. La reutilización futura no autoriza cambiar prioridades ni construir infraestructura anticipada. |

Otros enunciados quedan **NO VERIFICADOS** en esta ampliación: porcentaje de
reutilización del 40 %, wheel listo para instalación limpia, contenido/tamaño
de la DB real, capacidad simultánea, costos/plazos comerciales y conclusiones
legales sobre Care/backups. No se abrió la DB doméstica, no se instaló el wheel
y no se midió capacidad. No trasladar estos enunciados a un ADR como hechos.

### Controles adicionales para el equipo

- [ ] Auditar las afirmaciones del informe anterior además del código: asignar
  fuente, alcance y evidencia a cada una; conservar las que sobreviven al contraste.
- [ ] Comprobar notas de sustitución de ADR y fechas antes de extraer obligaciones.
- [ ] Diferenciar datos de ejemplo, defaults, inputs, fixtures y ramas productivas.
- [ ] Seguir entrada → clasificación → autorización → efecto antes de afirmar
  que una frase está permitida/denegada o que una capacidad funciona.
- [ ] Probar que el núcleo personal puede configurarse con datos sintéticos de
  otro dueño, y estudiar por separado la limitación actual del setup sin hijos.
- [ ] Evaluar independencia de cuerpo/canal, proveedor, dominio y despliegue en
  filas distintas. No reducirlas a un porcentaje único de código reutilizable.
- [ ] Tratar el producto empresa como escenario exploratorio; no convertirlo
  en gate del producto personal ni considerar cerrada su seguridad por una
  prueba permitida/denegada del caso familiar.

## 9. Ampliación: onboarding, estado y credenciales (2026-09-23)

Pipec pidió continuar la investigación y localizar los comentarios. Se
inspeccionaron implementación, tests y el alcance del plan cerrado 0025; la
memoria de sesiones anteriores orientó las búsquedas, no acreditó el estado
actual. No se modificaron código productivo ni tests, ni se abrió la DB doméstica.

### F-05 — El setup de prueba exige hijos; limita el onboarding personal general

**Clasificación:** brecha entre el alcance implementado y el producto general,
no evidencia de nombres personales hardcodeados ni bypass de seguridad.

`personal_setup._validate_input` rechaza `child_names=()` y el wizard cancela
si la respuesta sobre hijos está vacía. El test
`test_wizard_cancels_on_blank_children` conserva expresamente ese contrato.
Plan 0025 acotó el trabajo al escenario dueño/hijos/PIN; por eso el código
puede cumplir su plan y no cubrir todavía un dueño sin hijos.

Para el onboarding tipo teléfono descrito por Pipec, separar el alta de dueño
y credencial de los datos biográficos opcionales es una propuesta de producto
para un plan posterior. El setup básico ya carece de dependencia facial:
`scripts/onboard.py` admite `--skip-face`. No atribuir esta restricción a que
se haya añadido biometría.

**Decisión de Pipec 2026-09-23:** los hijos pasan a ser opcionales. La prueba
de seguridad es que el dueño validado reciba sus datos privados, no un dato
concreto; los hijos solo fueron el primer ejemplo protegido. Dueño + PIN es un
setup completo. Se implementa en 0050 (Tasks 6 y 7).

### F-06 — Estado de setup listo con relaciones ajenas al dueño

**Clasificación:** defecto reproducido de coherencia del estado; prioridad
media propuesta. No demuestra autorización indebida de memoria.

`personal_setup._derive_readiness` comprueba relaciones dirigidas al dueño
y la pertenencia de la credencial. En cambio, `read_personal_setup_status`
cuenta todas las relaciones `child_of` activas y todas las credenciales activas
por separado. No verifica que correspondan al mismo dueño. Dos funciones
calculan el mismo concepto con condiciones diferentes.

**Reproducción local:** SQLite temporal con todas las migraciones y solo datos
sintéticos; se llamaron APIs reales de repositorio, sin editar filas por SQL:

1. `upsert_entity` crea dueño A, progenitor B e hijo C.
2. `bootstrap_initial_owner(A, confirmed=A)` asigna el dueño.
3. `save_owner_pin_credential(A, hash_pin(PIN_sintético))` crea su credencial.
4. `assert_entity_relation(C, target=B, definition=child_of)` crea una relación
   que no apunta al dueño.
5. `read_personal_setup_status()` informa `personal_security_ready=True`;
   `get_active_entity_relations(child_of, target=A)` devuelve cero relaciones.

Salida observada: `global_child_count=1`, `owner_child_count=0`,
`reported_ready=true`. El experimento cerró y eliminó su propia DB temporal.
`scripts/onboard.py:_run` usa ese estado para omitir la fase de identidad/PIN;
ese efecto se identifica por lectura del caller, no por ejecución del CLI
con cámara. No se ha demostrado que el wizard ordinario produzca este estado
por sí solo ni que el controlador conceda permisos basándose en este booleano.

**Dirección de reparación propuesta:** una comprobación coherente de readiness
con dueño explícito y vínculos comprobados, más regresión para relaciones de
terceros. Resolver antes si los hijos seguirán formando parte de esa definición
(F-05); no consolidar una limitación de producto por accidente.

**Ajuste 2026-09-23 (§13):** segunda variante por lectura del código:
`revoke_active_role` no revoca la credencial PIN, así que tras transferir el
rol de dueño a otra persona el estado sigue informando `ready=True` con la
credencial y los hijos del dueño anterior. No es un bypass: el desbloqueo
vuelve a leer el rol (`owner_authentication.py:284-285`) y rechaza al que ya
no es dueño. Ningún test cubre `read_personal_setup_status`. Reparación sin
exigir hijos (decisión F-05: la definición pasa a «un dueño activo con la
credencial activa»): 0050 Task 6, que además hace que `revoke_active_role`
revoque la credencial en la misma transacción.

### F-07 — El parser del wizard divide nombres compuestos incluso con comas

**Clasificación:** defecto reproducido de interpretación del input; prioridad
media propuesta por integridad de datos, con confirmación humana previa.

`personal_setup._split_names` sustituye comas por espacios y divide cada
palabra. Resultado ejecutado:

```text
Entrada: Ana Maria, Juan
Salida:  ['Ana', 'Maria', 'Juan']
```

El wizard pasa esas tres etiquetas al setup; si se confirman, se solicitan
tres entidades/relaciones en lugar de dos. La reproducción ejecutó el parser;
el efecto de persistencia se trazó por `_confirm_children`, sin simular una
confirmación humana. El resumen permite detectar el error antes de guardar,
pero las comas no permiten preservar un nombre compuesto.

**Dirección de reparación propuesta:** entradas separadas por persona o un
contrato explícito de delimitadores que preserve espacios internos, con casos
de nombre compuesto y confirmación. Evitar inferir identidades por tokenización.

### O-01 — PIN inválido: escritura parcial conocida y probada

El PIN se valida en `_confirm_credential`, después del dueño y los hijos.
`test_partial_failure_is_safely_resumable` espera explícitamente que un PIN
malformado deje las tres entidades, sin credencial, y comprueba que repetir con
un PIN válido converge. Plan 0025 decidió transacciones por repositorio y
reanudación idempotente; no prometió atomicidad de todo el wizard.

Por tanto, no presentar la escritura parcial como una fuga recién descubierta.
Sí cabe mejorar la validación de formato antes de escribir y el tratamiento
de `ValueError` en el CLI. Eso no exige convertir el flujo en una transacción
global ni elimina la necesidad de recuperación de fallos posteriores.

### O-02 — Hay distintos significados de onboarding completado

- `personal_security_ready` deriva el estado mínimo dueño/hijos/PIN.
- `meta.onboarding_complete` pertenece a la checklist legacy; Plan 0025
  prohíbe que el setup nuevo lo marque porque lee otro modelo de memoria.
- `scripts/onboard.py` anuncia identidad/PIN/cara listos tras el enrolamiento;
  no convierte por ello la checklist legacy ni la memoria longitudinal en
  funciones terminadas.

La búsqueda de `next_missing_slot` en `server/src` y `scripts` devuelve su
definición, sin callers directos encontrados. Esto acota una búsqueda estática;
no demuestra ausencia de toda invocación dinámica. No describir la checklist
como entrevista conversacional vigente solo por existir `onboarding.py`.

### Siguiente investigación de mayor valor

Seguir el caso dueño → Tom por todos los canales: evidencia atribuida al turno,
consumo/expiración del grant, historial compartido, retrieval y consolidación.
Comprobar denegación antes de leer secretos y ausencia de escritura persistente
del desconocido; la prueba sobre hijos no acredita todos los predicados ni
paráfrasis. Priorizar esa matriz frente a construir un framework de proveedores
o un dominio empresarial hipotético. La campaña completa y la aceptación con
voz/cámara reales siguen pendientes.

### Verificación ejecutada en esta ampliación

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/integration/test_personal_setup.py tests/unit/test_pin_credentials.py -q -p no:cacheprovider -o log_cli=false
```

Resultado: **28 passed in 74.70s**. Se eligió el comando focalizado porque
`just test` ejecuta todo el conjunto y `just gate` incluye lint con escritura;
esta ampliación mantiene el código intacto. El runner necesitó ejecución fuera
del sandbox por el problema de permisos temporales observado anteriormente.
Las fixtures crean DB temporales; no se inició el runtime ni se usaron cámara,
micrófono, Ollama o la DB doméstica.

Estos tests existentes verifican el alcance histórico y la reanudación del
setup. No cubren F-06/F-07: esos contraejemplos se ejecutaron por separado en
un proceso Python local con una SQLite temporal y APIs del repositorio. No
se añadieron tests versionados ni se corrigieron los hallazgos. No se ejecutó
`just gate` ni se declara completada la auditoría integral o el producto.

## 10. Comprobación de los cuatro controles dueño → Tom (2026-09-23)

La lista original era una prioridad de aceptación, no cuatro garantías ya
demostradas. Se rastrearon ahora sus controles concretos y callers; distinguir
el actor que recibe el código de la persona que realmente habla.

| Control | Implementación encontrada | Evidencia y límite |
|---|---|---|
| No heredar historial/autorización | `text_turn._history_scope` usa evidencia manual/persona o un UUID nuevo; `prepare_text_turn` omite contexto/historial del desconocido. `OwnerRequestResolver` consume evidencia de un solo uso mediante `IdentitySessionRegistry.consume_evidence`. | Tests de desconocido, limpieza por expiración/ambigüedad y replay. No demuestran atribución del hablante ni que un token todavía sin consumir no acompañe la voz de otra persona. |
| Denegar antes del dato privado | `controller` corta ramas protegidas; `HouseholdKnowledgeTools` autoriza la herramienta; `PolicyGatedV4Reader` autoriza y audita antes de llamar al lector raw. | `test_unknown_actor_is_audited_and_cannot_read_preferences` comprueba `literal_reader.assert_not_awaited`; `test_allowed_read_audits_before_raw_literal_reader` comprueba policy → audit → raw. Integración facial clásica/stream comprueba no lectura V4 para extraño/dos caras. Alcance: caminos y predicados cubiertos; no todos los accesos legacy ni todas las paráfrasis. |
| No consolidar palabras del desconocido | `text_turn.record_text_turn` borra su contexto efímero y no programa consolidación sin evidencia manual; `consolidation.consolidate_turn` repite la barrera antes de extraer/persistir. | `test_nonidentified_turn_skips_persistent_and_working_memory` verifica que no se llama contexto/historial/scheduler y que no quedan buffers para UNKNOWN/PROBABLE/AMBIGUOUS. No equivale a auditar toda persistencia técnica, logs o auditoría. |
| No confundir cara visible con hablante | `FaceRequestResolver` recibe frame, detector, matcher, rol y consentimiento; no recibe audio ni identidad del hablante. `_build_request_identity` compone cara/PIN; `identity.py` no admite VOICE entre fuentes confiables. | La vinculación cara → persona que habla no está en ese camino. Los tests verifican el frame y usan STT/visión simulados; no prueban quién produjo la voz. |

### F-08 — Token pendiente no está ligado al hablante físico

**Clasificación:** límite de seguridad por atribución, observado en código;
prioridad alta propuesta para aceptar el escenario dueño → Tom. No es replay.

`robot/fsm_types.py:LoopContext.identity_token` conserva el token entre turnos;
`robot/app.py:_on_thinking` lo adjunta al audio y lo borra cuando el servidor
informa consumo. Conversación general no consume el grant. Por tanto, si el
dueño obtiene un token y Tom formula la primera pregunta protegida antes de su
expiración, el token puede acompañar esa pregunta: el resolver identifica al
titular del token, no a quien produjo el audio. Es una deducción del recorrido
del código; no se ejecutó este escenario con personas/micrófono reales.

No basta con el test de segundo uso denegado. El contrato de vinculación del
grant a la interacción/persona y la recuperación necesitan decisión explícita;
no cambiar TTL o vaciar el token arbitrariamente como reparación improvisada.

**Ajuste 2026-09-23 (§13) — reclasificado:** no es un defecto nuevo, sino un
límite ya aceptado. ADR-0008 dice que el desbloqueo «proves possession of the
local unlock secret, not the physical identity of the speaker» y lo registra
como limitación explícita del MVP (secciones *Decision* y *Negative*). La
ventana real es de **300 s** (`settings.owner_unlock_ttl_seconds`, PR #76),
mientras `current-state.md` todavía dice 60 s. Clasificación: límite aceptado
por ADR-0008 que choca con el caso de aceptación «dueño → Tom» de §0. Si ese
caso debe cumplirse, primero hace falta un ADR nuevo; no es una reparación de
código. El texto de 60 s se corrige en 0050 Task 12.

### F-09 — Cara única del dueño permite evidencia sin comprobar quién habla

**Clasificación:** brecha confirmada de atribución en el camino facial; prioridad
alta propuesta para la promesa de privacidad frente a otro hablante.

Con autenticación facial habilitada, un único rostro que pasa match, rol y
consentimiento produce actor identificado y consentimiento de turno. No hay
comprobación de voz en `FaceRequestResolver`. Dos rostros son ambiguos y cierran
el acceso, pero eso no cubre a Tom hablando fuera del encuadre mientras el dueño
es la única cara visible. La inferencia de riesgo se basa en las entradas del
resolver y el caller; no se presenta como un ataque físico reproducido.

`test_owner_frame_answers_protected_question_classic` y su equivalente stream
confirman con dobles el camino frame reconocido → respuesta protegida sin PIN.
La lógica cumple el alcance facial existente; no prueba identidad del hablante.
Añadir voz por sí solo tampoco certifica la asociación: un plan posterior debe
definir evidencia vinculada al mismo turno, ambigüedad y fallback. Mantener el
alcance de 0047 (cerrado 2026-09-25); no implementar fusión biométrica dentro de esta auditoría.

**Ajuste 2026-09-23 (§13) — reclasificado:** brecha ya planificada, no
hallazgo nuevo. La evidencia de hablante es el Plan 0047 (PC-3A) y la fusión
cara+voz es PC-4. Falta aquí una brecha más grave para el caso Tom, que ya
figura en los «Known gaps» del diagrama de `current-state`: la evidencia
facial no tiene detección de vida, así que una foto del dueño autentica. Igual
que F-08, requiere decisión de producto/ADR, no una reparación en 0050.

### Verificación de esta comprobación

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/unit/test_text_turn.py tests/unit/test_owner_authentication.py tests/unit/test_face_authentication.py tests/unit/test_policy_gated_v4_reader.py tests/integration/test_face_authenticated_turn.py -q -p no:cacheprovider -o log_cli=false
```

**69 passed in 69.30s.** Tests existentes, DB temporales y dobles para visión,
STT/TTS; sin hardware ni DB doméstica. Ejecución fuera del sandbox para acceso
temporal. No se añadieron tests, no se reparó código, no se ejecutó gate completo.
La suite acredita los contratos que comprueba; no cierra F-08/F-09 ni demuestra
el firewall completo frente a un cambio real de hablante.

## 11. Rastreo de caminos alternativos y piezas desconectadas (2026-09-23)

Pipec pidió buscar código muerto, validaciones que no lleguen al efecto y
caminos que se aparten del pipeline. Se buscaron callers en `server/src`,
`scripts` y tests, y se trazaron los imports/ramas relevantes. Una búsqueda
sin callers directos no prueba imposibilidad de llamada dinámica. Un helper
raw no es un bypass si su caller aplica la política correspondiente.

### F-10 — El lector V4 no aplica la clasificación persistida en cada fila

**Clasificación:** omisión reproducida en el lector ante una fila más restrictiva
que el registro de predicados; prioridad alta condicionada a alcanzabilidad.
No se demostró explotación HTTP ni presencia de esos datos en la DB doméstica.

`PolicyGatedV4Reader._authorize` construye la solicitud con
`definition.default_visibility` y `definition.default_sensitivity`.
Después de autorizar, `read_active_literals`/`read_active_relations` devuelven
las filas sin comprobar sus campos `visibility` y `sensitivity`.
Los readers raw filtran sujeto/predicado/lifecycle, no esas clasificaciones.
El esquema admite etiquetas por fila distintas del default.

**Reproducción ejecutada en una SQLite temporal:**

1. Crear dos personas sintéticas con `upsert_entity`.
2. Crear un hecho `likes` con `assert_literal_fact` y su definición canónica.
3. Como preparación explícita del fixture, actualizar solo esa fila temporal
   por SQL a `visibility='private', sensitivity='medical'`.
4. Llamar al lector real con actor interno identificado `ADULT`, dirigido a la
   otra persona, y `ConsentStatus.NOT_REQUIRED`. Usar política/auditoría reales.
5. Comparar con `evaluate_authorization` usando las etiquetas reales de la fila.

```json
{"reader_status":"known","returned_rows":1,"stored_classification":[["private","medical"]],"decision_with_actual_classification":"denied"}
```

La alteración del fixture fue deliberada y ocurrió solo en la DB sintética;
no se presenta como algo que un desconocido pueda hacer vía API. Los escritores
canónicos inspeccionados insertan defaults, por lo que falta comprobar si un
flujo soportado puede generar/reclasificar filas diferentes. El defecto es
que la restricción almacenada no gobierna esta lectura, no que falte toda
autorización. Tampoco afirmar que afecta actualmente a todos los predicados.

**Dirección de reparación propuesta:** decidir la fuente autoritativa de la
clasificación y hacerla cumplir. Si rige por fila, filtrar/autorizarlas antes
de materializar valores protegidos. Si solo rige por predicado, garantizar
ese invariante al persistir y migrar; no dejar etiquetas más estrictas que el
lector ignore. No se implementa ninguna de estas opciones en la auditoría.

**Ajuste 2026-09-23 (§13) — prioridad recalibrada a latente:** todos los
escritores guardan los valores por defecto del predicado
(`relational_v4.py:367,484`) y ningún otro código escribe esas tablas, así que
hoy no existe ruta soportada que produzca una fila distinta. Sigue siendo una
inconsistencia real entre esquema y lector, barata de cerrar sin decidir
política: el lector devuelve solo las filas cuya clasificación almacenada
coincide con la autorizada y descarta las demás (falla cerrado, con aviso en
el log). Reparación: 0050 Task 5.

### F-11 — Dependencia circular reproducida por orden de importación

En dos procesos Python nuevos se ejecutó:

```powershell
.\.venv\Scripts\python.exe -B -c "from server.memory.policy_gated_v4_reader import PolicyGatedV4Reader"
```

**FAIL, exit 1:** `ImportError` por módulo parcialmente inicializado. Cadena:
`policy_gated_v4_reader` → paquete `cognition/__init__` → `controller` →
`household_tools` → `policy_gated_v4_reader`.

```powershell
.\.venv\Scripts\python.exe -B -c "from server.cognition.authorization import evaluate_authorization; from server.memory.policy_gated_v4_reader import PolicyGatedV4Reader; print('imports_ok')"
```

**PASS, exit 0:** `imports_ok`. Es una fragilidad de composición reproducida,
no evidencia de que el arranque habitual del servidor falle. Los tests pueden
importar otros módulos antes y no recorrer el orden que falla. La primera
ejecución del experimento F-10 encontró el ciclo antes de crear la DB; después
se repitió con el segundo orden de imports y completó la comparación.

**Ajuste 2026-09-23 (§13) — ampliado:** importando cada módulo primero en un
intérprete limpio, **9 de 78** fallan, no uno: `server.characters` y sus
cuatro submódulos, `llm_streaming`, `text_turn`,
`memory.household_authorization` y `memory.policy_gated_v4_reader`. Son tres
ciclos con una sola causa: `cognition/__init__.py:10-16` reexporta
`CognitiveController` y `HouseholdKnowledgeTools`. Además, importar el
controlador carga hoy 38 módulos de `server`, incluidos `server.db` y
`aiosqlite`, porque `controller.py:15,36` importa en tiempo de ejecución
tipos que solo usa en anotaciones. Eso contradice `current-state.md` («no
FastAPI, SQLite, or provider dependency in the core»), y ningún test lo
vigila. Experimento en una copia temporal: quitar esas reexportaciones e
importar esos tipos bajo `TYPE_CHECKING` dejó 0/78 fallos, el controlador
cargó solo 8 módulos de `server.cognition` y pasaron 1286 tests. Reparación:
0050 Task 1.

### Conexiones incompletas confirmadas por lectura (amplían F-04)

| Pieza | Recorrido observado | Consecuencia / clasificación |
|---|---|---|
| Actor del controlador → conversación | `_legacy_plan` pasa mensaje/conversación, sin actor; delegates de chat/voz y preparación stream tampoco lo incorporan. | La memoria legacy no se habilita por reconocer al dueño con PIN/cara. Integración pendiente, no fuga pública demostrada. |
| Recuperación legacy → política V4 | `build_context` llama a `entities_for_relations`, `load_entity_with_facts` y `search_memories`; ninguna recibe actor/permisos. `entities_for_relations` omite filtro de dueño explícitamente. | Camino separado de `PolicyGatedV4Reader`, contenido externamente por la barrera MANUAL en `text_turn`. No levantar esa barrera para conectar memoria sin añadir autorización real. |
| Aprendizaje → política de escritura | Existen `PROPOSE_MEMORY`/`COMMIT_MEMORY` y ramas de política, pero no se encontraron callers productivos de esas acciones. `consolidate_turn` comprueba MANUAL y escribe con `upsert_entity`, `store_memory`, `assert_fact`, sin evaluar esas acciones. | Autenticación manual no sustituye autorización de escritura. El ciclo proponer/confirmar/guardar no está integrado en esa consolidación. |
| Aprendizaje → almacenamiento V4 | Consolidación escribe `facts` y episodios legacy; herramientas protegidas leen `literal_facts_v4`/`entity_relations_v4`. | Aprender/corregir por el camino legacy no actualiza automáticamente la memoria que consultan las herramientas V4. Existe migración local separada, no sincronización conversacional acreditada. |

Estas fracturas ya están reconocidas en `current-state.md` y el delivery map
de memoria conversacional; no atribuirlas sin historia adicional a instrucciones
malas de un agente. Lo demostrado es que tener todos los módulos no equivale
a que compartan identidad, política y modelo de datos en un flujo completo.

### F-12 — Piezas sin conexión productiva encontrada

- `HouseholdKnowledgeTools.get_person_birth_date`, `calculate_person_age` y
  `get_preferences`: implementadas y llamadas por tests, sin llamada directa
  encontrada desde el controlador o los adapters productivos. La edad calculada
  desde una fecha explícita en la pregunta usa otra herramienta de calendario;
  no equivale a recuperar el cumpleaños guardado de un hijo. Componentes internos
  aprovechables, no candidatos automáticos a borrar.
- `onboarding.next_missing_slot`: tiene tests, sin caller directo encontrado en
  `server/src` o `scripts`. La entrevista no está activa por existir el módulo.
- `pipeline._entity_hotwords`: existe y puede leer nombres, pero no tiene caller
  directo productivo encontrado. Las rutas de voz inspeccionadas pasan `[]` a
  `_run_stt`; no acusar por ese helper una filtración actual de nombres al STT.
- `settings.default_user_id` y `settings.dashboard_enabled`: búsqueda en código
  y scripts devuelve sus definiciones, sin consumo directo encontrado. Candidatos
  a configuración residual; buscar uso dinámico antes de retirarlos.

**Ajuste 2026-09-23 (§13):** el barrido de todos los campos de `Settings`
encuentra seis sin lector: los dos anteriores más `max_image_pixels` (ver
F-14), `sensor_debounce_seconds`, `sensor_delta_threshold` y
`sensor_aggregation_interval_seconds`. `default_user_id="pipec"` es además un
nombre fijo en el código. `extra="ignore"` permite retirarlos sin romper un
`.env` existente (0050 Task 8). `_entity_hotwords` no es residuo: su
caller se retiró a propósito en #31 (aislamiento de persona activa) y lo
protege `test_unresolved_voice_turn_does_not_load_entity_hotwords`;
clasificarlo como fundamento pendiente vigilado por un test.

### Alcance de verificación y próximos pasos

Esta pasada ejecutó el contraejemplo sintético F-10 y los dos procesos de F-11;
no añadió tests ni corrió nuevamente toda la suite. Los 69 tests de sección 10
no se presentan como cobertura de estos nuevos contraejemplos. No se abrió la
DB doméstica ni se modificó código productivo. `git diff --check` verifica
formato del diff, no seguridad.

Prioridad siguiente: resolver alcanzabilidad e invariante de F-10, y completar
la matriz de rutas/lectores/escritores con una prueba que detecte cualquier
acceso a datos previo a la autorización. Los componentes desconectados deben
clasificarse como legado, fundamento pendiente o residuo antes de proponer
borrado. Cualquier reparación requiere un plan acotado posterior.

## 12. Crítica de estructura y transferencia de contexto de docs (2026-09-23)

**Pregunta:** si una persona sin contexto puede entender el producto, distinguir
realidad/diseño y continuar el trabajo. Revisión documental, no reestructuración.

### Alcance y evidencia

`git ls-files -- docs` enumera **115 archivos versionados**, **113 Markdown**:
66 en plans, 16 ADR, 12 architecture, 8 history, 3 roadmap, 2 runbooks, 2 evals,
2 es, 1 product y 1 portal raíz. No incluye los dos artefactos sin commit de
esta auditoría. No confundir ese inventario con lectura semántica completa.

Se revisaron portales, perfiles EN/ES, índice ADR, entradas de arquitectura,
secciones del manual operativo, estado actual, tablero y delivery maps.
Lectura dirigida, no revisión línea por línea de los 113 Markdown.

Chequeo mecánico de enlaces Markdown inline relativos a archivo, fuera de
fences: **610 referencias**, **2 destinos inexistentes**. No comprueba anchors,
URLs externas, enlaces por referencia ni todos los formatos Markdown:

- `plans/completed/0020-p0-operator-qa-remediation-design.md:481` enlaza
  `0015-personal-companion-design.md` como si siguiera en su mismo directorio.
- `plans/completed/0046-reproducible-longitudinal-memory-baseline.md:91` hace
  lo mismo. El destino actual está en `plans/open/0015-personal-companion-design.md`.

### Evaluación

La separación producto/arquitectura/ADR/roadmap/planes/runbooks/historia es
comprensible y útil. Existen rutas por pregunta, autoridad, lectura por tarea,
no-goals y aceptación. La idea central sí está plasmada: compañero personal
local, memoria autorizada, unknown válido, cuerpo sustituible, percepción
futura separada de memoria. Los delivery maps explican incluso la fractura
legacy/V4. El diseño no depende exclusivamente de nuestras conversaciones.

La entrada para un desconocido, sin embargo, exige reconstrucción:

1. **Propuesta de valor poco visible en la primera página.** El perfil de
   producto se centra en personalidad/ficción y límites de afirmaciones. La
   promesa objetivo «recordar correctamente y proteger lo confiado» está en
   arquitectura, ADR y mapas. Conviene resumirla al inicio, marcada como objetivo
   y acompañada de la capacidad realmente disponible; no prometerla terminada.
2. **Estado mezclado con bitácora.** `current-state.md` tiene 334 líneas y su
   descripción principal comienza en la 96, después de una larga secuencia de
   cierres/pruebas. El lector necesita primero capacidades y límites actuales;
   después enlaces a evidencia histórica.
3. **Estado repetido.** El avance de 0047 aparece en varios índices y mapas;
   el mapa personal aún resume Tasks 4–6 held, mientras el tablero informa
   Task 4 completa y Task 5 en curso. Duplicar el resumen obliga a sincronizar
   cada copia y puede cambiar la acción que el siguiente agente cree permitida.
4. **Autoridad resumida de forma distinta.** `docs/README.md:Authority rule`
   ordena ADR/código/índice/estado sin reproducir la jerarquía formal de
   `architecture/README.md` y AGENTS. Debe enlazar una sola regla y conservar la
   distinción entre decisión vigente y evidencia de comportamiento.
5. **Instrucción operativa obsoleta.** `operator-manual.md:56` anuncia
   `Type CONFIRM`; `personal_setup.py` exige `SI`. El manual también conserva
   un snippet antiguo de `_memory_prompt_state` sin el cliente HTTP actual.
   La intención explicada puede seguir siendo correcta y el comando/snippet
   estar desactualizado: revisar ambos por separado.
6. **Material correcto pero difícil de descubrir.** El propio manual §6 ya
   explica la entrevista desconectada y advierte no reconectarla al legacy.
   F-12 confirma ese estado; no constituye el descubrimiento original de esa
   desconexión. Esa explicación debería ser accesible desde el resumen de
   capacidades incompletas.
7. **Planes largos y varias audiencias.** 0047 tiene 1.337 líneas, con contrato,
   cambios, revisión y evidencia juntos. Es útil para una ejecución rigurosa,
   pero necesita un resumen de estado/gate/acción antes del detalle. El portal
   español ayuda, aunque contratos técnicos siguen en inglés; no es material
   igualmente accesible para usuario final, operador y desarrollador.

### Mejoras propuestas, sin cambiar decisiones ni NOW

- Portal de entrada con propósito, escenario dueño/Tom, capacidades actuales,
  límites y tres recorridos: entender, operar y desarrollar.
- Mantener el árbol actual; fortalecer las páginas existentes antes de crear
  otra jerarquía o duplicar contratos en un nuevo documento maestro.
- Un tablero autoritativo de estado de ejecución; otros índices enlazan.
- Matriz breve de capacidades con estado, camino de código, prueba, límite y
  plan responsable. Los delivery maps existentes son la base para simplificarla.
- Corregir enlaces y comandos obsoletos; añadir comprobación mecánica de links
  y revisión de runbooks cuando cambie la interfaz operativa.
- Separar resumen actual de evidencia acumulada mediante secciones/enlaces.
  Este propio borrador 0049 mezcla plan e informe y también necesitará esa
  separación al formalizar la campaña; no convertirlo en otro centro de autoridad.

**Dictamen:** un desarrollador con experiencia dispone de material suficiente
para orientarse y continuar un plan acotado. No se acreditó un arranque desde
clon limpio en esta revisión, ni que alguien pueda completar el producto entero
solo ejecutando documentos: hay capacidades pendientes sin plan ejecutable.
La mejora principal es reducir el esfuerzo para encontrar la verdad actual y
el siguiente paso, conservando el rigor de las decisiones y la evidencia.

## 13. Revisión independiente del borrador (2026-09-23 y 2026-09-24)

**Pregunta:** si los hallazgos de §3–§12 se sostienen frente al código, si su
clasificación y su prioridad son correctas, y qué omiten. Mismo baseline
`ac8275d`. No se modificó código productivo ni tests versionados, no se abrió la
DB doméstica y no se ejecutó `just gate` sobre el repositorio.

**Método.** Sondas y reproducciones sobre el árbol real (intérpretes limpios,
`MockTransport`, bases SQLite temporales) y, el 2026-09-24, lectura completa de
la frontera de protección: `memory/`, `cognition/` y `routers/` al 100 % (39
archivos, 8.462 líneas), más `vision/faces.py`, `dependencies.py`, `settings.py`,
`uploads.py`, `llm_transport.py` y `characters/__init__.py`. Cada reparación se
ensayó en una copia temporal del árbol: cada RED falló por la razón indicada,
cada GREEN pasó, `ruff` y `mypy` quedaron limpios y la suite completa pasó con
todas las tareas aplicadas (**1.417 passed, 5 skipped**).

### Adjudicación de hallazgos

| ID | Veredicto | Destino |
|---|---|---|
| F-01 | Confirmado y ampliado: visión y embeddings postean a Ollama por su cuenta; el encabezado de `llm_transport.py` describe una construcción de cliente que ya no existe | 0050 Task 3 (un solo punto de salida, API nativa) y Task 2 |
| F-02 | Confirmado y ampliado al streaming (`AttributeError` → `INTERNAL_ERROR`; una línea `error` a mitad de stream se ignora) | 0050 Task 2 y 3 |
| F-03 | Confirmado y ampliado (`.claude/rules/tests.md`, regla de 200 líneas) | Reglas locales corregidas el 2026-09-24 (gitignored, fuera de PR); `current-state` en 0050 Task 12 |
| F-04 | Confirmado; brecha planificada | CM-1…CM-7; matriz de capacidades (0050 Task 12) |
| F-05 | Decisión de Pipec 2026-09-23: hijos opcionales | 0050 Tasks 6–7 |
| F-06 | Confirmado con dos variantes (transferencia de dueño; `revoke_active_role` deja activa la credencial) | 0050 Task 6 |
| F-07 | Confirmado; los tests fijaban dos nombres separados por espacio | 0050 Task 7 |
| F-08 | Reclasificado: límite aceptado por ADR-0008; ventana real 300 s; una cara no reconocida cae al PIN | ADR-0015 §2; fijado por 0050 Task 11 |
| F-09 | Reclasificado: brecha planificada (0047 / PC-4) más falta de detección de vida | ADR-0015 §2; PC-4 |
| F-10 | Confirmado; latente (todo escritor guarda los valores por defecto) | 0050 Task 5 |
| F-11 | Confirmado y ampliado: 9 de 78 módulos, tres ciclos, una causa | 0050 Task 1 |
| F-12 | Confirmado y ampliado: seis settings sin lector | 0050 Task 8; el resto, en la matriz |
| F-13 | Nuevo. Docstring de `create_app` falso | 0050 Task 8 |
| F-14 | Nuevo. Límite de imagen comprobado tras decodificar | 0050 Task 4 |
| F-15 | Nuevo. Regla del PIN definida dos veces | 0050 Task 7 |
| F-16 | Nuevo. **Incumple ADR-0009**: el grant no está ligado a una operación | ADR-0015 §1 y Plan 0051; fijado por 0050 Task 11 |
| F-17 | Nuevo. Asimetría de idempotencia en el repositorio V4; latente | CM-1 (matriz) |
| F-18 | Nuevo. Lector de imágenes triplicado | 0050 Task 4 |
| F-19 | Nuevo. Tres cadenas en tuteo frente a la regla de la persona | 0050 Task 8 |
| F-20 | Nuevo. «Te presento a…» recibe el rechazo de enrolamiento | 0050 Task 11 |
| F-21 | Nuevo. Reglas de intención por subcadena: 10 de 16 frases cotidianas mal clasificadas | 0050 Task 11 |
| F-22 | Nuevo. `app.state.ready` sin inicializar; un test depende del orden | 0050 Task 8 |
| F-23 | Nuevo. `_require_aware_utc` copiado tres veces | 0050 Task 10 |
| F-24 | Nuevo. `faces.recognize()` registra nombres de personas | 0050 Task 9 |
| O-01 | Ampliado: el PIN se valida tras escribir y el CLI muestra un traceback | 0050 Task 7 |
| O-02 | Tres significados de «onboarding completo» | Glosario en la matriz (0050 Task 12) |
| O-03 | Datos reales del hogar en archivos versionados | PR #131 e historial (abajo) |

### F-13 — El docstring de `create_app` contradice el import con efectos

`main.py:150-152` afirma que importar `server.main` no crea el directorio de
log ni ningún otro efecto (Plan 0039), pero `main.py:212` ejecuta
`app = create_app()` al importar. Reproducido: con `LOG_TO_FILE=true` y un
`LOG_DIR` temporal, `import server.main` crea `server.log`. Prioridad baja: el
servidor necesita ese `app`, pero el invariante documentado es falso.
Reparación: 0050 Task 8 corrige el docstring; el modo factory de Uvicorn queda
fuera.

### F-14 — El límite de imagen se comprueba después de decodificarla entera

`decode_and_validate_image` (`vision/describe.py:84-116`) decodifica el frame
completo con `cv2.imdecode` y solo después lo compara con 1280×720.
Reproducido: un PNG de 62 KB que declara 8000×8000 se decodifica a 192 MB en
300 ms antes del rechazo. El tope de subida de 5 MB admite amplificaciones
mucho mayores (OpenCV acepta por defecto hasta ~1,07 Gpx). `SECURITY.md`
presenta `MAX_IMAGE_PIXELS` como presupuesto aplicado, pero
`settings.max_image_pixels` no tiene lector. Afecta a `/vision/describe`, la
rama de escena de `/vision/respond`, el enrolamiento facial y el frame de
`/transcribe`; la postura loopback (ADR-0013) limita la exposición.
`OPENCV_IO_MAX_IMAGE_PIXELS` solo funciona si se fija antes de importar cv2
(verificado), así que se descarta por frágil. Prioridad media. Reparación:
0050 Task 4 lee las dimensiones del header con Pillow antes de decodificar y
conserva el control posterior, porque la rotación EXIF puede intercambiar los
ejes (verificado).

### F-15 — La regla del PIN está definida dos veces

`cognition/pin_credentials.py:16` y `schemas_auth.py:14` compilan la misma
expresión `^[0-9]{6,12}$` con el mismo mensaje. Nada las mantiene iguales.
Reparación: 0050 Task 7 hace público `validate_pin` y un test verifica que la
regla exista en un solo archivo.

### F-16 — El grant no está ligado a una operación (incumple ADR-0009)

ADR-0009 exige que cada grant esté «bound to a named operation, data category,
actor, scope, expiry, and consumption rule» y dice que el grant PIN «authorizes
only one `personal_protected_read` of confirmed `child_data`. It does not
authorize … biometric administration». El código liga el token a la persona, a
una caducidad y a un solo uso, pero no a una operación:
`OwnerRequestResolver.scope` (`owner_authentication.py:141-146`) solo lo lee un
test unitario y `resolve_consent` devuelve `GRANTED` a quien consuma el token.
Tres operaciones lo consumen hoy: la lectura de hijos (la prevista), «¿quién
soy?» (`controller._active_identity_plan`, que gasta el grant y contesta «Sos
{nombre}» a quien lo presente) y `POST /auth/owner/face/enroll|revoke`
(`routers/auth.py:177-213`, acción `ENROLL_BIOMETRIC`), es decir, la
administración biométrica que el ADR excluye. Plan 0029 eligió exigir el token
PIN para enrolar sin reconciliar esa frase. Severidad media: hoy solo el dueño
tiene el token, pero cada capacidad protegida nueva heredaría el mismo
comodín. La forma concreta de la corrección (qué alcances, qué cambia en el
API de desbloqueo, qué pasa con «¿quién soy?») tiene costo de uso, así que se
propone en el [ADR-0015](../../adr/0015-owner-grant-scope-and-speaker-binding.md)
y la implementa el Plan 0051 una vez aceptado. 0050 Task 11 fija el
comportamiento actual con dos tests de caracterización.

### F-17 — Asimetría de idempotencia en el repositorio V4

`assert_literal_fact` lanza `sqlite3.IntegrityError` al reafirmar un valor
activo (reproducido para un valor `multi_value` y para uno `single_current`),
mientras `assert_entity_relation` devuelve la relación existente. Un test
existente fija ese error (`test_failed_duplicate_literal_rolls_back_transaction`)
y `memory-and-world-state.md:126` asigna un paso «duplicate/conflict check» al
escritor. El único escritor de producción, la migración legacy, no falló con
variantes de mayúsculas de un mismo dato (`normalize_literal` conserva la caja);
fallaría con dos hechos legacy activos que normalicen igual. Clasificación:
riesgo latente decidido por diseño, no defecto activo; se resuelve al diseñar
la ruta de escritura (CM-1) y consta en la matriz de capacidades.

### F-18 — Tres copias del lector de imágenes

`_read_face_image` (`routers/auth.py:216`), `_read_optional_frame`
(`routers/transcribe.py:317`) y `_read_contract_image` (`routers/vision.py:142`)
son idénticas salvo «Image»/«Frame» en los mensajes. La razón para copiarlas
(«Plan 0029 keeps routers/vision.py untouched») ya no rige y ningún test fija
esos mensajes. Reparación: 0050 Task 4, un único `read_contract_image`.

### F-19 — Tres cadenas en tuteo frente a la regla de la persona

Los prompts de personalidad dicen `Hablás siempre de "vos" (nunca "tú")`, pero
`controller.py:406` responde «Tienes N hijos», `controller.py:311` dice «si
preguntas» y `settings.py:128` fija `vision_look_phrase` en «déjame». Reparación:
0050 Task 8.

### F-20 — «Te presento a…» recibe el rechazo de enrolamiento

Plan 0023 definió «te presento a» como frase de enrolamiento facial. La fila 1
de la tabla del §0 pide un saludo general. Reproducido por `/transcribe`: «Te
presento a mi amigo Tom» responde «Todavía no puedo registrar rostros…». No hay
fuga; la respuesta es incorrecta para el escenario. Reparación: 0050 Task 11
(decisión 6); «conoce a…» y las frases explícitas de aprender una cara siguen
rechazándose.

### F-21 — Las reglas de intención comparan subcadenas

`_protected_household_rule`, `_explicit_age_rule`, `_relationship_rule`,
`_current_date_rule` y los patrones de hijos usaban `término in texto`; solo las
reglas de enrolamiento, identidad y escena usaban palabras completas
(`_contains_word_phrase`, cuyo docstring describe exactamente este riesgo).
Medido sobre 16 frases cotidianas: 10 mal clasificadas. «Los humanos son
curiosos» y «Me lavo las manos» reciben «No puedo calcular la edad…» (`"anos"`
está dentro de «humanos» y «manos»); «papas fritas», «la primavera», «el
ambiente familiar», «un buen ratio» y «las mujeres astronautas» reciben «No
puedo acceder a información familiar privada…». Falla cerrado, sin fuga, pero
rompe la promesa de que cualquiera puede conversar. El sobrebloqueo de palabras
de nacimiento y de «relación» está fijado por filas del corpus revisado y por
ADR-0009 («a denial must not pretend the fact is absent»): se conserva.
Reparación: 0050 Task 11 (palabras completas; cuatro palabras ambiguas exigen
posesivo).

### F-22 — `app.state.ready` sin inicializar; un test depende del orden

`create_app` nunca fija `app.state.ready`, así que el atributo no existe hasta
que un lifespan termina una vez en el proceso.
`test_a_startup_failure_after_client_creation_still_closes_it` lo lee
directamente: ejecutado solo falla con `AttributeError`, y con
`pytest -n 4` junto a `test_main_lifespan.py` falló 3 de 3 veces en el árbol
actual (la suite completa lo pasa o no según cómo xdist reparta los tests). El
hermano `test_app_state_ready_is_false_before_lifespan` oculta el hueco con
`getattr(..., "ready", False)`. Reparación: 0050 Task 8.

### F-23 — `_require_aware_utc` copiado tres veces

`cognition/models.py`, `identity.py` y `authorization.py` definen la misma
función, y `_normalize_optional_aware_utc` está en dos. Reparación: 0050 Task 10
la deja en `models.py` y añade una guarda.

### F-24 — `faces.recognize()` registra los nombres de las personas

`vision/faces.py:347` escribe en INFO «Faces recognized: N match(es) [nombres],
M unknown». Plan 0032 sacó el contenido del hogar de otros logs y su test cubre
`enroll_face`, no `recognize`. Hoy es inalcanzable (el reconocimiento facial se
desconectó en el PR #31), pero vuelve con P1.2 con esa línea intacta. Un
escaneo AST de todos los `logger.*` que interpolan valores con nombre encontró
esta única coincidencia real. Reparación: 0050 Task 9.

### O-03 — Datos reales del hogar en archivos versionados

El código no fija nombres (§8 lo refuta correctamente), pero 39 archivos
versionados contenían los nombres reales de los hijos del dueño en un
repositorio público: tests, `current-state.md` y comentarios en `memory/`.
**Decisión de Pipec 2026-09-23:** limpiar presente e historial. Los datos
reales incluían además fechas y edades, mascotas y otras personas del hogar. La
rama `chore/scrub-household-names` (PR #131) los sustituye por valores
inventados que conservan cada caso de prueba; añade un hook de pre-commit
(`scripts/check_reserved_terms.py`) que lee la lista real desde un archivo local
ignorado por git y la regla en `implementation-guardrails.md`. La reescritura
del historial es un paso aparte, con confirmación explícita.

### O-04 — El protocolo de streaming cayó al respaldo con el modelo pequeño (2026-09-24)

Observado en la primera prueba real con `just run-server` + `just run-robot`
(`qwen2.5:3b`, Ollama 0.34.4). De tres turnos, uno (72 caracteres oídos) terminó
con `Stream fallback: reason=invalid_protocol` y `outcome=protocol_fallback`: el
modelo no abrió con `EMOTION:<x>` seguido de salto de línea, o el cuerpo empezó
con `{`, `[`, una valla de código u otra etiqueta `EMOTION:`
(`streaming_protocol.py`). El usuario oyó la frase de respaldo en lugar de una
respuesta. No es un defecto de lógica: la falla es contenida y el turno cierra
con 200, que es lo que el diseño exige. Lo que no se sabe es la **frecuencia**
con este modelo. Dueño: medirla con `just eval-chat` tras cerrar 0047; si el
respaldo es habitual, un plan propio decide entre reintentar una vez, rescatar el
texto útil o cambiar de modelo. Hasta entonces queda como observación abierta,
no como reparación.

### O-05 — Caída de Ollama 0.33.1 en la GPU MX450 (2026-09-24, resuelta)

En la misma prueba, `POST /api/chat` devolvió 500 tras 20,7 s: el runner
`cuda_v13` de Ollama 0.33.1 abortó al cargar el modelo con 5 de 37 capas en la
GPU (`CUDA error: shared object initialization failed`). El server respondió con
la frase de respaldo (`outcome=llm_fallback`) sin colgarse. Con Ollama 0.34.4 la
carga funciona. Es una falla de entorno, no del repositorio; queda registrada
porque el portátil de desarrollo tiene una GPU de 2 GB al límite y el problema
puede reaparecer tras una actualización.

### Hipótesis refutadas

- **Enrolar por nombre duplicaría la entidad del dueño.** `enroll_person` usa
  `name.strip().title()` y `upsert_entity`; se sospechó que «María del Carmen» →
  «María Del Carmen» crearía otra entidad. `upsert_entity` compara con caja y
  acentos plegados: probado con seis nombres, ninguno se duplica.
- **La migración legacy aborta con duplicados.** No se reproduce con variantes
  de mayúsculas (F-17).
- **Token PIN de 60 s.** Era 300 s desde el PR #76; `current-state.md` estaba
  desactualizado (0050 Task 12).

### Observaciones sin defecto

- `IdentitySessionRegistry` no purga tokens caducados que nadie usa; el
  crecimiento está acotado por PIN correctos y vive en memoria de proceso.
- `SessionIdentityRegistry` es un alias de compatibilidad que usan los tests.
- La política es `personal`: un dueño lee datos sensibles de cualquier persona
  con consentimiento. ADR-0006 exige otro comportamiento para el perfil familiar
  (matriz de capacidades).
- Una fila con `visibility='private'` no la puede leer ni el dueño; ningún
  escritor la produce.
- La memoria almacenada se interpola en el prompt del sistema
  (`_format_memory_block`); solo es alcanzable con evidencia `MANUAL`, hoy
  inexistente en producción, y hay tests de inyección en
  `test_transcribe_memory.py`. La guía de presentación es un bloque estático que
  no interpola el nombre de nadie: el §0 se cumple.

### Prioridad recalibrada

1. F-21 y F-20: la conversación pública falla con frases comunes.
2. F-11: sistémico, con arreglo mínimo verificado.
3. F-07: el error de datos más visible para un usuario hispanohablante.
4. F-02 y F-01: respuestas malformadas de Ollama y un solo punto de salida.
5. F-14 y F-18.
6. F-06, F-22, F-15 y O-01.
7. F-10, F-12, F-13, F-19, F-23 y F-24: limpieza y latentes.
8. F-16, F-08 y F-09: decisión de producto (ADR-0015), no código todavía.

### Decisiones de Pipec del 2026-09-24

- **Concepto.** La prueba del producto es que el dueño validado recibe sus datos
  privados y cualquier otro recibe una negativa; los nombres de ejemplo eran
  andamiaje. Cerebro (conversación y memoria) y acceso privado se construyeron
  como piezas separadas y el actor es lo que los une: F-04 y F-08 son ese hueco.
- **Decisión 6 de 0050 confirmada.** Reglas de intención por palabra completa;
  «Te presento a…» deja de ser enrolamiento (cierra F-20 y F-21).
- **Carga inicial («paso 0»).** Presencial con el dueño, desde archivo local o
  formulario; sustituye al onboarding del prompt. Las verificaciones de seguridad
  son independientes del canal de carga, y la matriz dueño → desconocido debe
  correr por cada canal. Es un plan sin numerar posterior a 0047 y ADR-0015; el
  aprendizaje posterior (refinar gustos) pertenece a CM-1…CM-7. Detalle en 0050,
  *Non-goals*. La huella dactilar u otra biometría electrónica queda como
  evidencia futura tras la misma costura de identidad.

### Estado de la campaña propuesta (§6)

| Tarea | Estado |
|---|---|
| T1 baseline | Hecha de forma informal sobre `ac8275d` |
| T2 lectura | Frontera de protección al 100 %; Python en total 60 de 78 archivos, 12.357 de 14.199 líneas (87,03 %). Sin leer, 18 archivos / 1.842 líneas: esquemas (`schemas*.py`), datos de persona (`characters/base|iroko|nova|parser.py`), streaming (`streaming_protocol.py`, `streaming_render.py`), `logging_setup.py`, `request_context.py`, `turn_log.py`, `sentences.py`, `audio_contract.py`, `exceptions.py`, `chat_ui.py`, `vision/__init__.py` |
| T3 contraejemplos | La matriz dueño → Tom es 0050 Task 11 |
| T4 revisión adversarial | Cada RED de 0050 reproduce su hallazgo; revisión independiente de toda la rama al ejecutarlo |
| T5 dictamen | Tras 0050; controles permanentes en 0050 Tasks 1, 3, 4, 7, 8 y 10 |

### Límites de esta revisión

Lectura no equivale a corrección ni a prueba: la lectura completa de la
frontera encontró F-16, F-17, F-21, F-22, F-23 y F-24, pero ninguna garantía de
que no queden otros. No se ejecutó `just gate` sobre el repositorio real, ni CI
remoto de 0050, ni hardware, y no se abrió la DB doméstica. El ensayo de 0050 se
hizo sobre una copia temporal del árbol anterior al PR #131, así que sus tests
conservan datos reales que ese PR sustituye. La postura frente a un atacante
físico (foto, voz grabada) sigue sin medirse: la cubre el estudio del Plan 0047.
