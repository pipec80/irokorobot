"""Extract entities, facts, and episodic memories from a conversation turn.

Runs as a FastAPI ``BackgroundTask`` — the caller has already returned a
response to the user. All errors are caught, logged, and swallowed so that
consolidation failures are never visible to the user.
"""

from __future__ import annotations

import asyncio
import logging
import re

import anthropic
import httpx

from server.exceptions import LLMError
from server.llm_clients import get_anthropic_client
from server.llm_transport import ollama_chat, strip_json_fences
from server.memory.declarative import assert_fact, find_entities_by_name, upsert_entity
from server.memory.meta import get_flag, set_flag
from server.memory.normalize import normalize_extraction
from server.memory.semantic import store_memory
from server.schemas import EntityType, TurnExtraction
from server.settings import settings

logger = logging.getLogger(__name__)

_LOW_IMPORTANCE = 0.2
_RETRY_DELAY_S = 5.0
_EXTRACTION_TOOL_NAME = "record_extraction"

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


async def _extract_via_anthropic(user_text: str, assistant_text: str) -> TurnExtraction:
    """Call Anthropic with a forced tool to extract structured data from a turn.

    Uses tool-choice-forced tool use so the model must emit JSON matching
    ``TurnExtraction.model_json_schema()`` — no free-text parsing involved.

    Args:
        user_text: The user's message in the current turn.
        assistant_text: The robot's response in the current turn.

    Returns:
        Validated ``TurnExtraction`` Pydantic model.

    Raises:
        LLMError: If the response has no tool_use block or fails validation.
        anthropic.AnthropicError: If the API call itself fails.
    """
    client = get_anthropic_client()
    message = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        system=_EXTRACTION_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": f"Conversación:\n[user] {user_text}\n[assistant] {assistant_text}",
            }
        ],
        tools=[
            {
                "name": _EXTRACTION_TOOL_NAME,
                "description": (
                    "Registra entidades, hechos, resumen episódico e importancia "
                    "extraídos del turno de conversación."
                ),
                "input_schema": TurnExtraction.model_json_schema(),
            }
        ],
        tool_choice={"type": "tool", "name": _EXTRACTION_TOOL_NAME},
    )
    tool_blocks = [block for block in message.content if block.type == "tool_use"]
    if not tool_blocks:
        raise LLMError("Anthropic extraction returned no tool_use block")
    try:
        return TurnExtraction.model_validate(tool_blocks[0].input)
    except Exception as exc:
        raise LLMError(f"Extraction returned invalid schema: {exc}") from exc


async def _extract(user_text: str, assistant_text: str) -> TurnExtraction:
    """Route extraction to the configured provider, retrying once on failure.

    Provider resolution: ``settings.consolidation_provider``, falling back to
    ``settings.llm_provider`` when empty. Transient failures (model still
    loading, brief network hiccups) get a single retry after a short delay.

    Args:
        user_text: The user's message.
        assistant_text: The robot's response.

    Returns:
        Validated ``TurnExtraction``.

    Raises:
        LLMError: If both attempts fail with a malformed response.
        httpx.HTTPError: If both attempts fail reaching Ollama.
        anthropic.AnthropicError: If both attempts fail reaching Anthropic.
    """
    provider = settings.consolidation_provider or settings.llm_provider
    extractor = _extract_via_anthropic if provider == "anthropic" else _extract_via_ollama
    try:
        return await extractor(user_text, assistant_text)
    except (LLMError, httpx.HTTPError, anthropic.AnthropicError) as exc:
        logger.warning(
            "Extraction failed (provider=%s) — retrying in %.0fs: %s",
            provider,
            _RETRY_DELAY_S,
            exc,
        )
        await asyncio.sleep(_RETRY_DELAY_S)
        return await extractor(user_text, assistant_text)


# Self-introduction patterns — the ONLY way to anchor the owner's name.
# "Soy X" alone is risky ("soy de Santiago"), hence the non-name guard.
_INTRO_PATTERN = re.compile(
    r"\b(?:me llamo|mi nombre es|yo soy|soy)\s+"
    r"([a-záéíóúüñ]+(?:\s+[a-záéíóúüñ]+)?)",
    re.IGNORECASE,
)
_NON_NAME_WORDS = frozenset({"de", "del", "el", "la", "un", "una", "muy", "yo", "tu", "su"})


def _self_intro_name(user_text: str, extraction: TurnExtraction) -> str | None:
    """Extract the owner's name from an explicit self-introduction.

    Deterministic anchor for owner identity: only the USER saying
    "me llamo X" (or variants) can name the owner. The previous heuristic
    ("first person learned IS the owner") broke live on 2026-07-13: the
    owner mentioned his children before introducing himself and a child
    got anchored as the owner.

    Args:
        user_text: The user's literal words for this turn.
        extraction: Raw extraction — person entities refine the captured
            name to its full form ("felipe" → "Felipe Castro").

    Returns:
        The owner's name title-cased, or ``None`` if no introduction found.
    """
    match = _INTRO_PATTERN.search(user_text)
    if match is None:
        return None
    first_word = match.group(1).split()[0].casefold()
    if first_word in _NON_NAME_WORDS:
        return None
    lowered = user_text.casefold()
    for ent in extraction.entities:
        name = ent.name.strip()
        # Grounded person entity containing the captured word wins — it
        # carries the full name when the user gave one.
        if ent.type == "person" and first_word in name.casefold() and name.casefold() in lowered:
            return name.title()
    return first_word.title()


async def _maybe_anchor_owner(user_text: str, extraction: TurnExtraction) -> None:
    """Persist ``owner_name`` when the user introduces themselves.

    Idempotent: only writes while the flag is unset. Errors are logged and
    swallowed (background-task context). Onboarding completion is decided
    elsewhere — by the checklist in ``server.onboarding``, not here.

    Args:
        user_text: The user's literal words for this turn.
        extraction: Raw extraction for this turn (pre-normalization).
    """
    try:
        if await get_flag("owner_name") is not None:
            return
        name = _self_intro_name(user_text, extraction)
        if name is None:
            return
        await set_flag("owner_name", name)
        logger.info("Owner anchored: %s", name)
    except Exception as exc:
        logger.warning("Owner anchor failed: %s", exc)


async def _owner_name() -> str | None:
    """Return the persisted owner name, or ``None`` if unset or unavailable."""
    try:
        return await get_flag("owner_name")
    except Exception as exc:
        logger.warning("Owner lookup failed — normalizing without owner: %s", exc)
        return None


async def consolidate_turn(user_text: str, assistant_text: str) -> None:
    """Extract and persist entities, facts, and memories from one turn.

    Designed to run as a ``BackgroundTask`` after the HTTP response has been
    sent. All exceptions are caught and logged — failures here must never
    propagate to the user.

    Args:
        user_text: The user's message.
        assistant_text: The robot's response.
    """
    try:
        extraction = await _extract(user_text, assistant_text)
    except (LLMError, httpx.HTTPError, anthropic.AnthropicError) as exc:
        logger.warning("Consolidation extraction failed: %s", exc)
        return

    # Anchor BEFORE normalizing so this very turn's "usuario" facts already
    # resolve to the freshly learned owner ("me llamo Felipe" → Felipe).
    await _maybe_anchor_owner(user_text, extraction)

    owner_name = await _owner_name()
    extraction = normalize_extraction(extraction, owner_name=owner_name, user_text=user_text)

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
                # The owner's implicit entity is a person, not an abstract
                # concept ("Felipe [concept]" observed in the DB 2026-07-14
                # when the intro turn carried no explicit entity).
                implicit_type: EntityType = (
                    "person"
                    if owner_name and fact.subject.casefold() == owner_name.casefold()
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
