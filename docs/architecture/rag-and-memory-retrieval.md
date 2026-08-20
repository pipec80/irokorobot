# RAG, memoria y recuperación híbrida de Iroko

> **Status:** Arquitectura canónica objetivo; no es un plan ejecutable.
>
> **Observed baseline:** 2026-08-20, rama `docs/personal-family-profiles`.
>
> **Principio rector:** Iroko tiene un sistema de memoria. RAG es uno de sus
> mecanismos de recuperación, no el cerebro completo ni una autoridad sobre la
> verdad, la identidad o los permisos.

## 1. Propósito

Este documento conserva y ordena la dirección de RAG y recuperación de datos
para Iroko. Define cómo combinar, cuando corresponda:

- conocimiento estructurado sobre personas, objetos y relaciones;
- recuerdos derivados de conversaciones y experiencias;
- documentos cargados explícitamente, como PDF, Markdown y texto;
- búsqueda semántica mediante embeddings;
- búsqueda lexical para palabras, nombres, códigos y referencias exactas;
- filtros de metadata, tiempo, identidad, autorización y vigencia;
- fusión de candidatos, reranking y selección del contexto;
- generación fundamentada mediante el LLM;
- trazabilidad, corrección, revocación, eliminación y reconstrucción de índices.

El documento no autoriza todavía nuevas tablas, dependencias, endpoints,
modelos, proveedores ni procesos de ingestión. Cada incremento necesita un ADR
cuando cambie una decisión durable y un plan TDD pequeño antes de modificar
código.

## 2. Resultado de producto

La arquitectura existe para que Iroko pueda responder preguntas que requieren
distintas clases de conocimiento sin inventar ni mezclar información privada.

Ejemplo simple y exacto:

```text
Pipec autenticado: “¿Quiénes son mis hijos?”
  -> identidad/autenticación vigente
  -> autorización para relaciones familiares propias
  -> consulta estructurada de relaciones
  -> Máximo y Dominga
  -> respuesta audible
```

Ejemplo compuesto y futuro:

```text
“¿Te acuerdas cuándo cambiamos el sensor de temperatura,
 cuál pusimos y qué dice su manual sobre cómo conectarlo?”

  “¿cuándo?”             -> memoria episódica + tiempo
  “¿cuál pusimos?”       -> hecho/relación estructurada
  “qué dice el manual”   -> recuperación documental
  “cómo conectarlo”      -> búsqueda lexical + semántica
                         -> fusión + evidencia + respuesta
```

El primer ejemplo no debe esperar al RAG documental. El segundo muestra por
qué el sistema final necesita más que una base vectorial.

## 3. Qué es RAG y qué no es

RAG, `Retrieval-Augmented Generation`, es una arquitectura donde el sistema
recupera evidencia externa antes de pedir al LLM que redacte una respuesta.

```text
pregunta
  -> recuperación de evidencia permitida
  -> construcción de contexto acotado
  -> LLM
  -> respuesta fundamentada
```

RAG no es:

- una base de datos específica;
- un modelo de embeddings;
- un LLM;
- sinónimo de memoria;
- una autorización de acceso;
- una garantía automática de verdad;
- aprendizaje o fine-tuning del modelo;
- guardar cada conversación para siempre;
- enviar siempre los primeros `K` vecinos al prompt.

El LLM no “aprende” sus pesos cuando Iroko guarda un recuerdo. En cada turno
recibe evidencia pertinente y autorizada. La memoria puede cambiar sin
reentrenar el modelo, y el índice vectorial puede reconstruirse sin cambiar la
verdad almacenada.

## 4. Estado real observado

La implementación actual ya contiene una base semántica útil:

| Capacidad | Estado observado | Evidencia de código |
|---|---|---|
| Embeddings locales | Implementado | Ollama mediante `memory/embeddings.py`. |
| Modelo configurado | Implementado | `nomic-embed-text` por defecto en `settings.py`. |
| Dimensión vectorial | Implementado/fija | 768 dimensiones en código y `schema.sql`. |
| Caché de embeddings | Implementado | Hash de texto + modelo en SQLite. |
| Memoria vectorial | Implementado | `memories` + tabla virtual `vec_memories`. |
| Búsqueda semántica | Implementado/legacy | KNN `MATCH + k` de `sqlite-vec`. |
| Tipos vectorizados | Implementado | `episodic`, `semantic`, `reflection`. |
| Contexto mixto legacy | Implementado/restringido | Relaciones por palabras, entidades por tokens y búsqueda semántica. |
| Memoria relacional v4 | Implementado/aislado | Entidades, relaciones tipadas y herramientas protegidas. |
| Autorización previa | Implementada para herramientas v4 | No integrada todavía en el retriever semántico legacy. |
| Umbral mínimo semántico | Ausente | Devuelve vecinos por `top_k`, aunque sean débiles. |
| Ingestión PDF/MD/TXT | Ausente | No existe pipeline documental de producción. |
| Búsqueda lexical/FTS | Ausente | No existe índice lexical documental/memoria. |
| Fusión híbrida | Ausente | No existe RRF ni combinación equivalente. |
| Reranking | Ausente | No existe reranker de producción. |
| Citación documental | Ausente | No existe contrato de evidencia documental. |
| Recuperación multimodal | Ausente | Cara usa vectores biométricos separados; no es memoria/RAG. |

`memory/semantic.py` declara que el KNN actual realiza un escaneo de fuerza
bruta adecuado para el volumen esperado menor a 100.000 recuerdos. Por tanto,
no se justifica migrar ahora a PostgreSQL, Qdrant, Milvus o Weaviate. Primero
deben existir un problema medido, un conjunto de evaluación y un ADR.

## 5. Lugar de RAG dentro del cerebro

```text
Audio / texto / visión / sensores
                |
                v
       percepción y evento tipado
                |
                v
        contexto de trabajo actual
                |
                v
 identidad -> autenticación -> intención
                |
                v
          autorización previa
                |
                v
       planificador de recuperación
        /       |       |       \
      SQL    lexical  vector   temporal
        \       |       |       /
         candidatos autorizados
                |
          fusión / reranking
                |
       paquete mínimo de evidencia
                |
     herramienta / respuesta / LLM
                |
        validación y TTS/acción
```

El controlador decide qué clase de evidencia hace falta. El retriever obtiene
candidatos. La política decide qué puede leerse. El LLM expresa resultados
permitidos. Ninguna de esas responsabilidades debe absorber a las demás.

## 6. Capas de memoria y conocimiento

| Capa | Naturaleza | Ejemplo | Recuperación preferida |
|---|---|---|---|
| Contexto de trabajo | Transitoria | pregunta y aclaración actuales | ID de interacción y recencia |
| Hecho declarativo | Literal/confirmado | fecha de nacimiento | SQL exacto |
| Relación | Entidad a entidad | Pipec `parent_of` Máximo | SQL/relaciones |
| Episodio | Evento con tiempo | cambiamos DHT11 por SHT31 | temporal + vector |
| Memoria semántica | Resumen derivado | Pipec usa SHT31 | vector + metadata |
| Hipótesis/reflexión | Inferencia revisable | podría preferir respuestas breves | vector, baja autoridad |
| Documento | Fuente externa versionada | manual SHT31, página 8 | lexical + vector |
| Procedimiento | Pasos controlados | cómo reiniciar un servicio | exacto + documental |
| Mundo actual | Estado con TTL | sensor visible en el taller | estructurado + temporal |
| Percepción | Observación con fuente | herramienta vista en una mesa | multimodal futuro |
| Auditoría | Decisión operativa | acceso denegado | consulta exacta restringida |
| Telemetría | Diagnóstico técnico | latencia o temperatura CPU | consulta operacional |

Estas capas pueden compartir infraestructura física, pero no semántica. Un
vector no convierte una hipótesis en un hecho. Un documento no sustituye el
estado actual. Una conversación no se transforma automáticamente en memoria
permanente.

## 7. Fuentes y representaciones

Una fuente conserva el contenido original y su procedencia. El vector es solo
un índice derivado para encontrarlo.

```text
Fuente original
├── contenido canónico
├── metadata y permisos
├── fragmentos/chunks derivados
├── términos lexicales derivados
└── embeddings derivados
```

Fuentes previstas:

| Fuente | Unidad canónica | Metadata mínima |
|---|---|---|
| PDF | archivo + versión/hash | nombre, hash, página, sección, fecha, propietario |
| Markdown | archivo + commit/hash | ruta, encabezados, sección, versión |
| TXT | archivo + hash | nombre, párrafos, codificación, versión |
| Código | repositorio + commit | ruta, lenguaje, símbolo, líneas, commit |
| Conversación | mensaje/evento confirmado | actor, interacción, tiempo, canal, consentimiento |
| Audio | transcripción autorizada | actor, tiempo, STT/confianza; audio no retenido por defecto |
| Visión | observación tipada | tiempo, cámara, confianza, TTL; frame no retenido por defecto |
| Sensores | lectura/evento tipado | sensor, unidad, ubicación, tiempo, calidad |
| Importación estructurada | registro validado | origen, importador, esquema, confirmación |

El contenido canónico es la autoridad para reconstruir sus índices. Borrar o
revocar una fuente debe invalidar chunks, embeddings, resúmenes y cachés
derivados.

## 8. Ingestión documental

La ingestión ocurre antes de consultar un documento y debe ser repetible.

```text
archivo recibido
  -> autorización y clasificación
  -> identificación/hash
  -> extracción
  -> normalización conservadora
  -> segmentación estructural
  -> chunks
  -> metadata/procedencia
  -> índice lexical
  -> embeddings
  -> publicación atómica de la versión
```

### 8.1 Registro y clasificación

Antes de extraer texto se determina:

- quién incorporó la fuente;
- quién es propietario o sujeto de sus datos;
- visibilidad y sensibilidad;
- retención y posibilidad de exportación/eliminación;
- tipo MIME real, tamaño y hash;
- versión lógica y relación con versiones anteriores;
- si contiene datos personales, biométricos, médicos, infantiles o secretos.

Un archivo no se vuelve confiable por haber sido importado. Su procedencia y
estado deben acompañar cada resultado recuperado.

### 8.2 Extracción

- PDF de texto: preservar página, bloques, títulos y orden de lectura.
- PDF escaneado: OCR es un adaptador opcional; su salida lleva confianza y no
  se presenta como transcripción perfecta.
- Markdown: preservar jerarquía de encabezados, listas y bloques de código.
- TXT: detectar codificación y respetar párrafos.
- Código: segmentar por módulo, clase, función o símbolo; nunca por tamaño a
  ciegas si existe una frontera sintáctica.
- Tablas: conservar encabezados y relación fila/columna; no aplanar de manera
  que se pierda el significado.

Archivos cifrados, corruptos, vacíos, no soportados o demasiado grandes fallan
con un estado explícito. Una ingestión parcial no se publica como completa.

### 8.3 Normalización

La normalización elimina ruido técnico sin destruir información útil:

- espacios repetidos y artefactos de extracción;
- encabezados/pies repetitivos cuando estén identificados con seguridad;
- caracteres de control;
- duplicados exactos de una misma versión.

No se deben borrar acentos, puntuación técnica, códigos, unidades, rutas,
números de pin, identificadores ni estructura de tablas del contenido
canónico. La normalización usada para búsqueda lexical puede ser distinta y
derivada.

## 9. Chunking: unidad de recuperación

La calidad de un RAG depende fuertemente de que cada chunk sea suficientemente
completo para responder y suficientemente pequeño para recuperar con precisión.
No existe un tamaño universal.

### 9.1 Reglas por fuente

| Fuente | Frontera primaria | Contexto que se conserva |
|---|---|---|
| Markdown | encabezado/sección | ruta completa de encabezados |
| PDF técnico | sección/subsección/página | título, página y documento |
| Prosa larga | párrafo/grupo de oraciones | párrafos vecinos cuando sean necesarios |
| Tabla | tabla o subconjunto coherente | encabezados en cada fragmento |
| Código | símbolo sintáctico | firma, clase/módulo, imports relevantes |
| Conversación | episodio significativo | actores, tiempo, resumen y mensajes fuente |
| Procedimiento | paso o grupo inseparable | prerequisitos y advertencias |

### 9.2 Solapamiento

El overlap evita cortar una idea entre chunks, pero duplicarlo en exceso
contamina los resultados y desperdicia contexto. Debe aplicarse solo cuando la
frontera estructural no conserva suficiente continuidad. Los valores se eligen
mediante evaluación local, no por copiar una receta externa.

### 9.3 Identidad estable

Cada chunk necesita un identificador estable derivado de:

```text
source_id + source_version + structural_path + ordinal
```

También conserva:

- texto original del fragmento;
- offsets o páginas hacia la fuente;
- encabezados/jerarquía;
- hash del contenido;
- idioma y tipo de contenido;
- visibilidad, sensibilidad, propietario y sujetos;
- fechas de creación, vigencia, indexación y expiración;
- extractor, chunker y versiones de sus configuraciones.

## 10. Embeddings

Un embedding representa contenido en un espacio numérico donde textos con
significados cercanos pueden tener vectores cercanos. El vector sirve para
recuperar el texto; no reemplaza el texto ni demuestra que una respuesta sea
verdadera.

### 10.1 Contrato del espacio vectorial

Todo índice debe registrar:

- identificador y versión exacta del modelo;
- dimensión;
- distancia usada, por ejemplo coseno o L2;
- normalización aplicada;
- prefijos/instrucciones diferentes para consulta y documento, si el modelo
  los requiere;
- idioma y dominios evaluados;
- versión de preprocesamiento y chunking;
- fecha de construcción.

No se mezclan vectores de modelos, dimensiones o preprocesamientos
incompatibles en el mismo espacio. Cambiar el modelo requiere un índice nuevo,
reindexación controlada, evaluación comparativa y conmutación/rollback; nunca
un cambio en caliente de una variable de entorno sobre la tabla actual.

### 10.2 Política local-first

El baseline usa Ollama y `nomic-embed-text` con 768 dimensiones. Se mantiene
mientras cumpla las evaluaciones en español y el hardware local. Otro modelo
solo se adopta mediante comparación con un conjunto de consultas reales de
Iroko. “Más dimensiones” o “modelo más nuevo” no prueban mejor recuperación.

### 10.3 Caché

La caché actual evita recomputar embeddings, pero el contrato objetivo debe
incluir como clave efectiva contenido completo/hash robusto, modelo, versión,
preprocesamiento y propósito (`query` o `document`) cuando difieran. Una
colisión, modelo retirado, fuente eliminada o cambio de pipeline debe poder
invalidarse de forma determinista.

## 11. Memory Manager

El Memory Manager es una responsabilidad de aplicación, no un agente autónomo
ni una base de datos. Decide qué candidato sigue qué ciclo de vida.

```text
conversación/observación
  -> candidato
  -> clasificar
  -> política de retención
  -> normalizar
  -> buscar duplicado/conflicto
  -> confirmar cuando corresponda
  -> guardar / actualizar / descartar / expirar
  -> construir índices derivados
```

Preguntas mínimas:

1. ¿Es un hecho, relación, episodio, preferencia, estado temporal, hipótesis o
   simple conversación?
2. ¿Quién lo afirmó y a quién se refiere?
3. ¿Es persistente o dejará de ser cierto pronto?
4. ¿Requiere confirmación?
5. ¿Ya existe?
6. ¿Contradice, corrige o reemplaza otro dato?
7. ¿Quién puede leerlo, modificarlo o eliminarlo?
8. ¿Cuándo expira?
9. ¿Debe generar embedding o basta una consulta estructurada?

“Tengo sueño” suele ser estado temporal. “Mi placa es una ESP32-S3” puede ser
un hecho durable confirmado. El LLM puede proponer la clasificación, pero una
política tipada decide la escritura final.

## 12. Comprensión y planificación de consultas

Antes de recuperar, el sistema produce un plan acotado:

```text
RetrievalPlan
├── actor y autenticación vigente
├── intención y subpreguntas
├── categorías de datos solicitadas
├── fuentes permitidas
├── filtros de entidad/tiempo/visibilidad
├── métodos de recuperación
├── presupuesto de candidatos/contexto/latencia
└── política de no resultado
```

Ejemplos:

| Pregunta | Plan preferido |
|---|---|
| ¿Quiénes son mis hijos? | relación SQL exacta; sin vector |
| ¿Qué hablamos ayer del sensor? | actor + tiempo + episodios + vector |
| ¿Qué dice IRK-4821 sobre GPIO 17? | documento + lexical exacto + vector auxiliar |
| ¿Cuándo cambiamos el DHT11? | episodio + temporal + términos exactos |
| ¿Dónde viste esta herramienta? | observaciones visuales/espaciales futuras |
| ¿Cómo conectamos el SHT31? | proyecto + episodios + manual + fusión |

El LLM puede ayudar a dividir una pregunta compleja, pero no decide identidad,
permisos ni la lectura de una categoría protegida.

## 13. Autorización antes de recuperación

El orden obligatorio es:

```text
resolver actor
  -> validar autenticación/expiración/alcance
  -> clasificar acción y categorías solicitadas
  -> evaluar autorización
  -> aplicar filtros obligatorios
  -> recuperar el mínimo permitido
  -> generar respuesta
```

Filtrar después de que el LLM recibió datos es demasiado tarde. El retriever
no recibe un conjunto amplio para luego ocultar resultados. Recibe desde el
inicio el actor, las categorías y el alcance permitidos.

La política de recuperación debe poder expresar:

- sujeto/propietario de la información;
- visibilidad (`public`, `household`, `personal`, `private`, temporal);
- sensibilidad (`child_data`, biométrica, médica, ubicación, seguridad);
- propósito/acción;
- vigencia y consentimiento;
- canal y alcance de autenticación;
- denegación no reveladora.

Un desconocido que pregunta por los hijos no obtiene nombres, cantidad, hits
semánticos ni confirmación de que existe una relación almacenada.

## 14. Mecanismos de recuperación

### 14.1 Estructurada/SQL

Es la primera opción para entidades, relaciones, roles, fechas, estados y
conteos exactos. Ofrece semántica determinista y política verificable.

### 14.2 Lexical

Busca términos exactos y variantes normalizadas. Es especialmente útil para:

- nombres propios;
- códigos como `IRK-4821`;
- modelos como `ESP32-S3-DevKitC-1 N8R2`;
- pines como `GPIO17`;
- direcciones como `0x44`;
- rutas, símbolos de código y mensajes de error.

La implementación futura puede usar capacidades FTS de SQLite si la evaluación
lo justifica. No se introduce PostgreSQL solo para obtener BM25.

### 14.3 Vectorial

Encuentra significado aproximado cuando las palabras cambian:

```text
“cambiamos el sensor de temperatura”
~ “reemplazamos el DHT11 por un SHT31”
```

Debe aceptar filtros de autorización, fuente, entidad, tipo, idioma, tiempo,
vigencia y estado. Un vecino siempre existe matemáticamente; eso no significa
que sea relevante. Por eso se requiere una política explícita de distancia o
relevancia y la posibilidad de devolver cero resultados.

### 14.4 Temporal

Resuelve “ayer”, “la semana pasada”, “la última vez” o intervalos explícitos.
El tiempo no es otro score semántico: se traduce a ventanas, zonas horarias,
vigencia y orden cronológico determinista.

### 14.5 Relacional/grafo lógico

Recorre relaciones entre IDs conocidos:

```text
Pipec -> hermano_de -> Persona A -> parent_of -> Persona B
```

Iroko puede implementar estas consultas inicialmente sobre SQLite relacional.
“Knowledge graph” describe la semántica de entidades y aristas; no obliga a
instalar una base de grafos.

### 14.6 Multimodal futuro

Audio, imagen y escenas necesitan modelos e índices especializados. Un vector
facial es evidencia biométrica separada y jamás se fusiona con memoria textual.
Las observaciones visuales conservan tiempo, lugar, confianza, TTL y fuente.
Solo una política explícita puede promoverlas a episodio durable.

## 15. Recuperación híbrida

“Híbrida” tiene tres sentidos complementarios en Iroko:

1. **Fuentes:** documentos + recuerdos + datos estructurados + percepción.
2. **Búsqueda:** exacta/SQL + lexical + vector + temporal/relacional.
3. **Memoria:** trabajo + hechos + relaciones + episodios + documentos.

El flujo objetivo es:

```text
pregunta autorizada
   ├── SQL/relaciones
   ├── lexical
   ├── vector
   └── temporal
         |
    candidatos con procedencia
         |
    deduplicación y fusión
         |
       reranking opcional
         |
  umbrales + diversidad + presupuesto
         |
      paquete de evidencia
```

### 15.1 Fusión inicial recomendada

Cuando lexical y vector devuelvan rankings con escalas incompatibles, la
primera opción es Reciprocal Rank Fusion (RRF). RRF combina posiciones sin
pretender que distancia vectorial y score lexical significan lo mismo.

Una suma ponderada puede evaluarse después, pero exige normalización y pesos
calibrados por clase de consulta. No se fija un `50/50` por intuición.

Las respuestas estructuradas deterministas no compiten necesariamente en el
ranking: si una herramienta exacta resuelve toda la pregunta, puede terminar
la recuperación. Para preguntas compuestas, su resultado entra como evidencia
de alta autoridad junto con fuentes documentales o episódicas.

### 15.2 Duplicados y diversidad

La fusión debe evitar que cinco chunks solapados del mismo párrafo ocupen todo
el contexto. La selección considera:

- fuente y versión;
- documento/sección/página;
- similitud entre chunks;
- cobertura de subpreguntas;
- autoridad y procedencia;
- recencia cuando sea pertinente;
- diversidad de evidencia, no diversidad artificial de opiniones.

## 16. Reranking

El reranker recibe una lista pequeña de candidatos ya autorizados y los ordena
respecto de la pregunta completa. Es opcional y posterior a una línea base
híbrida medible.

Puede mejorar consultas complejas, pero añade latencia, consumo de memoria y
otro modelo que versionar. No debe:

- ver candidatos que el actor no puede leer;
- transformar un candidato irrelevante en verdad;
- ocultar score, modelo o versión usados;
- impedir devolver cero resultados;
- bloquear el MVP personal autenticado.

Se incorpora solo si mejora métricas y escenarios reales frente a RRF sin
reranking.

## 17. Paquete de evidencia y contexto del LLM

El LLM no recibe filas o chunks anónimos. Recibe un paquete tipado y acotado:

```text
EvidenceBundle
├── query/subquestion
├── actor_scope y decisión de autorización
├── evidencias[]
│   ├── evidence_id
│   ├── source_type/source_id/version
│   ├── contenido mínimo permitido
│   ├── ubicación: página/sección/episodio/relación
│   ├── autoridad/truth_status/confianza
│   ├── timestamps y vigencia
│   └── retrieval_method y scores diagnósticos
├── contradicciones
├── información faltante
└── instrucciones de respuesta/citación
```

Los scores sirven para evaluación y diagnóstico, no se convierten en
afirmaciones al usuario. La confianza de un embedding no es la confianza de un
hecho.

## 18. Generación fundamentada

El generador debe:

- responder solo con evidencia permitida;
- distinguir hecho confirmado, documento, episodio e inferencia;
- conservar incertidumbre y contradicciones;
- no rellenar información ausente;
- citar documentos cuando la interfaz lo permita;
- preferir resultados deterministas para nombres, relaciones, fechas y
  conteos;
- reconocer cuando no hay evidencia suficiente;
- evitar mencionar fuentes protegidas en una denegación.

Respuesta documental futura:

```text
“Según el manual SHT31, sección X, la dirección I²C indicada es 0x44.
 En el diseño de Iroko, el archivo hardware/sensors.md registra…”
```

Respuesta protegida denegada:

```text
“No puedo entregar información familiar protegida sin una autenticación válida.”
```

La segunda respuesta no dice cuántos registros encontró.

## 19. Correcciones, contradicciones y temporalidad

Cuando dos fuentes discrepan, Iroko no elige silenciosamente el chunk con mayor
similitud. Conserva:

- fuentes y versiones;
- estados `active`, `superseded`, `disputed`, `revoked` o `expired`;
- intervalo de validez;
- quién confirmó o corrigió;
- autoridad relativa de la fuente;
- contradicción visible para una aclaración autorizada.

Una nueva versión de un manual no borra la anterior sin registro. Un hecho
actual puede superseder otro manteniendo historia. Un estado como “tengo
sueño” expira en lugar de convertirse en rasgo permanente.

## 20. Eliminación, revocación y reconstrucción

Los índices son derivados. Si una fuente se elimina o pierde autorización:

1. deja de participar inmediatamente en recuperación;
2. se invalidan chunks, embeddings y resúmenes derivados;
3. se eliminan o reconstruyen entradas lexicales/vectoriales;
4. se registra un evento seguro sin copiar el contenido eliminado;
5. las cachés no pueden resucitarlo;
6. backups y restauraciones respetan la política definida.

La reconstrucción debe poder partir de fuentes canónicas todavía autorizadas.
El índice nunca es la única copia de información importante.

## 21. Arquitectura local de almacenamiento

La dirección inicial sigue siendo SQLite + `sqlite-vec`:

```text
SQLite
├── entidades, hechos y relaciones v4
├── recuerdos/episodios y metadata
├── fuentes documentales y chunks futuros
├── índice lexical futuro
├── auditoría y políticas
└── sqlite-vec
    ├── memoria textual
    ├── chunks documentales futuros
    └── índices especializados separados
```

No todos los vectores comparten tabla ni espacio:

- texto documental/memoria;
- código, si requiere modelo especializado;
- imagen/escena futura;
- cara biométrica, ya separada y sensible.

Una migración a otro motor solo se considera si mediciones reales muestran que
SQLite no cumple volumen, latencia, concurrencia, filtrado o calidad. Debe
preservar operación local-first, exportación, eliminación y rollback.

## 22. Observabilidad segura

Registrar para diagnóstico:

- `request_id`/interacción;
- tipo de plan, no el contenido privado;
- métodos activados;
- cantidad de candidatos antes/después de filtros;
- latencias por etapa;
- versiones de índices/modelos;
- resultado `known`, `unknown`, `ambiguous`, `contradictory` o
  `unauthorized`;
- IDs seguros de evidencia cuando la política lo permita.

No registrar en INFO/WARN:

- PIN o token de autenticación;
- texto privado completo;
- nombres o datos infantiles en decisiones denegadas;
- embeddings, audio crudo, frames o perfiles biométricos;
- prompts completos que contengan contexto protegido.

## 23. Evaluación

RAG no se acepta porque “parece responder bien”. Necesita un conjunto versionado
de preguntas, evidencia esperada y resultados prohibidos.

### 23.1 Métricas de recuperación

- `Recall@K`: recuperó la evidencia necesaria;
- `Precision@K`: evitó llenar el contexto con candidatos irrelevantes;
- `MRR`: posición del primer resultado relevante;
- `nDCG@K`: calidad del orden cuando hay varios grados de relevancia;
- tasa de cero-resultados correcta;
- cobertura de subpreguntas;
- latencia y memoria local;
- estabilidad entre versiones.

### 23.2 Métricas de respuesta

- exactitud respecto de la evidencia;
- groundedness: cada afirmación material tiene soporte;
- fidelidad de citas;
- omisiones importantes;
- contradicciones expuestas, no ocultadas;
- alucinaciones;
- cumplimiento de formato y latencia audible.

### 23.3 Métricas de seguridad

- filtraciones de datos no autorizados: objetivo cero;
- acceso al storage antes de autorización: objetivo cero;
- confirmación de existencia en denegaciones: objetivo cero;
- revocados/eliminados recuperados: objetivo cero;
- mezcla entre personas/interacciones: objetivo cero;
- prompts/logs con contenido protegido: objetivo cero.

### 23.4 Conjunto mínimo de escenarios

| Categoría | Ejemplo | Evidencia esperada |
|---|---|---|
| Relación exacta | ¿Quiénes son mis hijos? | herramienta v4, no vector |
| Denegación | desconocido hace la misma pregunta | cero retrieval protegido |
| Paráfrasis | ¿Cuándo reemplazamos el sensor térmico? | episodio correcto |
| Código exacto | ¿Qué dice IRK-4821 de GPIO17? | lexical + documento correcto |
| Temporal | ¿Qué hablamos ayer? | ventana horaria correcta |
| Documento + memoria | ¿Qué placa uso y qué dice su manual? | hecho + documento |
| Resultado débil | pregunta sin evidencia | cero resultados, no top-k forzado |
| Contradicción | dos modelos de placa activos | contradicción explícita |
| Corrección | reemplazo confirmado | versión anterior fuera de respuesta normal |
| Eliminación | fuente borrada | no chunk, embedding, resumen ni caché recuperable |

Los datos de evaluación deben incluir español real de Pipec, errores razonables
de STT, acentos omitidos, nombres, códigos técnicos y preguntas compuestas.

## 24. Fallos y degradación segura

| Fallo | Comportamiento esperado |
|---|---|
| Ollama embeddings no disponible | conservar ruta estructurada; informar que recuerdo semántico no está disponible |
| Índice desactualizado | no mezclar versiones; usar índice válido anterior o fallar explícitamente |
| PDF corrupto/OCR débil | estado de ingestión fallido/parcial, no publicar como completo |
| Cero candidatos relevantes | responder que no hay evidencia suficiente |
| Fuentes contradictorias | mostrar contradicción autorizada y pedir aclaración |
| Reranker caído | degradar a fusión base medida |
| Actor desconocido | excluir fuentes protegidas antes de buscar |
| Token expirado/consumido | denegar sin revelar resultados |
| Fuente eliminada | invalidación inmediata y reconstrucción derivada |
| Presupuesto excedido | reducir candidatos de forma determinista, no cortar permisos/procedencia |

## 25. Secuencia de evolución

Esta arquitectura no cambia la prioridad inmediata del compañero personal.

### R0 — MVP personal autenticado

Completar Plan 0024: Pipec autenticado obtiene “Máximo y Dominga”; sin
autenticación no hay recuperación protegida. Usa relaciones estructuradas, no
RAG documental.

### R1 — Recuperación semántica autorizada

Introducir filtros previos de actor/visibilidad/sensibilidad, umbral de
relevancia, cero-resultados, procedencia y tests de no filtración sobre la
memoria semántica existente.

### R2 — Fuente documental mínima

Agregar un único tipo de fuente prioritario, recomendado Markdown o texto antes
de PDF complejo. Versionar fuente/chunks, recuperar evidencia y mostrar
procedencia. No agregar todavía todos los formatos.

### R3 — Búsqueda lexical e híbrida

Implementar lexical local, línea base vectorial y RRF. Evaluar consultas
semánticas y términos exactos con el mismo corpus autorizado.

### R4 — PDF y calidad avanzada

Agregar PDF de texto, tablas/OCR solo si se necesitan, mejores estrategias de
chunking y reranking únicamente cuando la medición demuestre valor.

### R5 — Memoria Manager y documentos conversacionales

Formalizar candidatos, confirmación, duplicados, contradicciones,
supersession, retención y eliminación propagada.

### R6 — Recuperación multimodal y mundo

Solo después de WorldState y políticas de retención: observaciones visuales,
espaciales, audio y sensores con índices especializados.

Cada etapa tiene su propio ADR/plan/RED-GREEN/gates y aceptación real. No se
implementan R1–R6 dentro del MVP R0.

## 26. Decisiones que requieren ADR futuro

- contrato persistente de fuentes documentales y chunks;
- política de retención y eliminación documental;
- adopción/cambio de modelo o dimensión de embeddings;
- búsqueda lexical y método de fusión;
- incorporación de reranker;
- OCR y retención de archivos originales;
- migración fuera de SQLite;
- recuperación multimodal durable;
- uso opcional de proveedores cloud.

## 27. No objetivos

- convertir cada mensaje en memoria permanente;
- reemplazar SQL/relaciones por vectores;
- crear un framework de agentes o un “Memory Manager” autónomo;
- introducir varias bases de datos antes de medir SQLite;
- indexar biometría junto con documentos o conversaciones;
- usar el LLM como autoridad de identidad, permiso o verdad;
- llenar siempre el contexto hasta `top_k`;
- implementar ingestión, FTS, RRF o reranking desde este documento;
- bloquear el MVP “Máximo y Dominga” esperando el RAG completo.

## 28. Reglas invariantes

1. Identidad no es autorización.
2. Autorización ocurre antes de leer datos protegidos.
3. Structured-first para relaciones, fechas, conteos y estados exactos.
4. Un embedding es un índice derivado, no una verdad.
5. Cero resultados es una respuesta válida.
6. Toda evidencia conserva procedencia, vigencia y política.
7. Fuentes eliminadas o revocadas desaparecen también de derivados.
8. No se mezclan espacios vectoriales incompatibles.
9. Los documentos y recuerdos no se confunden con percepción actual.
10. La calidad se mide con preguntas reales y casos de privacidad.
11. SQLite + `sqlite-vec` sigue siendo la base hasta demostrar lo contrario.
12. RAG mejora generación; no reemplaza el controlador cognitivo.

## 29. Glosario

| Término | Definición en Iroko |
|---|---|
| Fuente | contenido canónico con procedencia y política |
| Chunk | fragmento derivado y recuperable de una fuente |
| Embedding | vector derivado para similitud semántica |
| Vector search | recuperación aproximada por cercanía matemática |
| Lexical search | recuperación por términos/palabras exactas |
| Metadata filter | restricción determinista por actor, fuente, tiempo o categoría |
| Hybrid search | combinación de varios métodos/fuentes de recuperación |
| RRF | fusión por posiciones de rankings heterogéneos |
| Reranker | modelo o regla que reordena candidatos ya autorizados |
| Grounding | soporte explícito de la respuesta en evidencia |
| RAG | recuperación de evidencia antes de generación |
| Memory Manager | servicio/política que gobierna ciclo de vida de recuerdos |
| Knowledge graph | semántica de entidades y relaciones; no exige una base especial |
| WorldState | representación expirable de lo probablemente cierto ahora |
| Provenance | origen, versión y cadena de transformación de un dato |

## 30. Documentos relacionados

- [Memoria, relaciones, onboarding y world state](memory-and-world-state.md)
- [Identidad, acceso y consentimiento](identity-and-access.md)
- [Arquitectura cognitiva](cognitive-architecture.md)
- [Contratos cognitivos](cognitive-contracts.md)
- [Estado actual](current-state.md)
- [Roadmap cognitivo](../roadmap/cognitive-roadmap.md)
- [MVP de memoria personal autenticada](../plans/open/0024-owner-authenticated-memory-mvp-design.md)
- [ADR 0008 — autenticación progresiva](../adr/0008-progressive-owner-authentication.md)
