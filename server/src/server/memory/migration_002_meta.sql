-- =====================================================================
-- Migration 002: meta table — small persistent key/value flags.
-- First use: onboarding_complete (replaces the per-request
-- count_entities() == 0 heuristic, which broke when consolidation
-- never ran).
-- =====================================================================

CREATE TABLE IF NOT EXISTS meta (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Backfill: a DB that already knows a person finished onboarding long ago.
INSERT INTO meta (key, value)
SELECT 'onboarding_complete', 'true'
WHERE EXISTS (SELECT 1 FROM entities WHERE type = 'person')
ON CONFLICT (key) DO NOTHING;
