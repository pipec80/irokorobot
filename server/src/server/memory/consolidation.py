"""The benchmark's extraction seam: one local-model call over a whole exchange.

``consolidate_turn`` — the ``MANUAL``-gated writer of the legacy tables — is gone (ADR 0021
decision 11, Plan 0062): it never ran in production, wrote around the authorization policy and
stored the whole turn as an episode. What stays is the prompt and ``_extract_via_ollama``, which
``just eval-memory`` (``scripts/eval_consolidation.py``) calls directly and the CM-0
benchmark (``just eval-longitudinal``) calls through
``scripts/eval_consolidation.extract_case_items``, behaviourally unchanged, so the baseline
stays comparable until CM-3b replaces it. Nothing under ``server`` calls it at runtime.

The candidate path of CM-3a has its own extractor (``candidate_extraction``), which sees only
the user's words.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from server.exceptions import LLMError
from server.llm_transport import ollama_chat, strip_json_fences
from server.schemas import TurnExtraction
from server.settings import settings

if TYPE_CHECKING:
    import httpx

_EXTRACTION_SYSTEM = """\
Eres un extractor de información de conversaciones para la memoria de un \
robot asistente personal.

Analiza el último intercambio (user + assistant) y extrae:
1. ENTIDADES: personas, lugares, objetos, eventos, preferencias, horarios.
2. HECHOS: triples (subject, predicate, object) que expresen información persistente.
3. RESUMEN EPISÓDICO breve si el turno es memorable; si no, null.
4. IMPORTANCIA 0.0-1.0.

Reglas:
- Extraé SOLO información dicha por [user]. El texto de [assistant] es
  contexto — NUNCA una fuente de hechos.
- NO inventes información ausente del texto.
- Usá SOLO estos predicados canónicos (snake_case, español):
  nombre, fecha_nacimiento, edad, vive_en, trabaja_en, hijo_de, pareja_de,
  mascota_de, especie, le_gusta, odia, prefiere, alergico_a.
  Si un hecho no encaja en ninguno de ellos, NO lo emitas.
- Para preferencias: subject="usuario", predicate="le_gusta"|"odia"|"prefiere".
- Hijos con nombre propio: extractá CADA UNO como entidad separada de tipo "person".
  En el hijo: predicate="hijo_de", object=nombre del progenitor.
  NO agrupes varios hijos bajo un único hecho en el padre/madre.
- Mascotas: entidad de tipo "other" con DOS hechos:
  predicate="especie", object=perro|gato|otro Y predicate="mascota_de",
  object=nombre del dueño.
- Si el usuario dice que NO tiene pareja/hijos/mascotas: emití el hecho
  subject="usuario", predicate correspondiente (pareja_de|hijo_de|mascota_de),
  object="ninguno". NO crees entidades para eso.
- Si se menciona fecha de nacimiento: predicate="fecha_nacimiento".
- Fechas, edades y números NUNCA son entidades — son el object de hechos
  (fecha_nacimiento, edad) sobre una persona.
- le_gusta/odia/prefiere JAMÁS llevan una persona como object.
- Si el turno es trivial (saludos sin información nueva), retorna listas vacías.

Ejemplo — [user] "tengo dos hijos, uno se llama Joaquín, tiene 9 años, nació
el 14 de octubre de 2016" produce EXACTAMENTE:
  entities: [{"name": "Joaquín", "type": "person"}]
  facts: [
    {"subject": "Joaquín", "predicate": "hijo_de", "object": "usuario"},
    {"subject": "Joaquín", "predicate": "edad", "object": "9"},
    {"subject": "Joaquín", "predicate": "fecha_nacimiento", "object": "14 de octubre de 2016"}]
Sin entidades para "9 años" ni para la fecha.

Responde SOLO con JSON válido conforme al schema. Sin comentarios.\
"""


async def _extract_via_ollama(
    client: httpx.AsyncClient, user_text: str, assistant_text: str
) -> TurnExtraction:
    """Call Ollama with ``format=json`` to extract structured data from a turn.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039).
        user_text: The user's message in the current turn.
        assistant_text: The robot's response in the current turn.

    Returns:
        Validated ``TurnExtraction`` Pydantic model.

    Raises:
        LLMError: If the model returns malformed JSON.
        httpx.HTTPError: If the Ollama HTTP call fails.
    """
    model = settings.consolidation_model or settings.ollama_model
    raw = await ollama_chat(
        client,
        [
            {"role": "system", "content": _EXTRACTION_SYSTEM},
            {
                "role": "user",
                "content": f"Conversación:\n[user] {user_text}\n[assistant] {assistant_text}",
            },
        ],
        model=model,
        format_schema=TurnExtraction.model_json_schema(),
        options={"temperature": 0.1},
        timeout=settings.ollama_timeout_s,
    )
    text = strip_json_fences(raw)
    try:
        return TurnExtraction.model_validate_json(text)
    except ValueError:
        # `from None` and no `{exc}`: a pydantic error quotes the offending input, which is the
        # model's own output about the household; it must not reach a log line.
        raise LLMError("Extraction returned invalid JSON") from None
