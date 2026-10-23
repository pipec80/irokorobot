-- Migration 11 — care contacts and the commissioning record (Plan 0070, ADR 0024 decisions 5, 6, 15).
-- Three new tables, none read by any older code, so there is no down-step: the rollback is to leave
-- them. The script is atomic like 010 (DDL and `user_version` are transactional in SQLite): a crash
-- half-way leaves version 10 and the next start retries it from the start.
-- The lists in the CHECKs (roles, modes, sections, statuses) are closed on purpose: they are the
-- last line of defence of two Python writers that validate first. Timestamps follow migration
-- 004: UTC text, `datetime('now')` where the database stamps them and an explicit value where the
-- caller states when a person confirmed something.
BEGIN;

-- A person the owner wants called or told: operational data, not a V4 fact, so it opens no fact
-- about the contact (ADR 0024 decision 5). The writer assigns the classification; the CHECKs
-- only allow what that writer can produce. `phone` and `phone_alt` are international
-- (`+` and 8 to 15 digits, the first not 0): SQL checks the first digit and the length, the
-- writer's `normalize_phone` checks the rest. A row is revoked, never edited or deleted.
CREATE TABLE care_contacts (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_entity_id         INTEGER NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
    contact_entity_id       INTEGER NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
    role                    TEXT NOT NULL CHECK (
        role IN ('emergency', 'caregiver', 'doctor', 'key_holder', 'neighbor', 'trusted', 'other')
    ),
    relationship            TEXT CHECK (relationship IS NULL OR length(relationship) BETWEEN 1 AND 40),
    phone                   TEXT NOT NULL CHECK (
        phone GLOB '+[1-9]*' AND length(phone) BETWEEN 9 AND 16
    ),
    phone_alt               TEXT CHECK (
        phone_alt IS NULL OR (phone_alt GLOB '+[1-9]*' AND length(phone_alt) BETWEEN 9 AND 16)
    ),
    call_order              INTEGER CHECK (call_order IS NULL OR call_order >= 1),
    has_key                 INTEGER NOT NULL DEFAULT 0 CHECK (has_key IN (0, 1)),
    may_receive_health_info INTEGER NOT NULL DEFAULT 0 CHECK (may_receive_health_info IN (0, 1)),
    may_view_activity       INTEGER NOT NULL DEFAULT 0 CHECK (may_view_activity IN (0, 1)),
    visibility              TEXT NOT NULL DEFAULT 'personal' CHECK (visibility = 'personal'),
    sensitivity             TEXT NOT NULL DEFAULT 'private' CHECK (sensitivity IN ('private', 'location')),
    asserted_by_entity_id   INTEGER REFERENCES entities(id) ON DELETE SET NULL,
    channel                 TEXT NOT NULL,
    confirmed_by_entity_id  INTEGER REFERENCES entities(id) ON DELETE SET NULL,
    confirmed_at            TEXT NOT NULL,
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    revoked_at              TEXT
);

-- One active row per owner, contact and role: a person with two roles has two rows.
CREATE UNIQUE INDEX care_contacts_active_role_idx
    ON care_contacts (owner_entity_id, contact_entity_id, role)
    WHERE revoked_at IS NULL;

-- The call order belongs to the person, so a second phone is a column and not a second order.
-- A contact with no order is never called by an alert.
CREATE UNIQUE INDEX care_contacts_active_order_idx
    ON care_contacts (owner_entity_id, call_order)
    WHERE revoked_at IS NULL AND call_order IS NOT NULL;

-- The acta of a commissioning: who interviewed, how the owner confirmed, what was loaded and what
-- was consented, with no household value (ADR 0024 decisions 6, 13, 15). The columns after
-- `pool_version` are nullable: they are filled as the commissioning goes, by the importer (the
-- hash and the counts) and by the session (consents, modalities, backups, readiness).
CREATE TABLE commissioning_records (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    installation_id             TEXT NOT NULL CHECK (length(installation_id) = 36),
    started_at                  TEXT NOT NULL,
    interviewer_label           TEXT NOT NULL CHECK (length(interviewer_label) BETWEEN 1 AND 80),
    interviewer_role            TEXT NOT NULL CHECK (
        interviewer_role IN ('builder', 'family', 'technician', 'other')
    ),
    confirmation_mode           TEXT NOT NULL CHECK (
        confirmation_mode IN ('owner_in_person', 'representative', 'builder_is_owner')
    ),
    disk_encryption             TEXT NOT NULL CHECK (
        disk_encryption IN ('declared_yes', 'declared_no', 'unknown')
    ),
    pool_version                INTEGER NOT NULL,
    seed_file_sha256            TEXT,
    counts_json                 TEXT,
    biometric_notice_version    TEXT,
    consents_json               TEXT,
    modalities_json             TEXT,
    backup_reference            TEXT,
    backup_destroy_by           TEXT,
    baseline_backup_reference   TEXT,
    baseline_destroy_by         TEXT,
    readiness_json              TEXT,
    closed_at                   TEXT,
    CHECK (confirmation_mode != 'builder_is_owner' OR interviewer_role = 'builder')
);

-- At most one open commissioning: the expression is the same constant in every open row, so the
-- partial unique index admits one of them (an index on the nullable `closed_at` itself would
-- enforce nothing, because NULLs are distinct). A new one after a closed one is a Python rule.
CREATE UNIQUE INDEX commissioning_records_one_open_idx
    ON commissioning_records ((1))
    WHERE closed_at IS NULL;

-- Absence is data: what the interview reached, one status per section (ADR 0024 decision 2). A
-- status is not a fact and is never written to the memory.
CREATE TABLE commissioning_sections (
    commissioning_id            INTEGER NOT NULL REFERENCES commissioning_records(id) ON DELETE CASCADE,
    section                     TEXT NOT NULL CHECK (
        section IN (
            'conditions', 'allergies', 'medications', 'devices', 'contacts', 'withhold',
            'secrets', 'documents', 'household', 'home', 'function'
        )
    ),
    status                      TEXT NOT NULL CHECK (
        status IN ('provided', 'none', 'unknown', 'declined', 'not_asked')
    ),
    recorded_at                 TEXT NOT NULL,
    PRIMARY KEY (commissioning_id, section)
);

PRAGMA user_version = 11;
COMMIT;
