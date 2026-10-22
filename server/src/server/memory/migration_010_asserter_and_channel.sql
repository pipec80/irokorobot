-- Migration 10 — who asserted a V4 fact and through which channel (Plan 0065, ADR 0022 decision 2).
-- One canonical writer serves every channel (the spoken confirmation, the initial import, later a
-- perceptual source); the memory contract asks "who asserted it", and the benchmark's
-- provenance_accuracy gate measures it. Both columns are nullable and additive: a row written
-- before this migration, or by a writer that does not state them (the local setup, the legacy
-- migration), reads NULL in both. SQLite needs no table rebuild for ADD COLUMN.
-- The channel is a closed list kept in Python (`WriteChannel`), not a CHECK, so adding a channel
-- later is not a migration.
ALTER TABLE literal_facts_v4
    ADD COLUMN asserted_by_entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL;
ALTER TABLE literal_facts_v4 ADD COLUMN channel TEXT;
ALTER TABLE entity_relations_v4
    ADD COLUMN asserted_by_entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL;
ALTER TABLE entity_relations_v4 ADD COLUMN channel TEXT;
