-- Migration 19 — the turn linked to what is derived from it (Plan 0085 D-8, ADR 0038 decision 6).
-- «Everything derived from this turn» becomes one query and one cascade: a recall unit, a memory
-- candidate and a pending topic each point at their `conversation_turns` row, so deleting a turn
-- removes them (the unit's FTS row and vector go with it, by the unit's own trigger). The columns
-- are added with ALTER TABLE ... ADD COLUMN, so no table is rebuilt; SQLite accepts a foreign key
-- there only nullable with a NULL default, so each is filled from the old correlation id text.
-- A row whose correlation id has no turn (the record was off, or the turn was purged) stays NULL.
-- The record keys stay, so today's cascades are unchanged. One unit per turn and one per episode:
-- a retried job cannot duplicate them. The body of a unit never changes (the FTS5 index would drift).
-- The same migration indexes every foreign key that a cascade, a SET NULL or a RESTRICT check
-- follows (a parent's DELETE otherwise scans the child table once per deleted row), and drops the
-- name index of `entities`, which `UNIQUE (name, type)` already serves. No transaction statements:
-- the runner wraps this file.

ALTER TABLE recall_units ADD COLUMN turn_id INTEGER DEFAULT NULL
    REFERENCES conversation_turns(id) ON DELETE CASCADE;
ALTER TABLE memory_candidates ADD COLUMN source_turn_id INTEGER DEFAULT NULL
    REFERENCES conversation_turns(id) ON DELETE CASCADE;
ALTER TABLE pending_topics ADD COLUMN source_turn_id INTEGER DEFAULT NULL
    REFERENCES conversation_turns(id) ON DELETE CASCADE;

UPDATE recall_units SET turn_id = (
    SELECT t.id FROM conversation_turns t WHERE t.correlation_id = recall_units.correlation_id
) WHERE kind = 'turn';
UPDATE memory_candidates SET source_turn_id = (
    SELECT t.id FROM conversation_turns t WHERE t.correlation_id = memory_candidates.source_correlation_id
);
UPDATE pending_topics SET source_turn_id = (
    SELECT t.id FROM conversation_turns t WHERE t.correlation_id = pending_topics.correlation_id
);

-- Full indexes: the foreign-key lookup of a turn's deletion needs one on each column, and a partial
-- index is not used for it. NULLs are distinct in a unique index, so units without a stored turn
-- (or, for the episode, a turn unit) may repeat; a stored turn has one unit and an episode has one.
-- The unique episode index also serves the episode's deletion, so it replaces the plain index of
-- migration 14 (`recall_units_episode_idx`).
CREATE UNIQUE INDEX recall_units_turn_idx ON recall_units (turn_id);
DROP INDEX recall_units_episode_idx;
CREATE UNIQUE INDEX recall_units_one_per_episode_idx ON recall_units (episode_id);
-- The model guard (ADR 0031 decision 8) runs on every recall question (the owner's units of
-- another model) and on every conversation-jobs tick (the units to embed): both read this index
-- (a vector of another model sorts before or after the configured name). A unit without a vector
-- is not in it; `recall_units_unembedded_idx` of migration 14 finds those.
CREATE INDEX recall_units_model_idx ON recall_units (embedding_model, owner_entity_id)
    WHERE embedding_model IS NOT NULL;
CREATE INDEX memory_candidates_source_turn_idx ON memory_candidates (source_turn_id);
-- The append links the candidates proposed before their turn existed, on every voice turn and
-- inside the write transaction: it finds them here, and only those still waiting for a turn.
CREATE INDEX memory_candidates_unlinked_idx ON memory_candidates (source_correlation_id)
    WHERE source_turn_id IS NULL;
CREATE INDEX pending_topics_source_turn_idx ON pending_topics (source_turn_id);

CREATE TRIGGER recall_units_body_locked BEFORE UPDATE OF body ON recall_units BEGIN
    SELECT RAISE(ABORT, 'recall unit body is immutable');
END;

CREATE INDEX admin_audit_target_entity_id_idx ON admin_audit (target_entity_id);
CREATE INDEX authorization_audit_events_actor_entity_id_idx ON authorization_audit_events (actor_entity_id);
CREATE INDEX authorization_audit_events_target_entity_id_idx ON authorization_audit_events (target_entity_id);
CREATE INDEX care_contacts_asserted_by_entity_id_idx ON care_contacts (asserted_by_entity_id);
CREATE INDEX care_contacts_confirmed_by_entity_id_idx ON care_contacts (confirmed_by_entity_id);
CREATE INDEX care_contacts_contact_entity_id_idx ON care_contacts (contact_entity_id);
CREATE INDEX care_contacts_owner_entity_id_idx ON care_contacts (owner_entity_id);
CREATE INDEX conversation_consent_grants_person_entity_id_idx ON conversation_consent_grants (person_entity_id);
CREATE INDEX entity_relations_v4_asserted_by_entity_id_idx ON entity_relations_v4 (asserted_by_entity_id);
CREATE INDEX entity_relations_v4_confirmed_by_entity_id_idx ON entity_relations_v4 (confirmed_by_entity_id);
CREATE INDEX entity_relations_v4_source_entity_id_idx ON entity_relations_v4 (source_entity_id);
CREATE INDEX entity_relations_v4_target_entity_id_idx ON entity_relations_v4 (target_entity_id);
CREATE INDEX entity_relations_v4_superseded_by_idx ON entity_relations_v4 (superseded_by);
CREATE INDEX entity_relations_v4_source_memory_id_idx ON entity_relations_v4 (source_memory_id);
CREATE INDEX face_consent_grants_person_entity_id_idx ON face_consent_grants (person_entity_id);
CREATE INDEX household_role_assignments_grantor_entity_id_idx ON household_role_assignments (grantor_entity_id);
CREATE INDEX household_role_assignments_person_entity_id_idx ON household_role_assignments (person_entity_id);
CREATE INDEX literal_facts_v4_asserted_by_entity_id_idx ON literal_facts_v4 (asserted_by_entity_id);
CREATE INDEX literal_facts_v4_confirmed_by_entity_id_idx ON literal_facts_v4 (confirmed_by_entity_id);
CREATE INDEX literal_facts_v4_subject_entity_id_idx ON literal_facts_v4 (subject_entity_id);
CREATE INDEX literal_facts_v4_superseded_by_idx ON literal_facts_v4 (superseded_by);
CREATE INDEX literal_facts_v4_source_memory_id_idx ON literal_facts_v4 (source_memory_id);
CREATE INDEX memory_candidates_asserted_by_person_id_idx ON memory_candidates (asserted_by_person_id);
CREATE INDEX memory_candidates_promoted_fact_id_idx ON memory_candidates (promoted_fact_id);
CREATE INDEX owner_pin_credentials_person_entity_id_idx ON owner_pin_credentials (person_entity_id);
CREATE INDEX voice_consent_grants_person_entity_id_idx ON voice_consent_grants (person_entity_id);

DROP INDEX entities_name_idx;
