# Iroko documentation manual implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

- **Status:** Complete.
- **Roadmap phase:** Documentation foundation; not a cognitive implementation
  phase.
- **Approved design:**
  [0007-iroko-documentation-manual-design.md](0007-iroko-documentation-manual-design.md)

**Goal:** Deliver the first accurate, bilingual entry point to Iroko: its
public character profile, public README, technical documentation portal, and
explicit routing away from obsolete bootstrap notes.

**Architecture:** Iroko is the reusable local-first cognitive product; its
public character profile is separate from runtime identity, memory, policy, and
hardware. The entry documents explain and link to canonical architecture rather
than reproducing or replacing it. The implementation changes Markdown only and
preserves the server/robot, public audio, provider, and cognitive boundaries.

**Provenance:** The technical portal makes the transition from the historical
pre-electronics roadmap (M3/M4) to the canonical cognitive foundation explicit.
It links the historical record and the audit protocol as context only; new work
continues from canonical architecture, the cognitive roadmap, and the named
current plan.

**Tech Stack:** Markdown, relative repository links, Git, `uv`, `pre-commit`,
and the root `justfile` verification commands.

## Global constraints

- [ ] Do not start until PR #22 is merged and the primary checkout's `main`
  contains its documentation portfolio. Do not copy its files manually or make
  this plan's branch a child of an unmerged PR.
- [ ] Work in a normal local feature branch from updated `main`; do not create
  or use a Git worktree for this repository.
- [ ] Read `AGENTS.md`, applicable `.codex/rules/`, the approved design, this
  plan, `docs/architecture/README.md`, `current-state.md`,
  `cognitive-architecture.md`, `personality-and-interaction.md`, ADR-0004,
  and the current `README.md`, `docs/SETUP.md`, and `docs/TOOLING.md` before
  editing.
- [ ] Change only the files listed in this plan. Do not change Python, tests,
  dependencies, settings, API schemas, audio contracts, `.env.example`, GitHub
  Actions, or generated files.
- [ ] English is canonical. Each changed public or technical entry document
  gets its Spanish equivalent in the same task.
- [ ] Label behavior as **Implemented**, **Planned**, or **Historical**. An
  implemented claim must link to code, a test, or `current-state.md`; a planned
  claim must link to the roadmap or a plan.
- [ ] Treat `roadmap-cerebro-agnostico-pre-electronica.md` as historical
  provenance: M3 is complete and M4 is only **implemented with historical
  closure not demonstrated**. Do not make it an operational plan or imply that
  an old M4 branch should be resumed.
- [ ] Document a PC development experience only. Raspberry Pi, homelab,
  OMNiBot 2000, electronics, physical actions, and deployment instructions are
  future vision, not supported operating procedures.
- [ ] Describe local providers as the primary path and cloud as an optional,
  authorized escalation under ADR-0004. Do not represent one model or provider
  as Iroko's permanent brain.
- [ ] Iroko's profile uses neutral Spanish. Its fiction cannot become a system
  memory, household fact, identity proof, authorization decision, or runtime
  behavior change.
- [ ] Use an evidence-first documentation loop for every task: first establish
  the missing or obsolete baseline (RED), then create the smallest accurate
  Markdown change (GREEN), then run the task's static verification. This is
  the TDD-equivalent for documentation-only work; do not introduce a test
  framework or code merely to satisfy the loop.

## File structure

| File | Action | Responsibility |
|---|---|---|
| `docs/product/iroko-profile.md` | Create | Canonical English public profile and product-fiction boundary. |
| `docs/es/product/iroko-profile.md` | Create | Semantically equivalent Spanish public profile. |
| `README.md` | Modify | Concise English public welcome and navigation; remove obsolete operational claims. |
| `README.es.md` | Create | Semantically equivalent Spanish public welcome and navigation. |
| `docs/README.md` | Create | Canonical English technical portal and reader routes. |
| `docs/es/README.md` | Create | Semantically equivalent Spanish technical portal. |
| `docs/SETUP.md` | Modify | Prominent Historical status and safe redirect to the portal. |
| `docs/TOOLING.md` | Modify | Prominent Historical status and safe redirect to the portal. |
| `docs/plans/0007-iroko-documentation-manual.md` | Modify at completion | Mark the plan complete only after every gate below passes. |

## Completion evidence

- **Merge base:** `c4381b2` (`c4381b2463563bad02fb9f31eff36820c168722f`).
- **Task commits:** `db1fcda`, `b030dfb`, `288ab26`, and `8d4f736`.
- **Successful verification:**

  ```powershell
  $requiredFiles = @(
    'README.md',
    'README.es.md',
    'docs/README.md',
    'docs/es/README.md',
    'docs/product/iroko-profile.md',
    'docs/es/product/iroko-profile.md',
    'docs/SETUP.md',
    'docs/TOOLING.md',
    'docs/plans/0007-iroko-documentation-manual.md'
  )
  $requiredFiles | ForEach-Object {
    if (-not (Test-Path $_)) { throw "Missing documentation deliverable: $_" }
  }
  git diff --check main...HEAD
  uv run pre-commit run --files README.md README.es.md docs/README.md docs/es/README.md docs/product/iroko-profile.md docs/es/product/iroko-profile.md docs/SETUP.md docs/TOOLING.md docs/plans/0007-iroko-documentation-manual.md
  ```

  All required files were present, `git diff --check main...HEAD` produced no
  output, and each applicable pre-commit hook passed. This documentation-only
  gate did not run external providers, download models, or claim clean-PC audio
  acceptance; Slice 2 owns that acceptance.

## Task 1: Create the public Iroko profile

**Files:**

```text
Create: docs/product/iroko-profile.md
Create: docs/es/product/iroko-profile.md
```

**Consumes:** `docs/architecture/personality-and-interaction.md`,
`docs/architecture/cognitive-architecture.md`, ADR-0004, and the approved
Plan 0007 design.

**Produces:** Stable profile pages that public README files can link to as
`docs/product/iroko-profile.md` and `docs/es/product/iroko-profile.md`.

- [ ] **Step 1: Establish the RED baseline.**

  Run:

  ```powershell
  Test-Path docs/product/iroko-profile.md
  Test-Path docs/es/product/iroko-profile.md
  ```

  Expected: both return `False`. Also read the existing personality document
  and record that its current voice says Chilean `vos`, while this approved
  public profile must use neutral Spanish and must not alter runtime behavior.

- [ ] **Step 2: Write the canonical English profile.**

  Create `docs/product/iroko-profile.md` with these exact sections:

  ```markdown
  # Meet Iroko
  > Status: Product profile. It does not describe runtime memory or policy.

  ## A small origin story
  ## What Iroko is
  ## How Iroko speaks
  ## What Iroko will not pretend
  ## Product boundary
  ## Learn more
  ```

  The origin story must combine three approved ideas: retro-technology roots,
  a warm household companion, and a careful explorer who learns only through
  evidence and permission. State that Iroko is a product identity, not an
  autonomous agent or a claim about consciousness. Link the product boundary
  to `../architecture/personality-and-interaction.md`,
  `../architecture/cognitive-architecture.md`, and
  `../adr/0004-local-first-cognitive-policy.md`.

- [ ] **Step 3: Write the Spanish equivalent.**

  Create `docs/es/product/iroko-profile.md` with the same section order and
  status meaning. Use neutral Spanish; do not introduce `vos`, regional slang,
  personal family claims, or new runtime capabilities. Its relative links must
  resolve to `../../architecture/`, `../../adr/`, and the English profile.

- [ ] **Step 4: Run GREEN static checks.**

  Run:

  ```powershell
  $profileFiles = @(
    'docs/product/iroko-profile.md',
    'docs/es/product/iroko-profile.md',
    'docs/architecture/personality-and-interaction.md',
    'docs/architecture/cognitive-architecture.md',
    'docs/adr/0004-local-first-cognitive-policy.md'
  )
  $profileFiles | ForEach-Object {
    if (-not (Test-Path $_)) { throw "Missing required profile target: $_" }
  }
  rg -n '^## (A small origin story|What Iroko is|How Iroko speaks|What Iroko will not pretend|Product boundary|Learn more)$' docs/product/iroko-profile.md
  rg -n '^## ' docs/es/product/iroko-profile.md
  git diff --check
  ```

  Expected: every file exists, the English headings are found exactly once,
  Spanish has the equivalent six sections, and `git diff --check` has no
  output.

- [ ] **Step 5: Commit the profile task.**

  ```powershell
  git add docs/product/iroko-profile.md docs/es/product/iroko-profile.md
  git commit -m "docs(product): add Iroko public profile"
  ```

## Task 2: Create the bilingual public welcome and technical portal

**Files:**

```text
Modify: README.md
Create: README.es.md
Create: docs/README.md
Create: docs/es/README.md
```

**Consumes:** Task 1 profile pages; `docs/architecture/README.md`,
`docs/architecture/current-state.md`, `docs/roadmap/cognitive-roadmap.md`,
`docs/plans/README.md`, and the root `justfile`.

**Produces:** A public welcome that links to a profile and portal, plus a
technical portal that routes visitors, developers, contributors, Codex, and
maintainers without requiring chat history.

- [ ] **Step 1: Establish the RED baseline.**

  Run:

  ```powershell
  Test-Path README.es.md
  Test-Path docs/README.md
  Test-Path docs/es/README.md
  rg -n '^# 🤖 OMNiBot 2000|ANTHROPIC_API_KEY|Phase 4 — Teleoperation' README.md
  ```

  Expected: the three files do not exist, and the current root README exposes
  the obsolete OMNiBot-centric title, cloud-key requirement, and unsupported
  phase roadmap. Do not preserve those as current operational claims.

- [ ] **Step 2: Replace the English public README with an accurate entry.**

  Rewrite `README.md` as a concise public document with this exact outline:

  ```markdown
  # Iroko
  > A local-first cognitive companion, built to be understandable and replaceable.

  ## Meet Iroko
  ## What exists today
  ## Principles that do not change
  ## Start here
  ## Current boundaries
  ## Project status
  ```

  Link `Meet Iroko` to `docs/product/iroko-profile.md`; identify Iroko as the
  reusable brain and OMNiBot 2000 as future experimental embodiment; link
  implemented facts only to `docs/architecture/current-state.md`; and link the
  documentation portal, architecture index, roadmap, and plans. The current
  boundaries must say that physical hardware guidance, autonomous action, and
  operational cloud escalation are not implemented. Do not include setup
  commands, an Anthropic key requirement, model download commands, or a claim
  that all use is fully offline today.

- [ ] **Step 3: Create the Spanish public README.**

  Create `README.es.md` with the same section order, link targets, status
  labels, and scope. Translate product prose naturally, but retain command and
  file names verbatim. Link the profile to `docs/es/product/iroko-profile.md`.

- [ ] **Step 4: Create the English technical portal.**

  Create `docs/README.md` with this exact outline:

  ```markdown
  # Iroko technical documentation
  > Status: Documentation portal. It is not an implementation plan.

  ## Start here
  ## Choose your route
  ## What is implemented today
  ## Canonical authority
  ## Documentation provenance
  ## Documentation status labels
  ## Current scope boundary
  ```

  `Choose your route` is a five-row table for visitor, new developer,
  contributor, Codex/architect, and maintainer/releaser. It must link only to
  files that exist at this slice: the profile, root README, architecture index,
  current state, roadmap, plans index, `AGENTS.md`, and `justfile`. It must say
  that the reproducible audio setup guide is delivered by Slice 2; do not link
  to nonexistent `docs/guides/` files. Define **Implemented**, **Planned**, and
  **Historical** exactly as this plan's global constraints require. In
  `Documentation provenance`, briefly link the historical pre-electronics
  roadmap and the cognitive foundation audit. State that M3/M4 are historical
  context, M4 has no demonstrated historical closure, and new work follows the
  canonical architecture index, current state, cognitive roadmap, and named
  current plan. Do not link to `docs/local/` or present either historical source
  as an executable plan.

- [ ] **Step 5: Create the Spanish technical portal.**

  Create `docs/es/README.md` with the same seven sections, five reader routes,
  and status semantics. Link to `../README.md`, `../product/`,
  `../../README.es.md`, and the canonical English architecture files as
  appropriate. State that English is the canonical technical source and the
  Spanish page is its maintained equivalent.

- [ ] **Step 6: Run GREEN static checks.**

  Run:

  ```powershell
  $entryFiles = @(
    'README.md',
    'README.es.md',
    'docs/README.md',
    'docs/es/README.md',
    'docs/product/iroko-profile.md',
    'docs/es/product/iroko-profile.md',
    'docs/architecture/README.md',
    'docs/architecture/current-state.md',
    'docs/architecture/roadmap-cerebro-agnostico-pre-electronica.md',
    'docs/architecture/cognitive-foundation-audit.md',
    'docs/roadmap/cognitive-roadmap.md',
    'docs/plans/README.md',
    'AGENTS.md',
    'justfile'
  )
  $entryFiles | ForEach-Object {
    if (-not (Test-Path $_)) { throw "Missing entry-document target: $_" }
  }
  rg -n '^## (Meet Iroko|What exists today|Principles that do not change|Start here|Current boundaries|Project status)$' README.md
  rg -n '^## (Start here|Choose your route|What is implemented today|Canonical authority|Documentation provenance|Documentation status labels|Current scope boundary)$' docs/README.md
  rg -n 'ANTHROPIC_API_KEY|Phase 4 — Teleoperation|Claude API' README.md
  git diff --check
  ```

  Expected: every required target exists, both English heading sets are found,
  the final `rg` finds no obsolete root README claim, and `git diff --check`
  has no output.

- [ ] **Step 7: Commit the entry-point task.**

  ```powershell
  git add README.md README.es.md docs/README.md docs/es/README.md
  git commit -m "docs: add Iroko documentation entry points"
  ```

## Task 3: Mark obsolete bootstrap notes as historical and route safely

**Files:**

```text
Modify: docs/SETUP.md
Modify: docs/TOOLING.md
```

**Consumes:** Task 2 documentation portal, current `justfile`, root
`pyproject.toml`, current architecture index, and both existing historical
notes.

**Produces:** Historical notes that remain available as provenance but cannot
be mistaken for current installation, dependency, CI, or quality instructions.

- [ ] **Step 1: Establish the RED baseline.**

  Run:

  ```powershell
  rg -n '^# OMNiBot|^> \*\*Status:\*\* Historical' docs/SETUP.md docs/TOOLING.md
  rg -n 'uv init|uv add|ANTHROPIC_API_KEY|commitizen.*Overkill' docs/SETUP.md docs/TOOLING.md
  ```

  Expected: both notes describe historical project bootstrap choices but lack a
  clear Historical status and redirect. Do not delete their contents in this
  slice; preserving provenance is intentional.

- [ ] **Step 2: Add accurate historical banners.**

  Insert directly below the title of each file:

  ```markdown
  > **Status:** Historical bootstrap note. It is preserved as project history,
  > not as current installation, dependency, CI, or quality instruction.
  > Start with [the Iroko technical documentation portal](../README.md).
  ```

  In `docs/SETUP.md`, add one sentence after the banner stating that it records
  initial workspace construction and may name obsolete commands, dependencies,
  and hardware assumptions. In `docs/TOOLING.md`, add one sentence stating that
  it records earlier tool evaluation and cannot override the root `justfile`,
  `pyproject.toml`, CI workflow, or runtime instructions. Do not alter the
  historical command blocks.

- [ ] **Step 3: Run GREEN static checks.**

  Run:

  ```powershell
  rg -n '^> \*\*Status:\*\* Historical bootstrap note\.' docs/SETUP.md docs/TOOLING.md
  rg -n '\]\(README\.md\)' docs/SETUP.md docs/TOOLING.md
  Test-Path docs/README.md
  git diff --check
  ```

  Expected: each note has one Historical banner, each redirects to the existing
  portal, `docs/README.md` exists, and `git diff --check` has no output.

- [ ] **Step 4: Commit the historical-routing task.**

  ```powershell
  git add docs/SETUP.md docs/TOOLING.md
  git commit -m "docs: mark bootstrap notes as historical"
  ```

## Task 4: Complete the documentation gate and record completion

**Files:**

```text
Modify: docs/plans/0007-iroko-documentation-manual.md
```

**Consumes:** Tasks 1-3, `docs/plans/README.md`, the root `justfile`, and the
current worktree diff.

**Produces:** A completed plan with recorded verification, while preserving the
plan index's cognitive readiness rules.

- [ ] **Step 1: Establish the RED baseline.**

  Run:

  ```powershell
  git status --short
  git diff --name-only main...HEAD
  ```

  Expected: only the eight entry/profile/historical documents and this plan are
  changed relative to updated `main`; no source, dependency, workflow, API, or
  generated file appears. Stop if another file is present rather than widening
  scope.

- [ ] **Step 2: Run the final documentation verification.**

  Run:

  ```powershell
  $requiredFiles = @(
    'README.md',
    'README.es.md',
    'docs/README.md',
    'docs/es/README.md',
    'docs/product/iroko-profile.md',
    'docs/es/product/iroko-profile.md',
    'docs/SETUP.md',
    'docs/TOOLING.md',
    'docs/plans/0007-iroko-documentation-manual.md'
  )
  $requiredFiles | ForEach-Object {
    if (-not (Test-Path $_)) { throw "Missing documentation deliverable: $_" }
  }
  git diff --check main...HEAD
  uv run pre-commit run --files README.md README.es.md docs/README.md docs/es/README.md docs/product/iroko-profile.md docs/es/product/iroko-profile.md docs/SETUP.md docs/TOOLING.md docs/plans/0007-iroko-documentation-manual.md
  ```

  Expected: all files exist, the diff check has no output, and each applicable
  pre-commit hook passes. Do not run external providers, download models, or
  claim a clean-PC audio run at this slice; Slice 2 owns that acceptance.

- [ ] **Step 3: Record plan completion.**

  Change this plan's status line from `Ready after PR #22 is merged into
  main.` to `Complete.` Add a `## Completion evidence` section after the file
  structure table with the merge-base commit, task commit IDs, and the exact
  successful verification commands from Step 2. Do not change
  `docs/plans/README.md`: its readiness language governs cognitive plans and
  must not be repurposed for this documentation-only slice.

- [ ] **Step 4: Commit the completion record.**

  ```powershell
  git add docs/plans/0007-iroko-documentation-manual.md
  git commit -m "docs(plans): complete Iroko entry documentation"
  ```

## Completion criteria

- [ ] The English and Spanish public README files accurately introduce Iroko,
  link to the profile and technical portal, and make no unsupported hardware,
  cloud, provider, or fully-offline claim.
- [ ] The English and Spanish technical portals route all five audiences to
  current files, clearly state English authority, and do not link to future
  guides that do not yet exist.
- [ ] The Iroko profile presents approved product fiction in neutral Spanish
  without becoming an identity, memory, authorization, cloud, or action claim.
- [ ] `docs/SETUP.md` and `docs/TOOLING.md` are unmistakably Historical and
  redirect readers to the portal without deleting their provenance.
- [ ] Internal links used by this slice resolve, `git diff --check` passes, and
  targeted documentation hooks pass.
- [ ] The final diff changes only the files enumerated in this plan and plan
  completion evidence records the actual commands and commits.
