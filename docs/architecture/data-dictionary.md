# Data dictionary

The one document that says what every table of Iroko's SQLite database is for, who owns it, what
it holds and how long it lives. It is checked by tests: `tests/unit/test_schema_guards.py` fails
when a table or a column of a clean, fully migrated database is missing here (or documented here
and absent from the schema), when a table has no primary key, when a foreign key has no full index,
when a table this plan touched leaves a foreign key on SQLite's default rule, or when a section
lacks a field below. Schema version at the time of writing: **22** (Plan 0085, ADR 0038,
ADR 0032 decision 1; Plan 0086 added `archived_at`; Plan 0087 the audit kind of an export). Counts about the data itself come from `iroko-admin health`, never from here.

How to read a table section:

- **Domain** is one of `memory` (what the owner said and what was derived from it), `identity`
  (who people are, what they consented to and may do) and `administration` (the record of who
  changed what, and of the installation itself).
- **Owner module** is the only module with SQL on the table (a path under `server/src/server/`).
  A second module reads or writes it only through the owner's functions, with the two exceptions
  the guards of ADR 0031 name (the importer and the consent revocation).
- **Classification** is one of: *household personal data* (facts about people and the home),
  *sensitive personal data* (may carry health, location or security data; the row's `sensitivity`
  says which), *biometric* (face or voice evidence, ADR 0016), *credential* (a verifier of a
  secret), *conversation content* (what was heard and said), *audit, no values* (who, what, when,
  never the value) or *system state* (nothing about a person).
- **Retention** says when a row leaves and which code removes it.
- A column marked `FK` has a declared foreign key; the rule after it is its `ON DELETE`.

## Tables

### admin_audit

- **Purpose:** One row per attempt of `iroko-admin` that wrote, exported or deleted something, with its outcome; never the value.
- **Owner module:** `memory/admin_audit.py`
- **Domain:** administration
- **Classification:** audit, no values
- **Retention:** Kept for the life of the installation; no purge job.

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key, AUTOINCREMENT |
| `recorded_at` | TEXT | exact instant, NOT NULL |
| `actor_label` | TEXT | NOT NULL, 1 to 80 characters |
| `actor_role` | TEXT | NOT NULL, `owner` or `builder` |
| `channel` | TEXT | NOT NULL, always `admin_local` |
| `operation` | TEXT | NOT NULL, closed list (`add`, `change`, `revoke`, `grant`, `export`, `delete`, `list`: a listing of the documents, migration 023) |
| `target_kind` | TEXT | NOT NULL, closed list (pool literal, pool relation, care contact, conversation consent, conversation record, household data: an export, migration 022; document, migration 023) |
| `field_id` | TEXT | catalogue id of the field, no value; for an export `all`, `person:<id>` or `person`; for a document its source id, or none |
| `target_entity_id` | INTEGER | FK `entities`, SET NULL |
| `outcome` | TEXT | NOT NULL, `applied` or `refused` |
| `reason` | TEXT | closed refusal reason, no value |

| Index | Columns | Query it serves |
|---|---|---|
| `admin_audit_recorded_at_idx` | `recorded_at DESC, id DESC` | `iroko-admin audit`: the newest rows first |
| `admin_audit_target_entity_id_idx` | `target_entity_id` | the SET NULL when an entity is deleted |

### authorization_audit_events

- **Purpose:** One row per policy decision (who asked which action on which categories, allowed or denied, by which policy).
- **Owner module:** `memory/household_authorization.py`
- **Domain:** administration
- **Classification:** audit, no values
- **Retention:** Kept for the life of the installation; no purge job.

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key, AUTOINCREMENT |
| `actor_entity_id` | INTEGER | FK `entities`, SET NULL |
| `target_entity_id` | INTEGER | FK `entities`, SET NULL |
| `action` | TEXT | NOT NULL, a closed list in Python |
| `data_categories` | TEXT | NOT NULL, the category names (JSON array text) |
| `decision` | TEXT | NOT NULL, `allowed`, `denied` or `requires_confirmation` |
| `policy_id` | TEXT | NOT NULL, a closed list in Python |
| `reason` | TEXT | NOT NULL, closed reason code |
| `correlation_id` | TEXT | NOT NULL, the turn's id |
| `evaluated_at` | TEXT | exact instant, NOT NULL |
| `expires_at` | TEXT | exact instant of the grant the decision used, or NULL |

| Index | Columns | Query it serves |
|---|---|---|
| `authorization_audit_events_correlation_idx` | `correlation_id, evaluated_at` | every decision of one turn, in order |
| `authorization_audit_events_actor_entity_id_idx` | `actor_entity_id` | the SET NULL when an entity is deleted |
| `authorization_audit_events_target_entity_id_idx` | `target_entity_id` | the SET NULL when an entity is deleted |

### care_contacts

- **Purpose:** The people the owner named to be called (emergency, caregiver, doctor, key holder), with phone and the three permissions each has.
- **Owner module:** `memory/care_contacts.py`
- **Domain:** identity
- **Classification:** sensitive personal data
- **Retention:** Kept; a revoked contact keeps its row with `revoked_at`. The seed replacement deletes the rows of an import channel while the commissioning is open.

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key, AUTOINCREMENT |
| `owner_entity_id` | INTEGER | NOT NULL, FK `entities`, RESTRICT |
| `contact_entity_id` | INTEGER | NOT NULL, FK `entities`, RESTRICT |
| `role` | TEXT | NOT NULL, closed list |
| `relationship` | TEXT | 1 to 40 characters, or NULL |
| `phone` | TEXT | NOT NULL, `+` and 9 to 16 characters |
| `phone_alt` | TEXT | same shape, or NULL |
| `call_order` | INTEGER | 1 or more, or NULL; unique among the active contacts of an owner |
| `has_key` | INTEGER | NOT NULL, 0 or 1 |
| `may_receive_health_info` | INTEGER | NOT NULL, 0 or 1 |
| `may_view_activity` | INTEGER | NOT NULL, 0 or 1 |
| `visibility` | TEXT | NOT NULL, always `personal` |
| `sensitivity` | TEXT | NOT NULL, `private` or `location` |
| `asserted_by_entity_id` | INTEGER | FK `entities`, SET NULL |
| `channel` | TEXT | NOT NULL, the write channel |
| `confirmed_by_entity_id` | INTEGER | FK `entities`, SET NULL |
| `confirmed_at` | TEXT | exact instant, NOT NULL |
| `created_at` | TEXT | exact instant, NOT NULL (the writer supplies it; see *Not tuned yet*) |
| `revoked_at` | TEXT | exact instant, or NULL while active |

| Index | Columns | Query it serves |
|---|---|---|
| `care_contacts_active_role_idx` | unique `owner_entity_id, contact_entity_id, role` where active | one active contact per person and role |
| `care_contacts_active_order_idx` | unique `owner_entity_id, call_order` where active and ordered | one active contact per position in the call order |
| `care_contacts_owner_entity_id_idx` | `owner_entity_id` | the contacts of an owner; the RESTRICT check |
| `care_contacts_contact_entity_id_idx` | `contact_entity_id` | the RESTRICT check |
| `care_contacts_asserted_by_entity_id_idx` | `asserted_by_entity_id` | the SET NULL when an entity is deleted |
| `care_contacts_confirmed_by_entity_id_idx` | `confirmed_by_entity_id` | the SET NULL when an entity is deleted |

### commissioning_records

- **Purpose:** The acta of the alta: who interviewed, how the owner confirmed, the hashes and counts of each import, the consents and the closing.
- **Owner module:** `memory/commissioning.py`
- **Domain:** administration
- **Classification:** system state
- **Retention:** Kept for the life of the installation. At most one is open at a time.

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key, AUTOINCREMENT |
| `installation_id` | TEXT | NOT NULL, 36 characters (a UUID) |
| `started_at` | TEXT | exact instant, NOT NULL |
| `interviewer_label` | TEXT | NOT NULL, 1 to 80 characters |
| `interviewer_role` | TEXT | NOT NULL, closed list |
| `confirmation_mode` | TEXT | NOT NULL, closed list; `builder_is_owner` needs a `builder` interviewer |
| `disk_encryption` | TEXT | NOT NULL, `declared_yes`, `declared_no` or `unknown` |
| `pool_version` | INTEGER | NOT NULL |
| `seed_file_sha256` | TEXT | hash of the imported file, or NULL |
| `counts_json` | TEXT | counts per import, or NULL |
| `biometric_notice_version` | TEXT | or NULL |
| `consents_json` | TEXT | or NULL |
| `modalities_json` | TEXT | or NULL |
| `backup_reference` | TEXT | a label, never a path with a name |
| `backup_destroy_by` | TEXT | a day, or NULL |
| `baseline_backup_reference` | TEXT | or NULL |
| `baseline_destroy_by` | TEXT | a day, or NULL |
| `readiness_json` | TEXT | or NULL |
| `closed_at` | TEXT | exact instant, or NULL while open |

| Index | Columns | Query it serves |
|---|---|---|
| `commissioning_records_one_open_idx` | unique `(1)` where `closed_at IS NULL` | at most one open commissioning |

### commissioning_sections

- **Purpose:** One status per section of the acta ("absence is data": provided, none, unknown, declined, not asked).
- **Owner module:** `memory/commissioning.py`
- **Domain:** administration
- **Classification:** system state
- **Retention:** Deleted with its record (CASCADE); a section is also replaced while the replacement window is open.

| Column | Type | Rules |
|---|---|---|
| `commissioning_id` | INTEGER | NOT NULL, part of the primary key, FK `commissioning_records`, CASCADE |
| `section` | TEXT | NOT NULL, part of the primary key, closed list of eleven |
| `status` | TEXT | NOT NULL, closed list of five |
| `recorded_at` | TEXT | exact instant, NOT NULL |

The primary key `(commissioning_id, section)` is the index of the foreign key.

### conversation_consent_grants

- **Purpose:** The person's consent to keep the record of what they say (ADR 0027), with the notice version they saw.
- **Owner module:** `memory/conversation_consent.py`
- **Domain:** identity
- **Classification:** household personal data
- **Retention:** Kept; revoking sets `revoked_at` and the conversation record is deleted by the revocation.

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key, AUTOINCREMENT |
| `person_entity_id` | INTEGER | NOT NULL, FK `entities`, RESTRICT |
| `purpose` | TEXT | NOT NULL, always `conversation_storage` |
| `notice_version` | TEXT | NOT NULL, 1 to 20 characters |
| `granted_at` | TEXT | exact instant, NOT NULL |
| `revoked_at` | TEXT | exact instant, or NULL while active |

| Index | Columns | Query it serves |
|---|---|---|
| `conversation_consent_active_idx` | unique `person_entity_id` where active | one active consent per person; "may this person's words be kept" |
| `conversation_consent_grants_person_entity_id_idx` | `person_entity_id` | the RESTRICT check (a partial index does not cover revoked rows) |

### conversation_episodes

- **Purpose:** The summary of one closed conversation (one row per record), written by the model while nobody talks.
- **Owner module:** `memory/conversation_episodes.py`
- **Domain:** memory
- **Classification:** conversation content
- **Retention:** Kept while the owner's conversation consent stands, after its record's turns expire (Plan 0086); deleted with its record (consent withdrawn, a PIN deletion) or by `iroko-admin forget episode`, which sets the record's `episode_status` to `skipped`. `expires_at` repeats the raw record's expiry.

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key, AUTOINCREMENT |
| `source_record_id` | INTEGER | NOT NULL, UNIQUE, FK `conversation_records`, CASCADE |
| `owner_entity_id` | INTEGER | NOT NULL, FK `entities`, CASCADE |
| `visibility` | TEXT | NOT NULL, always `personal` |
| `sensitivity` | TEXT | NOT NULL, closed list of five |
| `summary` | TEXT | NOT NULL, 1 to 1000 characters |
| `model` | TEXT | NOT NULL, the summarizing model's name |
| `created_at` | TEXT | exact instant, NOT NULL |
| `expires_at` | TEXT | exact instant, NOT NULL |

| Index | Columns | Query it serves |
|---|---|---|
| `conversation_episodes_owner_idx` | `owner_entity_id` | the owner's episodes; the CASCADE |
| (automatic, from UNIQUE) | `source_record_id` | the episode of a record; the CASCADE |

### conversation_records

- **Purpose:** One conversation (a window of turns), its owner, its times, its expiry and the state of its episode.
- **Owner module:** `memory/conversation_record.py`
- **Domain:** memory
- **Classification:** conversation content
- **Retention:** Expires 365 days after closing with the owner's verified voice, 30 days without (settings); the oldest are purged while the turns exceed the byte cap (`memory/retention.py`). A purged record whose episode is written loses its turns and keeps its row (the diary outlives the raw text, Plan 0086); any other goes whole. The owner can delete one or all with the PIN, through the deletion register (`deletions.jsonl` beside the database, replayed at every start).

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key, AUTOINCREMENT |
| `previous_id` | INTEGER | FK `conversation_records`, SET NULL; the conversation before this one |
| `owner_entity_id` | INTEGER | NOT NULL, FK `entities`, CASCADE |
| `started_at` | TEXT | exact instant, NOT NULL |
| `last_turn_at` | TEXT | exact instant, NOT NULL |
| `closed_at` | TEXT | exact instant, or NULL while open |
| `eligible` | INTEGER | NOT NULL, 0 or 1: the owner's verified voice was heard |
| `expires_at` | TEXT | exact instant; NULL exactly while open |
| `episode_status` | TEXT | NOT NULL, `pending`, `done`, `skipped` or `failed` |
| `episode_attempts` | INTEGER | NOT NULL, 0 or more |

| Index | Columns | Query it serves |
|---|---|---|
| `conversation_records_one_open_idx` | unique `(closed_at IS NULL)` where open | at most one open record |
| `conversation_records_expiry_idx` | `expires_at` | the purge of expired records |
| `conversation_records_pending_idx` | `episode_status, closed_at` where closed | the next record whose episode is pending |
| `conversation_records_owner_idx` | `owner_entity_id` | the CASCADE on an owner |
| `conversation_records_previous_idx` | `previous_id` | the SET NULL on a deleted record |

### conversation_turns

- **Purpose:** One row per turn: what the owner's voice said (heard), what the robot answered (said) and who the voice was judged to be (Plan 0085 D-5).
- **Owner module:** `memory/conversation_record.py`
- **Domain:** memory
- **Classification:** conversation content
- **Retention:** Deleted with its record (CASCADE); what was derived from a turn (`recall_units`, `memory_candidates`, `pending_topics`) goes with it.

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key, AUTOINCREMENT |
| `record_id` | INTEGER | NOT NULL, FK `conversation_records`, CASCADE |
| `correlation_id` | TEXT | NOT NULL, UNIQUE, the turn's request id |
| `said_at` | TEXT | exact instant, NOT NULL, CHECK of the format |
| `verdict` | TEXT | NOT NULL, `verified`, `not_verified`, `not_owner` or `not_checked` |
| `heard` | TEXT | NOT NULL, at most 2000 characters |
| `said` | TEXT | NOT NULL, at most 4000 characters |
| `bytes` | INTEGER | generated, STORED: `length(CAST(heard AS BLOB)) + length(CAST(said AS BLOB))`, what the turn weighs for the segment limit and the cap |

The table is STRICT. `length` of a BLOB counts bytes on every supported SQLite (`octet_length` needs 3.43).

| Index | Columns | Query it serves |
|---|---|---|
| `conversation_turns_record_idx` | `record_id, said_at, id` | the turns of a record in order; the CASCADE |
| (automatic, from UNIQUE) | `correlation_id` | the turn of a request |

### document_sections

- **Purpose:** One section of an owner's document: its text cut under the embedding model's window, with its heading path (Plan 0088, ADR 0034). Searched by words and by vector.
- **Owner module:** `memory/document_store.py`
- **Domain:** memory
- **Classification:** document content (origin `document`; transformation `original` for `md` and `txt`, `extracted` for `pdf` and `camera`, read from the source's format)
- **Retention:** Deleted with its source (CASCADE); the triggers remove its word-index row and its vector in the same statement. Its `heading` and `body` never change (a trigger refuses it).

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key, AUTOINCREMENT |
| `source_id` | INTEGER | NOT NULL, FK `document_sources`, CASCADE |
| `position` | INTEGER | NOT NULL, from 0; `(source_id, position)` is unique |
| `heading` | TEXT | NOT NULL, the heading path (may be empty), at most 400 characters, immutable |
| `body` | TEXT | NOT NULL, 1 to 1200 characters (the section cap), immutable |
| `body_sha256` | TEXT | NOT NULL, the body's SHA-256 (64 hex characters) |
| `embedding_model` | TEXT | the model that computed its vector, or NULL while it has none |
| `vector_refused_by` | TEXT | the model that refused it as longer than its window, or NULL; such a section stays searchable by its words |

| Index | Columns | Query it serves |
|---|---|---|
| (automatic, from UNIQUE) | `source_id, position` | the sections of a source in order; the CASCADE from a deleted source |
| `document_sections_unembedded_idx` | `id` where `embedding_model IS NULL` | the next sections to embed |
| `document_sections_model_idx` | `embedding_model` where `embedding_model IS NOT NULL` | the model guard: sections of another model, and the sections to re-embed |

### document_sections_fts

- **Purpose:** The word index over `document_sections.heading` and `body` (FTS5, external content, no accents, `secure-delete` on). A virtual table: its shadow tables are not described.
- **Owner module:** `memory/document_store.py`
- **Domain:** memory
- **Classification:** document content
- **Retention:** Follows `document_sections` through its triggers (`document_sections_ai`, `document_sections_ad`).

| Column | Type | Rules |
|---|---|---|
| `heading` | FTS5 | the indexed heading path |
| `body` | FTS5 | the indexed text, the same as `document_sections.body` |

### document_sections_vec

- **Purpose:** The 768-dimension cosine vector of each section (sqlite-vec `vec0`), partitioned by owner and filtered by level and source inside the KNN. A virtual table: its shadow tables are not described.
- **Owner module:** `memory/document_store.py`
- **Domain:** memory
- **Classification:** document content
- **Retention:** Follows `document_sections`: deleted by `document_sections_ad`; replaced with its model in one transaction by `store_section_vector`.

| Column | Type | Rules |
|---|---|---|
| `rowid` | INTEGER | the section's id |
| `owner_entity_id` | INTEGER | partition key, the source's owner |
| `level` | TEXT | metadata, the source's level |
| `source_id` | INTEGER | metadata, the section's source |
| `embedding` | FLOAT[768] | the vector |

### document_sources

- **Purpose:** One document of the owner: a file loaded with `iroko-admin docs add` or at the alta, or a camera reading the owner chose to keep (Plan 0088, ADR 0034). The same file twice is refused by its hash.
- **Owner module:** `memory/document_store.py`
- **Domain:** memory
- **Classification:** document content (the title may be sensitive)
- **Retention:** Kept until the owner removes it (`iroko-admin docs remove`: a `document` line in the deletion register, then a physical delete of the source, its sections, word rows and vectors); deleted with its owner (CASCADE).

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key, AUTOINCREMENT |
| `owner_entity_id` | INTEGER | NOT NULL, FK `entities`, CASCADE |
| `title` | TEXT | NOT NULL, 1 to 120 characters |
| `file_sha256` | TEXT | NOT NULL, the file's SHA-256 (64 hex characters); `(owner_entity_id, file_sha256)` is unique |
| `format` | TEXT | NOT NULL, `md`, `txt`, `pdf` or `camera` |
| `level` | TEXT | NOT NULL, `normal` or `sensitive` |
| `channel` | TEXT | NOT NULL, `admin_local`, `import_file` (the alta) or `voice_camera` |
| `loaded_at` | TEXT | exact instant, NOT NULL |
| `loaded_by_entity_id` | INTEGER | FK `entities`, SET NULL: who loaded it |
| `sections` | INTEGER | NOT NULL, how many sections it has |
| `characters` | INTEGER | NOT NULL, how many characters its sections hold |

| Index | Columns | Query it serves |
|---|---|---|
| (automatic, from UNIQUE) | `owner_entity_id, file_sha256` | the same file refused; the owner's documents; the CASCADE on the owner |
| `document_sources_loaded_by_idx` | `loaded_by_entity_id` | the SET NULL when the loader is deleted |

### entities

- **Purpose:** Every person, place, object or concept the memory refers to; the node the facts and relations hang from.
- **Owner module:** `memory/declarative.py`
- **Domain:** memory
- **Classification:** household personal data
- **Retention:** Kept. Rows are deleted only for an import that left them with no rows and no contacts (`declarative.py`).

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key, AUTOINCREMENT |
| `name` | TEXT | NOT NULL; `(name, type)` is unique |
| `type` | TEXT | NOT NULL, closed list of eight |
| `attributes` | TEXT | NOT NULL, JSON object text |
| `aliases` | TEXT | NOT NULL, JSON array text |
| `created_at` | TEXT | exact instant, NOT NULL (the writer supplies it; see *Not tuned yet*) |
| `updated_at` | TEXT | exact instant, NOT NULL |

| Index | Columns | Query it serves |
|---|---|---|
| `entities_type_idx` | `type` | the entities of a kind (people) |
| (automatic, from UNIQUE) | `name, type` | the entity named so |

### entity_relations_v4

- **Purpose:** A relation between two entities (parent of, partner of, friend of) with its lifecycle, validity, visibility and who asserted it. The `_v4` is history (the fourth schema of relations), kept so names in older documents stay true.
- **Owner module:** `memory/relational_v4.py`
- **Domain:** memory
- **Classification:** household personal data
- **Retention:** Kept; a correction supersedes the row (`lifecycle`, `superseded_at`, `superseded_by`), never edits it. The seed replacement deletes the rows of an import channel while the commissioning is open.

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key, AUTOINCREMENT |
| `source_entity_id` | INTEGER | NOT NULL, FK `entities`, CASCADE; differs from the target |
| `predicate` | TEXT | NOT NULL, from the predicate registry |
| `target_entity_id` | INTEGER | NOT NULL, FK `entities`, CASCADE |
| `confidence` | REAL | NOT NULL, 0 to 1 |
| `source_memory_id` | INTEGER | FK `memories`, SET NULL |
| `confirmed_by_entity_id` | INTEGER | FK `entities`, SET NULL |
| `asserted_at` | TEXT | exact instant, NOT NULL |
| `confirmed_at` | TEXT | exact instant, or NULL |
| `valid_from` | TEXT | a day or a month (world time), or NULL |
| `valid_to` | TEXT | a day or a month, or NULL |
| `lifecycle` | TEXT | NOT NULL, `active`, `superseded`, `disputed`, `revoked` or `expired` |
| `visibility` | TEXT | NOT NULL, closed list of six |
| `sensitivity` | TEXT | NOT NULL, closed list of seven |
| `superseded_at` | TEXT | exact instant, or NULL |
| `superseded_by` | INTEGER | FK `entity_relations_v4`, SET NULL |
| `asserted_by_entity_id` | INTEGER | FK `entities`, SET NULL |
| `channel` | TEXT | the write channel, or NULL for rows older than the channel |
| `archived_at` | TEXT | exact instant while the owner keeps it set aside (no reader says, offers or searches it), or NULL (Plan 0086, migration 21) |

| Index | Columns | Query it serves |
|---|---|---|
| `entity_relations_v4_active_triple_idx` | unique `source_entity_id, predicate, target_entity_id` where active | one active relation per triple |
| `entity_relations_v4_active_source_predicate_idx` | `source_entity_id, predicate` where active | the relations out of an entity |
| `entity_relations_v4_active_target_predicate_idx` | `target_entity_id, predicate` where active | the relations into an entity |
| `entity_relations_v4_source_entity_id_idx` | `source_entity_id` | the CASCADE on an entity |
| `entity_relations_v4_target_entity_id_idx` | `target_entity_id` | the CASCADE on an entity |
| `entity_relations_v4_asserted_by_entity_id_idx` | `asserted_by_entity_id` | the SET NULL on an entity |
| `entity_relations_v4_confirmed_by_entity_id_idx` | `confirmed_by_entity_id` | the SET NULL on an entity |
| `entity_relations_v4_superseded_by_idx` | `superseded_by` | the SET NULL on a relation |
| `entity_relations_v4_source_memory_id_idx` | `source_memory_id` | the SET NULL on a memory |

### face_consent_grants

- **Purpose:** The person's consent to use their face to recognise them (ADR 0016).
- **Owner module:** `memory/biometric_consent.py`
- **Domain:** identity
- **Classification:** biometric
- **Retention:** Kept; revoking sets `revoked_at` and deletes the face profiles and `vec_faces` rows first.

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key, AUTOINCREMENT |
| `person_entity_id` | INTEGER | NOT NULL, FK `entities`, RESTRICT |
| `purpose` | TEXT | NOT NULL, always `owner_authentication` |
| `granted_at` | TEXT | exact instant, NOT NULL |
| `revoked_at` | TEXT | exact instant, or NULL while active |

| Index | Columns | Query it serves |
|---|---|---|
| `face_consent_grants_active_idx` | unique `person_entity_id` where active | one active consent per person |
| `face_consent_grants_person_entity_id_idx` | `person_entity_id` | the RESTRICT check |

### face_profiles

- **Purpose:** One enrolled face of a person; the embedding itself is the `vec_faces` row with the same id.
- **Owner module:** `vision/faces.py`
- **Domain:** identity
- **Classification:** biometric
- **Retention:** Deleted, with its `vec_faces` row, by the consent revocation (`memory/biometric_consent.py`). A person with a profile cannot be deleted (RESTRICT).

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key, AUTOINCREMENT (a deleted top id is never handed out again) |
| `entity_id` | INTEGER | NOT NULL, FK `entities`, RESTRICT |
| `label` | TEXT | NOT NULL, the profile's label |
| `created_at` | TEXT | exact instant, NOT NULL, CHECK of the format, no default |

The table is STRICT.

| Index | Columns | Query it serves |
|---|---|---|
| `idx_face_profiles_entity` | `entity_id` | the profiles of a person; the RESTRICT check |

### household_role_assignments

- **Purpose:** The role each person holds in the household (owner, adult, child, guest) and who granted it.
- **Owner module:** `memory/household_authorization.py`
- **Domain:** identity
- **Classification:** household personal data
- **Retention:** Kept; a revoked assignment keeps its row with `revoked_at`.

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key, AUTOINCREMENT |
| `person_entity_id` | INTEGER | NOT NULL, FK `entities`, RESTRICT |
| `role` | TEXT | NOT NULL, `owner`, `adult`, `child` or `guest` |
| `grantor_entity_id` | INTEGER | FK `entities`, SET NULL |
| `reason` | TEXT | NOT NULL, closed reason code |
| `granted_at` | TEXT | exact instant, NOT NULL (the writer supplies it; see *Not tuned yet*) |
| `revoked_at` | TEXT | exact instant, or NULL while active |

| Index | Columns | Query it serves |
|---|---|---|
| `household_role_assignments_active_person_idx` | unique `person_entity_id` where active | one active role per person |
| `household_role_assignments_single_active_owner_idx` | unique `role` where owner and active | exactly one active owner |
| `household_role_assignments_person_entity_id_idx` | `person_entity_id` | the RESTRICT check |
| `household_role_assignments_grantor_entity_id_idx` | `grantor_entity_id` | the SET NULL on an entity |

### literal_facts_v4

- **Purpose:** A fact about an entity as a literal value (a birthday, a medication, a phone); the same lifecycle and validity as a relation.
- **Owner module:** `memory/relational_v4.py`
- **Domain:** memory
- **Classification:** sensitive personal data
- **Retention:** Kept; a correction supersedes the row, never edits it. The seed replacement deletes the rows of an import channel while the commissioning is open.

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key, AUTOINCREMENT |
| `subject_entity_id` | INTEGER | NOT NULL, FK `entities`, CASCADE |
| `predicate` | TEXT | NOT NULL, from the predicate registry |
| `value_text` | TEXT | NOT NULL, the value (never logged) |
| `confidence` | REAL | NOT NULL, 0 to 1 |
| `source_memory_id` | INTEGER | FK `memories`, SET NULL |
| `confirmed_by_entity_id` | INTEGER | FK `entities`, SET NULL |
| `asserted_at` | TEXT | exact instant, NOT NULL |
| `confirmed_at` | TEXT | exact instant, or NULL |
| `valid_from` | TEXT | a day or a month (world time), or NULL |
| `valid_to` | TEXT | a day or a month, or NULL |
| `lifecycle` | TEXT | NOT NULL, `active`, `superseded`, `disputed`, `revoked` or `expired` |
| `visibility` | TEXT | NOT NULL, closed list of six |
| `sensitivity` | TEXT | NOT NULL, closed list of seven |
| `superseded_at` | TEXT | exact instant, or NULL |
| `superseded_by` | INTEGER | FK `literal_facts_v4`, SET NULL |
| `asserted_by_entity_id` | INTEGER | FK `entities`, SET NULL |
| `channel` | TEXT | the write channel, or NULL for rows older than the channel |
| `archived_at` | TEXT | exact instant while the owner keeps it set aside (no reader says, offers or searches it), or NULL (Plan 0086, migration 21) |

| Index | Columns | Query it serves |
|---|---|---|
| `literal_facts_v4_active_value_idx` | unique `subject_entity_id, predicate, value_text` where active | one active fact per subject, predicate and value |
| `literal_facts_v4_active_subject_predicate_idx` | `subject_entity_id, predicate` where active | the active facts of an entity |
| `literal_facts_v4_subject_entity_id_idx` | `subject_entity_id` | the CASCADE on an entity |
| `literal_facts_v4_asserted_by_entity_id_idx` | `asserted_by_entity_id` | the SET NULL on an entity |
| `literal_facts_v4_confirmed_by_entity_id_idx` | `confirmed_by_entity_id` | the SET NULL on an entity |
| `literal_facts_v4_superseded_by_idx` | `superseded_by` | the SET NULL on a fact |
| `literal_facts_v4_source_memory_id_idx` | `source_memory_id` | the SET NULL on a memory |

### memories

- **Purpose:** The retired first memory store (ADR 0027 decision 9). Kept only because two tables still name it as the source of a fact; nothing reads or writes it.
- **Owner module:** `memory/schema.sql`
- **Domain:** memory
- **Classification:** household personal data
- **Retention:** No new row can be inserted (the trigger `memories_retired` aborts it); rows from before stay until a later migration drops the table.

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key, AUTOINCREMENT |
| `kind` | TEXT | NOT NULL, `episodic`, `semantic` or `reflection` |
| `content` | TEXT | NOT NULL |
| `summary` | TEXT | or NULL |
| `metadata` | TEXT | NOT NULL, JSON object text |
| `importance` | REAL | NOT NULL, 0 to 1 |
| `related_entities` | TEXT | NOT NULL, JSON array text |
| `last_accessed_at` | TEXT | instant, or NULL |
| `access_count` | INTEGER | NOT NULL |
| `created_at` | TEXT | instant, NOT NULL |
| `archived_at` | TEXT | instant, or NULL |

| Index | Columns | Query it serves |
|---|---|---|
| `memories_kind_idx` | `kind` where not archived | none today (retired) |
| `memories_importance_idx` | `importance DESC` where not archived | none today (retired) |

### memory_candidates

- **Purpose:** What the owner said that the robot may want to remember, until the owner confirms or rejects it (ADR 0021). The value exists only while the candidate is live.
- **Owner module:** `memory/candidates.py`
- **Domain:** memory
- **Classification:** sensitive personal data
- **Retention:** A live candidate expires after 24 hours (`memory_candidate_ttl_seconds`) or when it runs out of offers; on resolution the value is scrubbed (`value_text` and `value_key` become NULL, enforced by a CHECK) and the write-ahead log is truncated. A candidate linked to a turn (`source_turn_id`) is deleted with that turn, so with its record whether the record is purged or deleted (CASCADE, Plan 0085 D-8); one with no stored turn lives out its own expiry.

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key, AUTOINCREMENT |
| `subject_person_id` | INTEGER | NOT NULL, FK `entities`, CASCADE |
| `asserted_by_person_id` | INTEGER | NOT NULL, FK `entities`, CASCADE |
| `predicate` | TEXT | NOT NULL, from the predicate registry |
| `value_text` | TEXT | the value while live, NULL after (CHECK) |
| `value_key` | TEXT | the normalised value while live, NULL after (CHECK) |
| `status` | TEXT | NOT NULL, `proposed`, `offered`, `confirmed`, `rejected` or `expired` |
| `channel` | TEXT | NOT NULL, `voice_classic` or `voice_stream` |
| `source_correlation_id` | TEXT | NOT NULL, the turn it came from |
| `offer_correlation_id` | TEXT | the turn that offered it, or NULL |
| `resolution_correlation_id` | TEXT | the turn that resolved it, or NULL |
| `proposed_at` | TEXT | exact instant, NOT NULL |
| `offered_at` | TEXT | exact instant, or NULL |
| `resolved_at` | TEXT | exact instant, or NULL |
| `expires_at` | TEXT | exact instant, NOT NULL |
| `offer_count` | INTEGER | NOT NULL, 0 or more |
| `promoted_fact_id` | INTEGER | FK `literal_facts_v4`, SET NULL |
| `source_turn_id` | INTEGER | FK `conversation_turns`, CASCADE; NULL for a candidate older than the turn rows |

| Index | Columns | Query it serves |
|---|---|---|
| `memory_candidates_live_value_idx` | unique `subject_person_id, predicate, value_key` where live | no duplicate live candidate |
| `memory_candidates_subject_status_idx` | `subject_person_id, status` | the candidates of a person in a state; the CASCADE on the subject |
| `memory_candidates_live_expiry_idx` | `expires_at` where live | the housekeeping that expires lapsed candidates |
| `memory_candidates_source_turn_idx` | `source_turn_id` | the CASCADE from a deleted turn |
| `memory_candidates_unlinked_idx` | `source_correlation_id` where `source_turn_id IS NULL` | linking the candidates proposed before their turn was appended |
| `memory_candidates_asserted_by_person_id_idx` | `asserted_by_person_id` | the CASCADE on the asserter |
| `memory_candidates_promoted_fact_id_idx` | `promoted_fact_id` | the SET NULL on a fact |

### meta

- **Purpose:** Small flags that survive a restart (for example that the alta is complete); never domain data.
- **Owner module:** `memory/meta.py`
- **Domain:** administration
- **Classification:** system state
- **Retention:** Kept; a flag is overwritten in place.

| Column | Type | Rules |
|---|---|---|
| `key` | TEXT | primary key |
| `value` | TEXT | NOT NULL |
| `updated_at` | TEXT | exact instant, NOT NULL (the writer supplies it; see *Not tuned yet*) |

### owner_pin_credentials

- **Purpose:** The verifier of the owner's PIN (a memory-hard hash with its salt), never the PIN.
- **Owner module:** `memory/owner_credentials.py`
- **Domain:** identity
- **Classification:** credential
- **Retention:** Kept; a changed or revoked PIN keeps its row with `revoked_at`. A person with a credential cannot be deleted (RESTRICT).

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key, AUTOINCREMENT |
| `person_entity_id` | INTEGER | NOT NULL, FK `entities`, RESTRICT |
| `algorithm` | TEXT | NOT NULL, always `scrypt` |
| `parameters_json` | TEXT | NOT NULL, the hash parameters |
| `salt` | BLOB | NOT NULL |
| `verifier` | BLOB | NOT NULL |
| `created_at` | TEXT | exact instant, NOT NULL (the writer supplies it; see *Not tuned yet*) |
| `updated_at` | TEXT | exact instant, NOT NULL |
| `revoked_at` | TEXT | exact instant, or NULL while active |

| Index | Columns | Query it serves |
|---|---|---|
| `owner_pin_credentials_active_owner_idx` | unique `person_entity_id` where active | one active credential per person |
| `owner_pin_credentials_person_entity_id_idx` | `person_entity_id` | the RESTRICT check |

### pending_topics

- **Purpose:** A thing the owner said they would do (an appointment, a trip) that the robot may ask about on the due day (ADR 0029).
- **Owner module:** `memory/pending_store.py`
- **Domain:** memory
- **Classification:** sensitive personal data
- **Retention:** Deleted more than two days past its due day, asked or not (`conversation_jobs.py` calls `delete_expired`); also deleted with its record or its source turn (CASCADE).

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key, AUTOINCREMENT |
| `owner_entity_id` | INTEGER | NOT NULL, FK `entities`, CASCADE |
| `source_record_id` | INTEGER | NOT NULL, FK `conversation_records`, CASCADE |
| `correlation_id` | TEXT | NOT NULL, UNIQUE, the turn's request id |
| `said_day` | TEXT | NOT NULL, a household day (`date(x) IS x`) |
| `due_day` | TEXT | NOT NULL, a household day, not before `said_day` |
| `topic` | TEXT | 1 to 40 characters, NULL exactly while unnamed |
| `heard` | TEXT | the words to name it from, NULL once named |
| `state` | TEXT | NOT NULL, `unnamed`, `open` or `asked` |
| `sensitivity` | TEXT | NOT NULL, `normal` or `medical` |
| `created_at` | TEXT | exact instant, NOT NULL |
| `asked_at` | TEXT | exact instant, NOT NULL exactly when asked |
| `naming_attempts` | INTEGER | NOT NULL, 0 or more |
| `source_turn_id` | INTEGER | FK `conversation_turns`, CASCADE; NULL for a topic older than the turn rows |
| `archived_at` | TEXT | exact instant while the owner keeps it set aside (no reader says, offers or searches it), or NULL (Plan 0086, migration 21) |

| Index | Columns | Query it serves |
|---|---|---|
| `pending_topics_owner_state_due_idx` | `owner_entity_id, state, due_day` | the topics due for an owner; the CASCADE on the owner |
| `pending_topics_record_idx` | `source_record_id` | the CASCADE from a deleted record |
| `pending_topics_source_turn_idx` | `source_turn_id` | the CASCADE from a deleted turn |
| (automatic, from UNIQUE) | `correlation_id` | the topic of a request |

### recall_units

- **Purpose:** One thing the owner can ask the robot to recall: the owner's words of a verified turn, or the summary of an episode (ADR 0028). Searched by words and by vector.
- **Owner module:** `memory/recall_store.py`
- **Domain:** memory
- **Classification:** conversation content
- **Retention:** Deleted with its record, episode, turn or owner (CASCADE); the triggers remove its word-index row and its vector in the same statement. Its `body` never changes (a trigger refuses it).

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key, AUTOINCREMENT |
| `owner_entity_id` | INTEGER | NOT NULL, FK `entities`, CASCADE |
| `source_record_id` | INTEGER | NOT NULL, FK `conversation_records`, CASCADE |
| `episode_id` | INTEGER | FK `conversation_episodes`, CASCADE; set exactly for an episode unit |
| `kind` | TEXT | NOT NULL, `turn` or `episode` |
| `body` | TEXT | NOT NULL, 1 to 2000 characters, immutable |
| `said_at` | TEXT | exact instant, NOT NULL |
| `visibility` | TEXT | NOT NULL, always `personal` |
| `sensitivity` | TEXT | NOT NULL, closed list of five |
| `correlation_id` | TEXT | the turn's request id; set exactly for a turn unit |
| `embedding_model` | TEXT | the model that computed its vector, or NULL while it has none |
| `occurred_start` | TEXT | first day of what happened, or NULL (CHECK with `occurred_end`) |
| `occurred_end` | TEXT | last day of what happened, or NULL |
| `turn_id` | INTEGER | FK `conversation_turns`, CASCADE; NULL for a unit older than the turn rows; unique |
| `archived_at` | TEXT | exact instant while the owner keeps it set aside (no reader says, offers or searches it), or NULL (Plan 0086, migration 21) |

| Index | Columns | Query it serves |
|---|---|---|
| `recall_units_owner_time_idx` | `owner_entity_id, said_at` | the owner's units in a time window; the CASCADE on the owner |
| `recall_units_record_idx` | `source_record_id` | the CASCADE from a deleted record |
| `recall_units_unembedded_idx` | `id` where `embedding_model IS NULL` | the next units to embed |
| `recall_units_owner_occurred_idx` | `owner_entity_id, occurred_start` where set | units by when the event happened |
| `recall_units_turn_idx` | unique `turn_id` | the unit of a turn; the CASCADE from a deleted turn |
| `recall_units_one_per_episode_idx` | unique `episode_id` | one unit per episode (turn units have a NULL, and NULLs are distinct); the CASCADE from a deleted episode |
| `recall_units_model_idx` | `embedding_model, owner_entity_id` where `embedding_model IS NOT NULL` | the model guard: the owner's units of another model, and the units to re-embed |

### recall_units_fts

- **Purpose:** The word index over `recall_units.body` (FTS5, external content, no accents, `secure-delete` on). A virtual table: its shadow tables are not described.
- **Owner module:** `memory/recall_store.py`
- **Domain:** memory
- **Classification:** conversation content
- **Retention:** Follows `recall_units` through its triggers (`recall_units_ai`, `recall_units_ad`).

| Column | Type | Rules |
|---|---|---|
| `body` | FTS5 | the indexed text, the same as `recall_units.body` |

### recall_units_vec

- **Purpose:** The 768-dimension cosine vector of each unit (sqlite-vec `vec0`), partitioned by owner and filtered by sensitivity. A virtual table: its shadow tables are not described.
- **Owner module:** `memory/recall_store.py`
- **Domain:** memory
- **Classification:** conversation content
- **Retention:** Follows `recall_units`: deleted by `recall_units_ad`; replaced with its model in one transaction by `store_vector`. Its sensitivity follows the unit's through `recall_units_au_sensitivity`.

| Column | Type | Rules |
|---|---|---|
| `rowid` | INTEGER | the unit's id |
| `owner_entity_id` | INTEGER | partition key, the unit's owner |
| `sensitivity` | TEXT | metadata, the unit's sensitivity |
| `embedding` | FLOAT[768] | the vector |

### vec_faces

- **Purpose:** The 512-dimension embedding of each enrolled face (sqlite-vec `vec0`), keyed by the id of its `face_profiles` row. A virtual table: its shadow tables are not described.
- **Owner module:** `vision/faces.py`
- **Domain:** identity
- **Classification:** biometric
- **Retention:** Deleted with its profile by the consent revocation (`memory/biometric_consent.py`). A row without a profile is an orphan that `iroko-admin health` counts.

| Column | Type | Rules |
|---|---|---|
| `rowid` | INTEGER | the `face_profiles` id |
| `embedding` | FLOAT[512] | the vector |

### voice_consent_grants

- **Purpose:** The person's consent to use their voice as evidence of who is speaking.
- **Owner module:** `memory/voice_consent.py`
- **Domain:** identity
- **Classification:** biometric
- **Retention:** Kept; revoking sets `revoked_at` and deletes the voice profiles first.

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key, AUTOINCREMENT |
| `person_entity_id` | INTEGER | NOT NULL, FK `entities`, RESTRICT |
| `purpose` | TEXT | NOT NULL, always `speaker_evidence` |
| `granted_at` | TEXT | exact instant, NOT NULL |
| `revoked_at` | TEXT | exact instant, or NULL while active |

| Index | Columns | Query it serves |
|---|---|---|
| `voice_consent_grants_active_idx` | unique `person_entity_id` where active | one active consent per person |
| `voice_consent_grants_person_entity_id_idx` | `person_entity_id` | the RESTRICT check |

### voice_profiles

- **Purpose:** One enrolled voiceprint of a person, with the model that computed it (a voiceprint of another model is never compared).
- **Owner module:** `voice/voiceprints.py`
- **Domain:** identity
- **Classification:** biometric
- **Retention:** Deleted by the consent revocation (`memory/voice_consent.py`). A person with a profile cannot be deleted (RESTRICT).

| Column | Type | Rules |
|---|---|---|
| `id` | INTEGER | primary key, AUTOINCREMENT (a deleted top id is never handed out again) |
| `entity_id` | INTEGER | NOT NULL, FK `entities`, RESTRICT |
| `label` | TEXT | NOT NULL, the profile's label |
| `embedding` | BLOB | NOT NULL, the voiceprint |
| `model_id` | TEXT | NOT NULL, the model that computed it |
| `created_at` | TEXT | exact instant, NOT NULL, CHECK of the format, no default |

The table is STRICT.

| Index | Columns | Query it serves |
|---|---|---|
| `idx_voice_profiles_entity` | `entity_id` | the profiles of a person; the RESTRICT check |

## Time format

An **instant** is UTC ISO 8601 with microseconds and an explicit offset, always 32 characters:
`2026-11-03T10:00:00.000000+00:00`. A text comparison is then a time comparison. Instants are
written by one Python module only (`server/timestamps.py`, `instant_text`); a writer passes the
instant, and the newest tables (`conversation_turns`, `face_profiles`, `voice_profiles`) have no
SQL default for it and a `CHECK` of the exact format. The exact check, which `iroko-admin health`
applies to every `TEXT` column named `*_at` of every live table (the columns come from the schema,
not from a list), is:

```sql
length(x) = 32
AND x GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
AND strftime('%Y-%m-%dT%H:%M:%S', substr(x, 1, 19)) IS substr(x, 1, 19)
```

A **day** (`said_day`, `due_day`, `occurred_start`, `occurred_end`) is an ISO date in the
household's zone (`date(x) IS x`). A **validity bound** (`valid_from`, `valid_to` of facts and
relations) is a day (`YYYY-MM-DD`) or a month (`YYYY-MM`). Migration 20 converted the older
19-character (`YYYY-MM-DD HH:MM:SS`) and 25-character (`...+00:00` without fraction) values to the
exact form and aborts on any value it cannot read as an instant.

## Deliberate denormalizations

- **`conversation_records.expires_at` and `conversation_episodes.expires_at`.** The episode repeats
  its record's expiry so a purge by expiry needs no join; the retention job writes both together.
- **`recall_units.said_at`, `owner_entity_id` and `sensitivity`.** A unit repeats the time of its
  turn and the owner and sensitivity of its record, so a search filters inside one query and the
  vector partition and metadata equal the row's; `store_vector` and a trigger keep them equal.
- **`recall_units.body`.** The words of the turn are copied (a unit is also an episode summary) and
  made immutable by a trigger, so the word index never goes stale.
- **`conversation_turns.bytes`.** The weight of a turn is stored, generated from its two texts, so
  the segment limit, the cap and the record's byte count share one definition.
- **`conversation_turns.heard` and `said`.** Turns are rows now; the former JSON array of turns on
  the record is gone (migration 18).
- **`memory_candidates.source_correlation_id`** and the other correlation ids are request ids for
  the logs and the audit, kept beside the `source_turn_id` foreign key that carries the relation.
- **JSON text columns** (`entities.attributes`, `entities.aliases`, `commissioning_records.*_json`,
  `owner_pin_credentials.parameters_json`) hold a closed document a reader loads whole; nothing
  queries inside them.

## Naming

Tables are plural snake_case nouns; a name ending `_v4` is history, not a version to choose.
Columns are snake_case: `id`, `<thing>_entity_id` for a reference to `entities` (or
`<thing>_person_id` where the row is about a person), `<thing>_id` for any other reference,
`*_at` for an instant, `*_day` for a day, `valid_from` and `valid_to` for world time, `*_json` for
JSON text. An index is `<table>_<what>_idx`; the older profile tables keep `idx_<table>_<what>`.
A partial unique index names its rule (`..._active_...`, `..._one_open_...`).

## Not tuned yet

Nothing here is tuned for scale: the database holds a household's few thousand rows and every
query below is measured only by its plan, never by a benchmark. A measured change waits for its
trigger (ADR 0031 decision 12):

- The count and sum of a record's turns (`COUNT(*)`, `SUM(bytes)`) find the record's rows by
  `conversation_turns_record_idx` and read `bytes` from the table, since SQLite never covers a
  generated column with an index; a record holds at most `CONVERSATION_SEGMENT_MAX_TURNS` rows.
  The space cap sums the whole table once per purge run.
- The FTS5 tokenizer is `unicode61 remove_diacritics 2`. A `trigram` tokenizer comparison on a real
  Spanish corpus, `int8` vectors and durability pragmas wait for a scale test that asks for them.
- Several older `*_at` columns (`entities`, `memories`, `care_contacts.created_at`,
  `household_role_assignments`, `owner_pin_credentials`, `meta`, `face_consent_grants`,
  `voice_consent_grants`, `literal_facts_v4`, `entity_relations_v4`) still carry
  `DEFAULT (datetime('now'))`, a second source of time in the old 19-character form. Every writer
  now supplies the exact instant, so the default is never used; removing it needs a table rebuild
  each and waits for the next migration that rebuilds that table.
- `PRAGMA optimize` runs when a connection opens; no table has hand-tuned statistics.
