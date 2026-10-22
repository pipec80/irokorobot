-- Migration 10 — who asserted a V4 fact and through which channel (Plan 0065, ADR 0022 decision 2).
-- One canonical writer serves every channel (the spoken confirmation, the initial import, later a
-- perceptual source); the memory contract asks "who asserted it", and the benchmark's
-- provenance_accuracy gate measures it. Both columns are nullable and additive: a row written
-- before this migration, or by a writer that does not state them (the local setup, the legacy
-- migration), reads NULL in both. SQLite needs no table rebuild for ADD COLUMN.
-- The channel is a closed list kept in Python (`WriteChannel`), not a CHECK, so adding a channel
-- later is not a migration.
-- This is the first migration made of several ALTER TABLE statements, which SQLite would
-- otherwise autocommit one by one: a crash between two of them would leave some columns added and
-- the version still 9, and the next start would fail on a duplicate column for good. DDL and
-- `user_version` are transactional in SQLite, so the four columns and the version go together.
BEGIN;
ALTER TABLE literal_facts_v4
    ADD COLUMN asserted_by_entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL;
ALTER TABLE literal_facts_v4 ADD COLUMN channel TEXT;
ALTER TABLE entity_relations_v4
    ADD COLUMN asserted_by_entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL;
ALTER TABLE entity_relations_v4 ADD COLUMN channel TEXT;
PRAGMA user_version = 10;
COMMIT;
