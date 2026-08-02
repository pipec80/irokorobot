# scripts/archive/

Experimentos descartados. Conservados por valor de aprendizaje, no se ejecutan.

## `sensevoice_test.py` (eliminado 2026-07-27)

Prueba de **SenseVoice** (FunAudioLLM/SenseVoiceSmall) como alternativa a
`faster-whisper` para STT en español + detección de emoción integrada en un
solo modelo.

**Por qué se descartó:**

1. El loader oficial de `funasr` intenta descargar desde **ModelScope**, que no
   es accesible de forma estable fuera de China. El workaround (usar
   `snapshot_download` de HuggingFace + `remote_code` apuntando a `model.py`
   local) funciona pero es frágil y se rompe con cada actualización de `funasr`.
2. `funasr` + `torch` son dependencias pesadas (~2 GB) y no están en
   `pyproject.toml`; vivían en un `[dependency-groups] sensevoice` efímero.
3. La calidad en español no superó a `faster-whisper small` con el
   `initial_prompt` + `hotwords` que ya tenemos en `server/src/server/stt.py`.
4. Las etiquetas de emoción de SenseVoice (`<|HAPPY|>`, `<|SAD|>`, etc.) son
   redundantes: el LLM ya clasifica emoción del usuario en el mismo turno
   (ver `_SYSTEM_PROMPT` en `server/src/server/llm.py`).

**Decisión:** seguimos con `faster-whisper` para STT y dejamos la detección de
emoción al LLM. SenseVoice queda fuera del alcance.

El script del experimento (`sensevoice_test.py`) se eliminó del repositorio
(2026-07-27, decisión de Pipec: "cero aporte al proyecto") — Git conserva su
historial completo si algún día hiciera falta consultarlo.
