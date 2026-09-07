# Evaluación de memoria conversacional longitudinal

**Estado:** especificación canónica; suite definida por Plan 0046 `Ready`
**Última revisión:** 2026-09-07

## Propósito

Definir cómo demostrar que Iroko aprende, conserva, actualiza, protege y elimina
recuerdos autobiográficos a través de múltiples sesiones. Esta especificación
evalúa una experiencia completa; no convierte una prueba de extracción ni un
`pytest` verde en aceptación del producto.

La memoria longitudinal forma parte de la aceptación de PC-5. El mapa de
entrega correspondiente está en
[conversational-memory-delivery-map.md](../roadmap/conversational-memory-delivery-map.md).
La primera implementación acotada es
[Plan 0046](../plans/open/0046-reproducible-longitudinal-memory-baseline.md):
construye el instrumento y registra RED, sin corregir todavía el runtime.

## Unidad evaluada

Una ejecución longitudinal debe poder recorrer, con el mismo sujeto autorizado:

```text
aprender
  -> reiniciar el proceso
  -> recordar
  -> corregir
  -> reiniciar nuevamente
  -> recordar la verdad vigente
  -> olvidar
  -> comprobar ausencia y no divulgación
```

Cada caso debe registrar la persona que es sujeto del recuerdo, quién lo afirmó,
la fuente, los tiempos relevantes, el estado de verdad, la visibilidad, la
sensibilidad, la decisión de política y las derivaciones eliminadas.

## Capacidades obligatorias

| Categoría | Pregunta que debe responder la evaluación |
|---|---|
| Extracción | ¿Se propuso el recuerdo correcto sin convertir una inferencia en hecho? |
| Multisesión | ¿Puede recuperarse después de cerrar y recrear la sesión o el proceso? |
| Temporalidad | ¿Distingue cuándo ocurrió, cuándo se afirmó y si sigue vigente? |
| Actualización | ¿Una corrección sustituye la verdad activa sin borrar su procedencia? |
| Abstención | ¿Admite no saber cuando no existe evidencia suficiente y vigente? |
| Procedencia | ¿La respuesta puede vincularse con sujeto, afirmante y fuente correctos? |
| Privacidad entre personas | ¿Una identidad no autorizada queda excluida antes de construir el prompt? |
| Eliminación completa | ¿Olvidar elimina o invalida hechos, episodios, embeddings, resúmenes y cachés derivados? |
| Resistencia a falsos recuerdos | ¿Rechaza negaciones espurias, atribuciones erróneas y contradicciones sin confirmar? |

## Capas de evidencia

La aceptación requiere tres capas, cada una con una responsabilidad diferente:

1. **Pruebas deterministas:** contratos, lifecycle, cardinalidad, autorización,
   filtrado y eliminación.
2. **Evaluaciones con Ollama local:** extracción y verbalización sobre conjuntos
   versionados, con modelo y parámetros registrados.
3. **Escenario real:** `just run-server` y `just run-robot`, usando el contrato
   de audio y la identidad disponible, con reinicios reales entre sesiones.

Las pruebas unitarias o de integración no sustituyen la tercera capa. Una prueba
manual no sustituye los invariantes deterministas de privacidad y borrado.

## Conjuntos mínimos

La suite futura debe incluir al menos:

- preferencias simples y corregibles;
- edades, domicilios y relaciones con vigencia temporal;
- relaciones familiares y de mascotas, incluidas negaciones engañosas;
- datos privados de dos adultos distintos;
- recados `recipient_only` con destinatario autorizado y no autorizado;
- información desconocida para comprobar abstención;
- episodios sensibles cuya eliminación tenga derivados vectoriales;
- evidencia perceptiva que no deba convertirse por sí sola en verdad durable.

Los nombres y datos reales de la familia no deben formar parte del conjunto
versionado. Deben utilizarse identidades y contenidos sintéticos.

## Métricas y resultados

Cada corrida debe producir, como mínimo:

- precisión y recall de candidatos por tipo;
- precisión y recall de sujeto, objeto y relación;
- exactitud de verdad vigente tras correcciones;
- tasa de abstención correcta;
- tasa de divulgación prohibida, cuyo umbral aceptable es cero;
- tasa de eliminación completa de derivados, cuyo umbral aceptable es 100 %;
- latencias p50 y p95;
- proveedor, modelo exacto, cuantización, parámetros, SHA, diff y estado de los
  servicios.

Los umbrales de calidad no deben codificarse solo en este documento: el futuro
plan ejecutable deberá fijarlos junto con el dataset versionado y observar RED
antes de implementar cambios.

## Línea base histórica recuperada

La auditoría del 2026-09-02 produjo evidencia útil, pero **no es una línea base
actual ni aceptación reproducible**: se ejecutó sobre un árbol con cambios
locales y el reporte conversacional quedó en una ruta temporal.

- extracción, 22 conversaciones, modelo
  `qwen3:4b-instruct-2507-q4_K_M`: recall global 0,69; precisión 0,75; recall de
  entidades 0,89; latencia media 27,5 s; máxima 55,2 s; resultado bajo el umbral
  histórico de 0,80;
- fidelidad conversacional, 12 casos, modelo `qwen2.5:3b`: pass rate 58,33 %;
  recall requerido 70,59 %; violaciones prohibidas 8,33 %.

Se observaron pérdidas de relaciones `hijo_de`, `mascota_de` y `pareja_de`,
negaciones falsas, preferencia por información antigua y respuestas que no se
abstuvieron. Estos resultados justifican el benchmark, pero deberán repetirse
sobre un SHA congelado antes de usarlos como comparación.

## Gate longitudinal de PC-5

PC-5 no puede aceptarse hasta que una corrida reproducible demuestre:

1. aprendizaje como candidato y promoción autorizada;
2. recuerdo tras reinicio con procedencia;
3. corrección y recuperación exclusiva de la verdad vigente;
4. olvido con eliminación o invalidación verificable de todos los derivados;
5. no divulgación a otra persona o a un interlocutor desconocido;
6. conversación completa por el camino real servidor/robot.

La respuesta del LLM es presentación de evidencia. La decisión sobre qué
recuerdo está vigente, autorizado o eliminado debe permanecer determinista.

## Evidencia de corrida

Cada reporte futuro debe ser un artefacto versionable o enlazado desde el plan,
e incluir:

- fecha, rama, SHA y `git status`;
- comandos exactos y resultados;
- modelos efectivos y disponibilidad de Ollama;
- dataset y versión;
- tabla por caso, no solo promedios;
- falsos positivos, divulgaciones y residuos después del olvido;
- limitaciones y cualquier intervención manual.

Un reporte temporal, un resultado sin SHA reproducible o una corrida sobre un
árbol mutable se conserva como investigación, no como gate cerrado.
