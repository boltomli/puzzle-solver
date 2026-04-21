# Architecture

## What belongs here

System structure, major components, relationships, data flow, and invariants for the active mission.

## Current system

- `src/models/puzzle.py` defines the domain model. `Project` is the aggregate root holding characters, locations, time slots, scripts, facts, deductions, rejections, hints, and ignored entities.
- `src/storage/json_store.py` persists one full project per JSON file and currently powers project listing, loading, and saving.
- `src/storage/json_repository.py` and `src/ui/state.py` expose an in-memory `current_project` workflow that UI pages and services rely on.
- Flet pages and services read project snapshots directly, so caller-visible behavior is currently tied to full-project load/save semantics.

## Target mission architecture

### Domain compatibility layer

- Keep `src/models/puzzle.py` as the caller-facing compatibility model.
- Workers should preserve existing `Project`/entity semantics, especially IDs, deduction states, and time-slot ordering.

### Persistence layer

- Introduce SQLite-backed persistence using SQLModel.
- Add SQLite-focused modules under `src/storage/` for:
  - schema/table definitions
  - engine/session/store helpers
  - row/domain mapping
  - explicit JSON import helpers
- The persistence layer must support the core chain only for this mission:
  - project
  - character
  - location
  - time slot
  - script
  - fact
  - deduction
  - rejection

### Repository boundary

- `src/storage/repository.py` remains the behavioral contract.
- The new SQLite repository must preserve caller-visible parity for create/list/load/save and core mutation flows.
- The repository should continue to expose a compatibility-friendly `current_project` snapshot initially, so UI call sites do not require a broad rewrite in this mission.

### Import boundary

- Legacy JSON is no longer a startup data source.
- JSON becomes an explicit import format selected by the user.
- Import must translate a JSON project into SQLite-backed storage while preserving visible semantics and leaving the source file untouched.

## Data flow

### Native project flow

User action in Flet UI  
→ `app_state.*` method  
→ active repository implementation  
→ SQLite persistence  
→ refreshed `current_project` compatibility snapshot  
→ UI re-render

### Import flow

User selects a JSON file  
→ import helper validates/parses JSON project  
→ repository/store writes into SQLite transactionally  
→ imported project becomes available in the default SQLite project list/load flow

## Key invariants

1. `AppState` public API remains stable for this mission.
2. Default startup must not scan legacy JSON files.
3. Import is the only supported bridge from legacy JSON into active storage.
4. SQLite remains local-only; no external database services are introduced.
5. Import failures must be atomic and must not create ghost projects.
6. Deduction dedup, accept/reject behavior, and cascade cleanup must remain parity-compatible.
7. Time-slot identity/order must remain stable across import, save, load, and reload.

## Worker guidance

- Prefer additive storage modules and targeted repository integration over invasive UI redesign.
- Optimize list/load/write paths through the storage boundary first.
- When uncertain, preserve old caller-visible behavior and surface ambiguity back to the orchestrator.
