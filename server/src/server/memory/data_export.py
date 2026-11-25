"""Gather everything, or everything about one person, for an export (Plan 0087 D-5, D-6).

ADR 0032 decision 8. «Todo» is every row each owner module keeps, history and archive included,
in the fixed order of ``SECTION_KEYS``. «Una persona» has the reach of ``forget person``
(``person_scope(..., for_deletion=True)``) plus the person's identity rows, and never holds a fact
whose subject is another person (so the owner's facts that name them stay out) nor a turn that
may be another person's words (``not_owner``, ``not_checked``), nor a unit or a topic made from
such a turn, nor the deletion register. Each excluded class is counted in ``no_sale``.

Every table is read through its owner module; this module holds no SQL and logs nothing. The
module is longer than the guideline because most of it is the closed table of Spanish labels.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from server import db
from server.memory import (
    admin_audit,
    biometric_consent,
    candidates,
    care_contacts,
    commissioning,
    conversation_consent,
    conversation_episodes,
    conversation_record,
    declarative,
    deletion_register,
    document_store,
    household_authorization,
    meta,
    owner_credentials,
    pending_store,
    recall_store,
    relational_v4,
    voice_consent,
)
from server.memory.conversation_types import TurnVerdict
from server.memory.export_model import (
    Cell,
    ExportColumn,
    ExportDocument,
    ExportScope,
    ExportScopeKind,
    ExportSection,
    StoredRows,
)
from server.memory.forget_scope import person_scope
from server.vision import faces
from server.voice import voiceprints

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Sequence

__all__ = ["SECTION_KEYS", "export_counts", "gather_export", "holds_nothing"]

type Row = dict[str, Cell]
type Keep = Callable[[Row], bool]

_TITLES: dict[str, str] = {
    "personas": "Personas",
    "datos": "Datos",
    "relaciones": "Relaciones",
    "contactos": "Contactos de cuidado",
    "roles": "Roles en el hogar",
    "consentimientos": "Consentimientos",
    "credenciales": "Credenciales (solo la referencia)",
    "perfiles": "Perfiles de cara y de voz (solo la referencia)",
    "conversaciones": "Conversaciones",
    "turnos": "Turnos",
    "diario": "Diario",
    "recuerdos": "Recuerdos",
    "temas_pendientes": "Temas pendientes",
    "por_confirmar": "Por confirmar",
    "documentos": "Documentos",
    "secciones_documentos": "Secciones de los documentos",
    "acta": "Acta del alta",
    "acta_secciones": "Secciones del acta",
    "auditoria_admin": "Auditoría de la administración",
    "decisiones": "Decisiones de la política",
    "borrados": "Registro de borrados",
    "no_sale": "Lo que no sale",
}
#: The sections of an export, in their one order (D-5).
SECTION_KEYS: tuple[str, ...] = tuple(_TITLES)

_LABELS: dict[str, str] = {
    "id": "Id",
    "name": "Nombre",
    "type": "Tipo",
    "aliases": "Otros nombres",
    "role": "Rol",
    "subject_entity_id": "Id de la persona",
    "subject_name": "De quién",
    "predicate": "Qué dato",
    "value_text": "Valor",
    "lifecycle": "Estado",
    "sensitivity": "Sensibilidad",
    "visibility": "Visibilidad",
    "valid_from": "Válido desde",
    "valid_to": "Válido hasta",
    "asserted_at": "Dicho el",
    "confirmed_at": "Confirmado el",
    "superseded_by": "Reemplazado por",
    "superseded_at": "Reemplazado el",
    "archived_at": "Archivado el",
    "channel": "Canal",
    "source_entity_id": "Id de origen",
    "source_name": "Origen",
    "target_entity_id": "Id de destino",
    "target_name": "Destino",
    "owner_entity_id": "Id de la persona titular",
    "contact_entity_id": "Id del contacto",
    "relationship": "Relación",
    "phone": "Teléfono",
    "phone_alt": "Otro teléfono",
    "call_order": "Orden de llamada",
    "has_key": "Tiene llave",
    "may_receive_health_info": "Puede saber de salud",
    "may_view_activity": "Puede ver la actividad",
    "created_at": "Creado el",
    "updated_at": "Actualizado el",
    "revoked_at": "Revocado el",
    "person_entity_id": "Id de la persona",
    "grantor_entity_id": "Id de quien lo dio",
    "reason": "Motivo",
    "granted_at": "Dado el",
    "purpose": "Para qué",
    "algorithm": "Algoritmo",
    "modality": "Modalidad",
    "entity_id": "Id de la persona",
    "label": "Etiqueta",
    "model_id": "Modelo",
    "previous_id": "Conversación anterior",
    "started_at": "Empezó el",
    "last_turn_at": "Último turno el",
    "closed_at": "Cerrada el",
    "eligible": "Va al diario",
    "expires_at": "Vence el",
    "episode_status": "Estado del diario",
    "record_id": "Conversación",
    "said_at": "Dicho el",
    "verdict": "Quién habló",
    "heard": "Lo que se oyó",
    "said": "Lo que dijo Iroko",
    "source_record_id": "Conversación",
    "summary": "Resumen",
    "turn_id": "Turno",
    "kind": "Tipo",
    "body": "Texto",
    "occurred_from": "Pasó desde",
    "occurred_to": "Pasó hasta",
    "source_turn_id": "Turno",
    "said_day": "Dicho el día",
    "due_day": "Para el día",
    "topic": "Tema",
    "state": "Estado",
    "asked_at": "Preguntado el",
    "subject_person_id": "Id de la persona",
    "asserted_by_person_id": "Id de quien lo dijo",
    "status": "Estado",
    "proposed_at": "Propuesto el",
    "installation_id": "Instalación",
    "interviewer_label": "Quién entrevistó",
    "interviewer_role": "Rol de quien entrevistó",
    "confirmation_mode": "Cómo se confirmó",
    "disk_encryption": "Disco cifrado",
    "pool_version": "Versión del pozo",
    "biometric_notice_version": "Versión del aviso biométrico",
    "commissioning_id": "Acta",
    "section": "Sección",
    "recorded_at": "Registrado el",
    "actor_label": "Quién administró",
    "actor_role": "Rol",
    "operation": "Operación",
    "target_kind": "Sobre qué",
    "field_id": "Campo",
    "outcome": "Resultado",
    "evaluated_at": "Decidido el",
    "actor_entity_id": "Id de quien pidió",
    "action": "Acción",
    "data_categories": "Categorías de datos",
    "decision": "Decisión",
    "policy_id": "Política",
    "seq": "Número",
    "at": "Borrado el",
    "what": "Qué",
    "why": "Por qué no sale",
    "rows": "Filas",
    "title": "Título",
    "level": "Nivel",
    "format": "Formato",
    "loaded_at": "Cargado el",
    "sections": "Secciones",
    "characters": "Caracteres",
    "source_id": "Documento",
    "position": "Posición",
    "heading": "Encabezado",
}

_OTHER_VOICES = frozenset({TurnVerdict.NOT_OWNER.value, TurnVerdict.NOT_CHECKED.value})
_NO_SALE_COLUMNS = ("what", "why", "rows")


def _dicts(stored: StoredRows) -> list[Row]:
    return [dict(zip(stored.columns, row, strict=True)) for row in stored.rows]


def _after(columns: Sequence[str], anchor: str, key: str) -> tuple[str, ...]:
    """*columns* with *key* inserted right after *anchor*."""
    at = list(columns).index(anchor) + 1
    return (*columns[:at], key, *columns[at:])


def _section(key: str, columns: Sequence[str], rows: Sequence[Row], keep: Keep) -> ExportSection:
    return ExportSection(
        key=key,
        title=_TITLES[key],
        columns=tuple(ExportColumn(column, _LABELS[column]) for column in columns),
        rows=tuple(tuple(row.get(column) for column in columns) for row in rows if keep(row)),
    )


def _everything(_: Row) -> bool:
    return True


def _of(ids: Collection[Cell]) -> Keep:
    return lambda row: row["id"] in ids


class _Store:
    """Every exportable row, read once through the owner modules."""

    async def load(self) -> _Store:
        self.entities = await declarative.entities_for_export()
        self.facts = await relational_v4.facts_for_export()
        self.relations = await relational_v4.relations_for_export()
        self.contacts = await care_contacts.contacts_for_export()
        self.roles = await household_authorization.roles_for_export()
        self.decisions = await household_authorization.decisions_for_export()
        self.consents = [
            *_dicts(await conversation_consent.conversation_consents_for_export()),
            *_dicts(await biometric_consent.face_consents_for_export()),
            *_dicts(await voice_consent.voice_consents_for_export()),
        ]
        self.credentials = await owner_credentials.credentials_for_export()
        self.profiles = [
            {"modality": "face", "model_id": None, **row}
            for row in _dicts(await faces.face_profiles_for_export())
        ] + [
            {"modality": "voice", **row}
            for row in _dicts(await voiceprints.voice_profiles_for_export())
        ]
        self.records = await conversation_record.records_for_export()
        self.turns = await conversation_record.turns_for_export()
        self.episodes = await conversation_episodes.episodes_for_export()
        self.units = await recall_store.units_for_export()
        self.topics = await pending_store.topics_for_export()
        self.candidates = await candidates.live_candidates_for_export()
        self.documents = await document_store.sources_for_export()
        self.sections = await document_store.sections_for_export()
        self.acta = await commissioning.commissioning_records_for_export()
        self.acta_sections = await commissioning.commissioning_sections_for_export()
        self.audit = await admin_audit.audit_for_export()
        self.register = deletion_register.lines_for_export()
        return self


class _Selection:
    """Which rows of each section one scope keeps, and what it left out (D-6)."""

    def __init__(self) -> None:
        self.keep: dict[str, Keep] = dict.fromkeys(SECTION_KEYS, _everything)
        self.excluded: list[tuple[str, str, int]] = []


async def _person_selection(
    scope: ExportScope, store: _Store, *, owner_entity_id: int, now: str
) -> _Selection:
    """The rows of one person: the reach of ``forget person`` and the person's identity."""
    reach = await person_scope(
        owner_entity_id,
        now=now,
        entity_id=scope.entity_id,
        words=scope.words,
        for_deletion=True,
    )
    person = reach.entity_id
    is_owner = person == owner_entity_id
    turns = _dicts(store.turns)
    owner_records = {
        row["id"] for row in _dicts(store.records) if row["owner_entity_id"] == owner_entity_id
    }
    reached = (
        {row["id"] for row in turns if row["record_id"] in owner_records}
        if is_owner
        else set(reach.turns)
    )
    other_voices = {row["id"] for row in turns if row["verdict"] in _OTHER_VOICES} & reached
    kept_turns = reached - other_voices
    # An episode reached only through another voice's turn stays out (fails closed): its summary
    # may retell those words, and a summary cannot be partly unsaid (ADR 0032 decision 2).
    kept_turn_records = {row["record_id"] for row in turns if row["id"] in kept_turns}
    other_records = {row["record_id"] for row in turns if row["id"] in other_voices}
    dropped_records = set() if is_owner else other_records - kept_turn_records
    episodes = set(reach.episodes) - dropped_records
    kept_records = owner_records if is_owner else kept_turn_records | episodes
    mine: Keep = lambda row: is_owner and row["owner_entity_id"] == person  # noqa: E731
    reached_units = [row for row in _dicts(store.units) if mine(row) or row["id"] in reach.units]
    reached_topics = [row for row in _dicts(store.topics) if mine(row) or row["id"] in reach.topics]
    units = [
        row
        for row in reached_units
        if row["turn_id"] not in other_voices and row["source_record_id"] not in dropped_records
    ]
    topics = [row for row in reached_topics if row["source_turn_id"] not in other_voices]
    other_voice_rows = (len(reached_units) - len(units) + len(reached_topics) - len(topics)) + len(
        set(reach.episodes) & dropped_records
    )
    selection = _Selection()
    keep = selection.keep
    known = person is not None  # every identity filter fails closed for a name only talked about
    keep["personas"] = _of({person} if known else set())
    keep["datos"] = lambda row: known and row["subject_entity_id"] == person
    keep["relaciones"] = lambda row: (
        known
        and person
        in (
            row["source_entity_id"],
            row["target_entity_id"],
        )
    )
    keep["contactos"] = lambda row: (
        known
        and person
        in (
            row["contact_entity_id"],
            row["owner_entity_id"],
        )
    )
    for key in ("roles", "consentimientos", "credenciales"):
        keep[key] = lambda row: known and row["person_entity_id"] == person
    keep["perfiles"] = lambda row: known and row["entity_id"] == person
    keep["conversaciones"] = _of(kept_records)
    keep["turnos"] = _of(kept_turns)
    keep["diario"] = lambda row: mine(row) or row["source_record_id"] in episodes
    keep["recuerdos"] = _of({row["id"] for row in units})
    keep["temas_pendientes"] = _of({row["id"] for row in topics})
    keep["por_confirmar"] = lambda row: known and row["subject_person_id"] == person
    # The owner's documents are the owner's own (ADR 0034 decision 2): only their export holds them.
    keep["documentos"] = keep["secciones_documentos"] = lambda _row: is_owner
    keep["acta"] = keep["acta_secciones"] = lambda _row: is_owner
    keep["auditoria_admin"] = lambda row: is_owner or (known and row["target_entity_id"] == person)
    keep["decisiones"] = lambda row: (
        known
        and person
        in (
            row["actor_entity_id"],
            row["target_entity_id"],
        )
    )
    keep["borrados"] = lambda _row: False
    selection.excluded = [
        ("turnos de otra voz", "pueden ser las palabras de otra persona", len(other_voices)),
        (
            "diario, recuerdos y temas de otra voz",
            "salieron de un turno de otra voz",
            other_voice_rows,
        ),
        ("registro de borrados", "un id borrado ya no se ata a nadie", len(store.register.rows)),
    ]
    if not is_owner:
        selection.excluded.insert(
            1, ("datos tuyos que la nombran", "su sujeto eres tú", len(reach.owner_facts))
        )
    return selection


async def _no_sale(store: _Store, excluded: Sequence[tuple[str, str, int]]) -> list[Row]:
    """What is never exported, and why, with its row count (D-5)."""
    fts, vectors = await recall_store.projection_counts()
    document_fts, document_vectors = await document_store.projection_counts()
    always = [
        (
            "índice de texto de los recuerdos",
            "una copia para buscar: el texto está en «Recuerdos»",
            fts,
        ),
        ("vectores de los recuerdos", "números para buscar, no se leen", vectors),
        (
            "índice de texto de los documentos",
            "una copia para buscar: el texto está en «Secciones de los documentos»",
            document_fts,
        ),
        ("vectores de los documentos", "números para buscar, no se leen", document_vectors),
        (
            "vectores de las caras",
            "dato biométrico: sale solo la referencia",
            await faces.count_face_vectors(),
        ),
        (
            "huellas de voz",
            "dato biométrico: sale solo la referencia",
            sum(1 for row in store.profiles if row["modality"] == "voice"),
        ),
        ("verificador del PIN", "un secreto: sale solo la referencia", len(store.credentials.rows)),
        ("estado del sistema", "no es un dato de nadie", await meta.count_flags()),
        (
            "memorias retiradas",
            "tabla retirada, nadie la lee (ADR 0027)",
            await db.count_retired_memories(),
        ),
    ]
    return [{"what": what, "why": why, "rows": rows} for what, why, rows in [*always, *excluded]]


def _sections(
    store: _Store, selection: _Selection, no_sale: list[Row]
) -> tuple[ExportSection, ...]:
    names = {row["id"]: row["name"] for row in _dicts(store.entities)}
    active_role = {
        row["person_entity_id"]: row["role"]
        for row in _dicts(store.roles)
        if row["revoked_at"] is None
    }
    people = [{**row, "role": active_role.get(row["id"])} for row in _dicts(store.entities)]
    facts = [
        {**row, "subject_name": names.get(row["subject_entity_id"])} for row in _dicts(store.facts)
    ]
    relations = [
        {
            **row,
            "source_name": names.get(row["source_entity_id"]),
            "target_name": names.get(row["target_entity_id"]),
        }
        for row in _dicts(store.relations)
    ]
    relation_columns = _after(
        _after(store.relations.columns, "source_entity_id", "source_name"),
        "target_entity_id",
        "target_name",
    )
    profile_columns = ("modality", "id", "entity_id", "label", "model_id", "created_at")
    plain: dict[str, StoredRows] = {
        "contactos": store.contacts,
        "credenciales": store.credentials,
        "conversaciones": store.records,
        "turnos": store.turns,
        "diario": store.episodes,
        "recuerdos": store.units,
        "temas_pendientes": store.topics,
        "por_confirmar": store.candidates,
        "documentos": store.documents,
        "secciones_documentos": store.sections,
        "acta": store.acta,
        "acta_secciones": store.acta_sections,
        "auditoria_admin": store.audit,
        "decisiones": store.decisions,
        "borrados": store.register,
        "roles": store.roles,
    }
    built = {
        "personas": (("id", "name", "type", "aliases", "role", "created_at"), people),
        "datos": (_after(store.facts.columns, "subject_entity_id", "subject_name"), facts),
        "relaciones": (relation_columns, relations),
        "consentimientos": (
            ("id", "person_entity_id", "purpose", "granted_at", "revoked_at"),
            store.consents,
        ),
        "perfiles": (profile_columns, store.profiles),
        "no_sale": (_NO_SALE_COLUMNS, no_sale),
        **{key: (rows.columns, _dicts(rows)) for key, rows in plain.items()},
    }
    return tuple(
        _section(key, built[key][0], built[key][1], selection.keep[key]) for key in SECTION_KEYS
    )


async def gather_export(scope: ExportScope, *, owner_entity_id: int, now: str) -> ExportDocument:
    """Build the one model both export files are rendered from.

    Args:
        scope: Everything, or one person (an entity id, or the words of a name only talked about).
        owner_entity_id: The owner whose robot is exported.
        now: The instant of the export (UTC ISO 8601), written in its header.

    Returns:
        The document: its scope, instant, schema version and every section of ``SECTION_KEYS``.
    """
    store = await _Store().load()
    selection = (
        _Selection()
        if scope.kind is ExportScopeKind.ALL
        else await _person_selection(scope, store, owner_entity_id=owner_entity_id, now=now)
    )
    no_sale = await _no_sale(store, selection.excluded)
    return ExportDocument(
        scope=scope,
        generated_at=now,
        schema_version=db.latest_schema_version(),
        sections=_sections(store, selection, no_sale),
    )


def holds_nothing(document: ExportDocument) -> bool:
    """Whether the export holds no row at all besides what does not leave (D-6, «empty»)."""
    return all(not section.rows for section in document.sections if section.key != "no_sale")


def export_counts(document: ExportDocument) -> tuple[str, ...]:
    """One Spanish line per section, «{título}: {n} filas», for the read-back before ``SI``."""
    return tuple(
        f"{section.title}: {len(section.rows)} {'fila' if len(section.rows) == 1 else 'filas'}"
        for section in document.sections
    )
