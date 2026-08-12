"""Extract entities, facts, and episodic memories from a conversation turn.

Runs as a FastAPI ``BackgroundTask`` — the caller has already returned a
response to the user. All errors are caught, logged, and swallowed so that
consolidation failures are never visible to the user.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    IdentityEvidenceSource,
)
from server.exceptions import LLMError
from server.llm_transport import ollama_chat, strip_json_fences
from server.memory.declarative import assert_fact, find_entities_by_name, upsert_entity
from server.memory.normalize import normalize_extraction
from server.memory.semantic import store_memory
from server.schemas import EntityType, TurnExtraction
from server.settings import settings

logger = logging.getLogger(__name__)

_LOW_IMPORTANCE = 0.2
_RETRY_DELAY_S = 5.0
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

Ejemplo — [user] "tengo dos hijos, uno se llama Máximo, tiene 10 años, nació
el 29 de diciembre de 2017" produce EXACTAMENTE:
  entities: [{"name": "Máximo", "type": "person"}]
  facts: [
    {"subject": "Máximo", "predicate": "hijo_de", "object": "usuario"},
    {"subject": "Máximo", "predicate": "edad", "object": "10"},
    {"subject": "Máximo", "predicate": "fecha_nacimiento", "object": "29 de diciembre de 2017"}]
Sin entidades para "10 años" ni para la fecha.

Responde SOLO con JSON válido conforme al schema. Sin comentarios.\
"""


async def _extract_via_ollama(user_text: str, assistant_text: str) -> TurnExtraction:
    """Call Ollama with ``format=json`` to extract structured data from a turn.

    Args:
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
    )
    text = strip_json_fences(raw)
    try:
        return TurnExtraction.model_validate_json(text)
    except Exception as exc:
        raise LLMError(f"Extraction returned invalid JSON: {exc}") from exc


async def _extract(user_text: str, assistant_text: str) -> TurnExtraction:
    """Extract locally with Ollama, retrying once on a transient failure.

    Transient failures (model still loading or a brief local HTTP interruption)
    get a single retry after a short delay.

    Args:
        user_text: The user's message.
        assistant_text: The robot's response.

    Returns:
        Validated ``TurnExtraction``.

    Raises:
        LLMError: If both attempts fail with a malformed response.
        httpx.HTTPError: If both attempts fail reaching Ollama.
    """
    try:
        return await _extract_via_ollama(user_text, assistant_text)
    except (LLMError, httpx.HTTPError) as exc:
        logger.warning(
            "Local extraction failed — retrying in %.0fs: %s",
            _RETRY_DELAY_S,
            exc,
        )
        await asyncio.sleep(_RETRY_DELAY_S)
        return await _extract_via_ollama(user_text, assistant_text)


def _manual_active_person_name(active_person: ActivePersonContext | None) -> str | None:
    """Return a validated turn-local subject reference, never authorization."""
    if (
        active_person is None
        or active_person.status is not ActivePersonStatus.IDENTIFIED
        or active_person.person_id is None
        or active_person.display_name is None
    ):
        return None
    if any(
        evidence.source is IdentityEvidenceSource.MANUAL
        and evidence.candidate_person_id == active_person.person_id
        for evidence in active_person.evidence
    ):
        return active_person.display_name
    return None


async def consolidate_turn(  # noqa: PLR0912
    user_text: str,
    assistant_text: str,
    *,
    active_person: ActivePersonContext | None = None,
) -> None:
    """Extract and persist entities, facts, and memories from one turn.

    Designed to run as a ``BackgroundTask`` after the HTTP response has been
    sent. All exceptions are caught and logged — failures here must never
    propagate to the user.

    Args:
        user_text: The user's message.
        assistant_text: The robot's response.
        active_person: Explicit manual identity evidence for this turn only.
    """
    active_person_name = _manual_active_person_name(active_person)
    if active_person_name is None:
        logger.info("Skipping consolidation without identified manual evidence")
        return
    try:
        extraction = await _extract(user_text, assistant_text)
    except (LLMError, httpx.HTTPError) as exc:
        logger.warning("Consolidation extraction failed: %s", exc)
        return

    extraction = normalize_extraction(
        extraction,
        active_person_name=active_person_name,
        user_text=user_text,
    )

    if extraction.importance < _LOW_IMPORTANCE and not extraction.facts:
        logger.debug("Turn below importance threshold — skipping consolidation")
        return

    entity_ids: dict[str, int] = {}
    for ent in extraction.entities:
        try:
            eid = await upsert_entity(
                name=ent.name,
                type=ent.type,
                attributes=ent.attributes,
                aliases=ent.aliases,
            )
            entity_ids[ent.name] = eid
        except Exception as exc:
            logger.warning("Entity upsert failed (%s): %s", ent.name, exc)

    memory_id: int | None = None
    if extraction.episodic_summary:
        try:
            memory_id = await store_memory(
                kind="episodic",
                content=f"[user] {user_text}\n[assistant] {assistant_text}",
                summary=extraction.episodic_summary,
                importance=extraction.importance,
                related_entities=list(entity_ids.values()),
            )
        except Exception as exc:
            logger.warning("Memory store failed: %s", exc)

    for fact in extraction.facts:
        entity_id: int | None = entity_ids.get(fact.subject)
        if entity_id is None:
            matches = await find_entities_by_name(fact.subject, limit=1)
            if matches:
                entity_id = int(matches[0]["id"])
            else:
                # A validated active person is a person, not an abstract concept.
                implicit_type: EntityType = (
                    "person"
                    if fact.subject.casefold() == active_person_name.casefold()
                    else "concept"
                )
                try:
                    entity_id = await upsert_entity(name=fact.subject, type=implicit_type)
                except Exception as exc:
                    logger.warning("Implicit entity creation failed (%s): %s", fact.subject, exc)
                    continue
        try:
            await assert_fact(
                entity_id=entity_id,
                predicate=fact.predicate,
                object_value=fact.object,
                confidence=fact.confidence,
                source_memory_id=memory_id,
            )
        except Exception as exc:
            logger.warning("Fact insert failed: %s", exc)

    logger.info(
        "Consolidated turn: entities=%d facts=%d memory_id=%s importance=%.2f",
        len(entity_ids),
        len(extraction.facts),
        memory_id,
        extraction.importance,
    )
