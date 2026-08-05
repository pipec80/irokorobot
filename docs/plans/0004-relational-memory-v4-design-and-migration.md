# Plan 0004 — Relational memory v4 design and migration

## Status

Approved design for a future **Draft** implementation plan. This is the
decision and migration-design half of P0.4. It authorizes no SQL migration,
production code, data rewrite, or readiness change while Plan 0002 is the only
`Ready` plan.

## Purpose

Define the relational-memory v4 target before changing persistence. V4 makes
literal facts and entity-to-entity relationships distinct, keeps current SQLite
integer IDs, records predicate semantics and lifecycle metadata, and provides a
safe migration path from the current name-valued `facts.object_value` baseline.

The design prevents a future implementation from treating all triples as the
same data shape, replacing multi-value facts accidentally, persisting mutable
age, or converting an unresolved name into a false confirmed relationship.

## Authority and prerequisites

- [`memory-and-world-state.md`](../architecture/memory-and-world-state.md)
  defines literal facts versus relationships, predicate cardinality, lifecycle,
  retrieval order, and migration constraints.
- [`cognitive-architecture.md`](../architecture/cognitive-architecture.md)
  requires entity-ID relations, deterministic counts/ages, uncertainty, and
  no post-retrieval privacy filtering.
- [`cognitive-contracts.md`](../architecture/cognitive-contracts.md) fixes
  entity/fact references as SQLite integers and UUIDs for envelopes/evidence.
- [`cognitive-roadmap.md`](../roadmap/cognitive-roadmap.md) requires a reviewed
  design/migration before P0.4 implementation and places P0.5 authorization
  after the relational foundation.
- [Plan 0002](0002-active-person-context.md) and its completion evidence are
  prerequisites for an executable later plan. [Plan 0003's design](0003-typed-controller-and-deterministic-tools-design.md)
  supplies the future controller/tool seam but remains Draft.

## Current baseline and gap

Current `schema.sql` stores every assertion in `facts(entity_id, predicate,
object_value TEXT, confidence, source_memory_id, asserted_at, superseded_*)`.
`assert_fact()` supersedes every active value for the same `(entity_id,
predicate)`. `relations.py` finds relationships by matching text in
`object_value`; current tests seed values such as `Valentina hijo_de "Pipec"`.

This is useful historical data, but it cannot enforce a target entity ID,
predicate cardinality, relationship inverse semantics, validity period,
verification, visibility, sensitivity, or an unambiguous migration. It also
contains persisted `edad` values, which conflict with the target rule that age
is derived from a confirmed ISO `birth_date` and an explicit date.

## Approved v4 data model

### 1. Additive split, never in-place reinterpretation

V4 adds new tables. It does not repurpose `facts.object_value`, alter existing
row IDs, or delete legacy data. Existing `entities.id` and `facts.id` remain
integers and continue to identify old records. New v4 record IDs are also
SQLite integers; UUIDs remain for evidence/envelopes/correlation only.

The implementation plan will introduce these logical records:

| Record | Purpose | Required key fields |
|---|---|---|
| `literal_fact_v4` | Entity-to-typed-literal assertion. | integer ID, `subject_entity_id`, stable predicate ID, canonical value, confidence/basis, provenance, lifecycle, visibility, sensitivity. |
| `entity_relation_v4` | Entity-to-entity assertion. | integer ID, `source_entity_id`, stable predicate ID, `target_entity_id`, confidence/basis, provenance, lifecycle, visibility, sensitivity. |
| migration ledger | Explains each legacy row's v4 outcome. | legacy fact ID, outcome (`migrated`, `deferred`, `rejected`), target v4 ID when present, deterministic reason. |

Both v4 assertion types carry `asserted_at`, optional `confirmed_at`, optional
`valid_from`/`valid_to`, lifecycle status (`active`, `superseded`, `disputed`,
`revoked`), safe provenance reference, and optional confirmer entity ID. They
never retain raw image, audio, voiceprint, or embedding data.

`visibility` and `sensitivity` are persisted classifications, not a permission
decision. P0.5 evaluates actor/action/category/consent policy before retrieval;
missing policy remains denial or confirmation rather than a v4 read shortcut.

### 2. Registry-owned predicate semantics

A versioned, typed Python predicate registry is the source of write and query
semantics. It is not an LLM prompt, free-form database text, or dynamic plugin
catalog. Each entry declares:

- stable v4 predicate ID and legacy aliases;
- assertion kind: literal or entity relation;
- allowed subject/target entity types or literal value type;
- cardinality: single-current, multi-value, relation, or temporal;
- inverse-query rule and symmetry where applicable;
- ISO normalization/validation rule when relevant;
- lifecycle, confirmation, visibility, and sensitivity defaults.

V4 canonical technical IDs use unambiguous English identifiers, while Spanish
language parsing and legacy predicates map explicitly through the registry:

| V4 ID | Legacy aliases | Kind and semantics |
|---|---|---|
| `birth_date` | `fecha_nacimiento` | Single current ISO `YYYY-MM-DD` literal. |
| `likes`, `dislikes`, `prefers`, `allergic_to` | `le_gusta`, `odia`, `prefiere`, `alergico_a` | Multi-value literals; siblings coexist. |
| `child_of` | `hijo_de` | Relation: source child -> target parent; inverse query is `parent_of`. |
| `partner_of` | `pareja_de` | Symmetric relation; stored once, queried from either direction. |
| `pet_of` | `mascota_de` | Relation: source pet -> target caretaker/household person. |
| `lives_in`, `works_at` | `vive_en`, `trabaja_en` | Temporal relation only when the target resolves to an existing entity. |

`age`/`edad` has no v4 predicate and no migration target. A deterministic tool
derives age only from valid `birth_date` plus supplied `on_date`.

The registry is deliberately small. An unsupported legacy predicate remains
legacy/deferred rather than being guessed as a confirmed v4 meaning.

### 3. Relationship direction and inverse rules

Only one relationship assertion is persisted. Inverse names describe query
behavior, not duplicate rows. For example, `child_of(valentina_id, pipec_id)`
answers both “who is Valentina's parent?” and “which children does Pipec have?”
without storing two values that can diverge.

`partner_of` is symmetric; canonical pair ordering and a unique active-pair
constraint prevent mirrored duplicates. Relation count tools count active,
authorized v4 rows after P0.5 policy, never legacy text rows.

### 4. Lifecycle and cardinality rules

- A new confirmed single-current literal supersedes the prior active value,
  preserving its lifecycle history.
- A new multi-value literal coexists with siblings unless an explicit revocation
  targets that value.
- Temporal facts/relations close their active validity interval before a new
  current assertion begins; they do not erase history.
- Contradictory or insufficiently grounded candidate data is recorded only when
  later lifecycle policy permits it; it is not promoted by the migration.
- Revocation changes lifecycle status and normal retrieval, while audit/provenance
  references remain controlled by retention policy.

## Migration and compatibility design

### Phase A — Preflight and ledger

The future implementation runs locally against a backup/temporary copy and
creates v4 tables plus a migration ledger. It snapshots counts and validates
foreign keys, predicate registry version, row uniqueness, and target entity
types. It performs no cloud upload and does not re-run an LLM extractor.

### Phase B — Conservative classification

For every active legacy fact, classify deterministically:

1. migrate a literal only when its legacy predicate is registered and its value
   satisfies the v4 value rule (notably ISO `birth_date`);
2. migrate a relation only when its predicate is registered and its object name
   resolves to exactly one existing allowed target entity;
3. defer Spanish prose dates, duplicate/ambiguous names, unsupported predicates,
   negative relation text such as `ninguno`, `edad`, and historical/superseded
   rows unless a documented rule preserves them safely;
4. record every non-migration with a stable reason in the ledger.

The migration must never create target entities merely to make a name resolve,
choose between same-name people, convert a value to a relationship by heuristic,
or present a deferred record as a confirmed v4 fact.

### Phase C — Verified cutover and logical rollback

V4 readers prefer a validated v4 record. A compatibility adapter may consult
legacy rows only for a predicate/entity that has no v4 migration outcome, and
must label that result legacy/unverified rather than silently merging duplicate
truths. New writes use v4 once the approved implementation cutover is enabled;
they do not dual-write competing definitions.

Rollback is logical and non-destructive: disable the v4 reader/writer feature
and return to the intact legacy read path. Added tables and ledger remain for
audit; no rollback drops data. The implementation plan must test forward
migration, idempotence, disabled-v4 rollback behavior, and unchanged legacy
database readability.

## Questions and decisions log

| ID | Question | Alternatives considered | Decision | Why |
|---|---|---|---|---|
| D04-01 | Mutate `facts` in place or add v4 records? | Add nullable entity target/meta columns; replace `facts`; additive v4 tables. | Additive v4 tables. | Existing records and IDs remain readable, migration is auditable, and a polymorphic triple table does not hide literal-vs-relation semantics. |
| D04-02 | How are relationships stored? | Target display name; JSON target; SQLite integer entity ID. | `source_entity_id` + `target_entity_id` integers. | Names are presentation/aliases and can collide or change; integer IDs preserve graph identity and foreign keys. |
| D04-03 | How are inverse relations represented? | Store both directions; compute all inverse queries; store one row with registry rule. | Store one canonical row and query inverses. | Two rows can drift or contradict. Registry semantics make inverse/count behavior deterministic. |
| D04-04 | What happens to multi-value preferences? | Keep current one-value replacement; special-case each query; registry cardinality. | Registry declares multi-value coexistence. | Cardinality belongs to predicate semantics, preventing a new preference from deleting unrelated values. |
| D04-05 | What happens to `edad` and prose birth dates? | Migrate text; ask LLM to normalize; defer unless valid ISO. | No age migration; only valid ISO `birth_date` migrates. | Age is derived and LLM/date guessing would create false precision. Deferred data remains inspectable in legacy storage. |
| D04-06 | How should v4 predicates be named? | Preserve mixed Spanish names; dynamically infer aliases; stable English IDs plus explicit aliases. | Stable English v4 IDs with explicit Spanish legacy aliases. | It aligns target architecture (`birth_date`, `child_of`) while retaining Spanish interaction/extraction vocabulary through a reviewable mapping. |
| D04-07 | Can migration create entities or resolve ambiguity heuristically? | Create named entities; choose first match; defer ambiguous data. | Defer. | Migration is not extraction or identity fusion; it must preserve uncertainty instead of manufacturing confirmed graph edges. |
| D04-08 | How is rollback achieved in SQLite? | Destructive down migration; dual-write forever; logical rollback with legacy preserved. | Logical rollback and audited ledger. | SQLite schema removal is risky and dual writes create divergence. Legacy remains intact while the reader/writer switch is reversible. |
| D04-09 | Does v4 metadata itself grant retrieval access? | Visibility tag is enough; confidence threshold; P0.5 policy. | P0.5 policy. | Classification and authorization are separate; a known relation still cannot bypass actor/action/consent evaluation. |

## Explicit non-goals

- Create, execute, or install any SQL migration now.
- Implement P0.2/P0.3/P0.5, authorization, onboarding, world state, lifecycle
  automation, cloud, biometric, audio, vision, or hardware work.
- Delete, rewrite, upload, or automatically reclassify existing household data.
- Treat `facts` legacy values as policy-authorized, entity-ID relationships, or
  confirmed knowledge merely because a migration can parse them.
- Add a graph database, new vector database, ORM, framework, dependency, or
  production multi-agent component.

## Readiness conditions for Plan 0005 implementation

The future Plan 0005 may become `Ready` only after P0.2 and P0.3 are Complete
and a current-tree review confirms this design. Its canonical scope must
include the exact SQL migration version, registry API, compatibility reader,
write cutover, fixture database cases, migration ledger assertions, rollback
test, and P0.5-safe retrieval boundary. Any departure from this model needs an
approved ADR or a documented replacement decision first.
