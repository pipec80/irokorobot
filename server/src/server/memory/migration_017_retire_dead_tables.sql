-- Migration 17 — the dead tables out (Plan 0085 D-6).
-- Eight tables nothing reads or writes any more: outbox, sensor_current, sensor_readings,
-- sensor_aggregates_hourly, facts, legacy_fact_migration_v4, embeddings_cache and events. A
-- migration never drops data it has not looked at: the guard below fails on a row in any of
-- them, and the runner then rolls everything back and leaves version 16. Children go before
-- parents (legacy_fact_migration_v4 refers to facts); a table's indexes go with it. `memories`
-- and the source_memory_id columns stay: dropping them needs a V4 rebuild nothing else asks for,
-- and `memories` is already locked by a trigger (migration 013). No transaction statements: the
-- runner wraps this file.

CREATE TEMP TABLE _dead_rows (n INTEGER CHECK (n = 0));
INSERT INTO _dead_rows SELECT
    (SELECT count(*) FROM outbox)
    + (SELECT count(*) FROM sensor_current)
    + (SELECT count(*) FROM sensor_readings)
    + (SELECT count(*) FROM sensor_aggregates_hourly)
    + (SELECT count(*) FROM facts)
    + (SELECT count(*) FROM legacy_fact_migration_v4)
    + (SELECT count(*) FROM embeddings_cache)
    + (SELECT count(*) FROM events);
DROP TABLE _dead_rows;

DROP TABLE legacy_fact_migration_v4;
DROP TABLE facts;
DROP TABLE outbox;
DROP TABLE sensor_current;
DROP TABLE sensor_readings;
DROP TABLE sensor_aggregates_hourly;
DROP TABLE embeddings_cache;
DROP TABLE events;
