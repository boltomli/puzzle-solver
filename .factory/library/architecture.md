# Repository Abstraction — Architecture

## 1. Current Architecture

### Component Overview

| Component | Role |
|-----------|------|
| **`models/puzzle.py`** | Pydantic v2 data models. `Project` is the root aggregate containing lists of `Character`, `Location`, `TimeSlot`, `Script`, `Fact`, `Deduction`, `Rejection`, `Hint`, `IgnoredEntity`. |
| **`storage/json_store.py`** | Low-level JSON I/O. Each project is one file (`data/{id}.json`). Uses `model_dump_json` / `model_validate_json`. |
| **`ui/state.py`** | `AppState` singleton — holds `current_project: Project`, owns all mutation methods (add/update/remove for every entity), calls `self.save()` after each mutation. |
| **UI pages** | Flet tab builders (`scripts.py`, `matrix.py`, `manage.py`, `review.py`, `settings.py`). Each reads from `app_state.current_project` and calls `app_state.*` methods to mutate. |
| **Services** | `prompt_engine.py` (prompt assembly), `deduction.py` (AI + cascade), `llm_service.py` (OpenAI client), `config.py` (API settings). Services read `Project` directly. |

### Data Flow

```
User interaction
      ↓
UI Page (Flet)  ──→  app_state.add_character(...)
                           ↓
                     AppState mutates Project in-memory
                     AppState calls self.save()
                           ↓
                     JsonStore.save_project(project)
                           ↓
                     data/{project_id}.json on disk
```

All mutations flow through AppState. UI pages call `page.update()` afterward to refresh the view.

### State Management

`app_state` is a **module-level singleton** (`AppState()`) imported by all UI pages and services. It holds:

- `current_project: Project | None` — the loaded project (entire object graph in memory)
- `store: JsonStore` — persistence backend

### Index Patterns

**3 deduplication indexes** (in AppState, rebuilt on project load):

| Index | Type | Purpose |
|-------|------|---------|
| `_fact_index` | `set[tuple[str,str,str]]` | Fast `(char_id, loc_id, ts_id)` lookup to skip duplicate facts |
| `_pending_index` | `set[tuple[str,str,str]]` | Skip duplicate pending deductions |
| `_rejection_index` | `set[tuple[str,str,str]]` | Skip already-rejected triples |

**7+ ad-hoc lookup maps** (rebuilt on every render in UI pages):

- `char_map = {c.id: c.name for c in proj.characters}` — review.py, manage.py
- `loc_map = {loc.id: loc.name for loc in proj.locations}` — review.py, manage.py
- `char_by_id = {c.id: c for c in proj.characters}` — matrix.py (×2)
- `loc_by_id = {lo.id: lo for lo in proj.locations}` — matrix.py (×2)
- `ts_label_map` (label/description→ID) — scripts.py (×2), matrix.py (×2)
- `ts_map = {ts.id: ts for ts in project.time_slots}` — prompt_engine.py (×2)
- `rejection_map = {r.from_deduction_id: r.reason ...}` — review.py

These are scattered, duplicated, and rebuilt from scratch on every UI render cycle.

---

## 2. Target Architecture

### Repository Protocol

A typed `Protocol` class defining the **complete data-access interface**. All reads and writes go through this contract. Framework-agnostic (no flet imports).

```python
class Repository(Protocol):
    # Project lifecycle
    def load_project(self, project_id: str) -> None: ...
    def save(self) -> None: ...
    # Entity CRUD (same signatures as current AppState methods)
    def add_character(self, ...) -> Character: ...
    def remove_character(self, character_id: str) -> bool: ...
    # ... etc for all entity types
    # Lookups (replaces ad-hoc maps)
    def get_character_name(self, char_id: str) -> str: ...
    def get_location_name(self, loc_id: str) -> str: ...
    def get_ts_label(self, ts_id: str) -> str: ...
```

### CacheManager

Centralized index/lookup layer that replaces all ad-hoc maps:

- Owns the 3 dedup indexes (`_fact_index`, `_pending_index`, `_rejection_index`)
- Owns entity lookup maps (`char_by_id`, `loc_by_id`, `ts_by_id`, etc.)
- Provides `rebuild(project)` to reconstruct all indexes from scratch
- Provides targeted `invalidate_*()` methods for surgical updates after mutations
- Single source of truth for all O(1) lookups

### JsonRepository

Concrete implementation of the Repository protocol:

- Wraps `JsonStore` for disk I/O
- Holds `current_project: Project` and a `CacheManager` instance
- All mutation methods update the project, invalidate relevant caches, then call `save()`
- Cascade delete logic lives here (removing a character also removes its facts, deductions, rejections)

### Slim AppState

Becomes a **thin coordinator** that delegates to Repository:

- Keeps the same public API (method signatures unchanged)
- Internally holds a `Repository` instance instead of managing data directly
- No more inline list comprehensions or index management
- UI pages continue importing `app_state` — zero UI changes needed

---

## 3. Component Relationships

```
┌─────────────┐     same public API     ┌────────────────┐
│  UI Pages   │ ──────────────────────→  │   AppState     │
│ (Flet)      │                          │ (thin coord)   │
└─────────────┘                          └───────┬────────┘
                                                 │ delegates
                                                 ▼
┌─────────────┐                          ┌────────────────┐
│  Services   │ ──── reads Project ────→ │  Repository    │
│ (prompt,    │                          │  (protocol)    │
│  deduction) │                          └───────┬────────┘
└─────────────┘                                  │ implements
                                                 ▼
                                         ┌────────────────┐
                                         │ JsonRepository  │
                                         │                │
                                         │  ┌────────────┐│
                                         │  │CacheManager││
                                         │  │ (indexes)  ││
                                         │  └────────────┘│
                                         │  ┌────────────┐│
                                         │  │ JsonStore   ││
                                         │  │ (disk I/O) ││
                                         │  └────────────┘│
                                         └────────────────┘
```

- **UI Pages → AppState**: unchanged call pattern, `app_state.add_character(...)` + `page.update()`
- **AppState → Repository**: all data logic delegated; AppState is just a pass-through
- **Repository → CacheManager**: lookups and index queries
- **Repository → JsonStore**: load/save JSON files to disk
- **Services → Project**: prompt_engine and deduction read from `Project` directly (passed as arg)

---

## 4. Key Invariants

1. **Framework-agnostic**: Repository, CacheManager, and JsonRepository never import `flet`. They remain fully testable with plain pytest.

2. **Cache coherence**: Every mutation in JsonRepository calls the appropriate `CacheManager.invalidate_*()` method before returning. No stale indexes.

3. **Cascade deletes**: Removing an entity (character, location, time slot) in the Repository also removes all referencing facts, deductions, and rejections. The current system does **not** cascade — this is a key improvement.

4. **Backward compatibility**: Existing JSON files load without migration. `Project._migrate_time_slots` handles the old string→TimeSlot format. No new file format changes.

5. **API stability**: AppState's public method signatures remain identical. UI pages and tests that call `app_state.add_character(name="X")` continue to work unchanged.

6. **Single rebuild point**: `CacheManager.rebuild(project)` is called once on project load, replacing the scattered per-render map constructions.

---

## 5. File Organization (Target)

```
src/
├── models/
│   └── puzzle.py                # Pydantic models (UNCHANGED)
├── storage/
│   ├── json_store.py            # Low-level JSON file I/O (UNCHANGED)
│   ├── repository.py            # NEW — Repository Protocol definition
│   ├── json_repository.py       # NEW — JsonRepository (implements Protocol)
│   └── cache_manager.py         # NEW — Centralized indexes & lookups
├── services/
│   ├── config.py                # (unchanged)
│   ├── deduction.py             # (unchanged)
│   ├── llm_service.py           # (unchanged)
│   └── prompt_engine.py         # (unchanged)
└── ui/
    ├── app.py                   # (unchanged)
    ├── state.py                 # REFACTORED — thin delegation to Repository
    └── pages/
        ├── scripts.py           # REFACTORED — use CacheManager lookups
        ├── matrix.py            # REFACTORED — use CacheManager lookups
        ├── manage.py            # REFACTORED — use CacheManager lookups
        ├── review.py            # REFACTORED — use CacheManager lookups
        └── settings.py          # (unchanged)
```

**3 new files** | **1 refactored file** (state.py) | **4 updated files** (UI pages drop ad-hoc maps)
