---
name: refactor-worker
description: Implements SQLite migration and parity-preserving storage refactors with TDD
---

# Refactor Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Use for features that:
- add or modify Python persistence/storage modules
- introduce SQLModel/SQLite schema and mappers
- preserve AppState/repository behavioral compatibility
- implement JSON import/migration flows
- add regression, parity, migration, and performance smoke tests

## Required Skills

None.

## Work Procedure

1. Read the feature, `mission.md`, mission `AGENTS.md`, and `.factory/library/architecture.md` before changing code.
2. Read every touched file fully, including adjacent tests and any callers that depend on the same API.
3. Write tests first:
   - add or update focused parity/migration/performance smoke tests covering each expected behavior item
   - run the new or focused tests first and confirm they fail for the intended reason
4. Implement the smallest storage-layer change that makes the tests pass while preserving current caller-visible behavior.
5. Prefer introducing new modules (`sqlite_*`, mapper/factory/import helpers) over invasive UI rewrites unless the feature explicitly requires UI changes.
6. For import or multi-record persistence flows, use transaction-safe behavior and verify failure paths, not only happy paths.
7. After focused tests pass, run:
   - `uv run ruff check src tests`
   - `uv run pytest tests/ -v`
8. If the feature is verification-focused and the implementation already satisfies the requested behavior, test-only completion is acceptable, but the added evidence must directly exercise every claimed surface.
9. If the feature touches the default load/list path or import flow, manually smoke the relevant path when feasible and record the observation; for storage-layer-only work, focused automated evidence can satisfy the feature if it directly proves the claimed behavior.
10. Do not leave TODOs or partial migration semantics undocumented in the handoff; explicitly state what remains undone.

## Example Handoff

```json
{
  "salientSummary": "Implemented SQLiteRepository parity for project lifecycle and core CRUD, keeping AppState behavior compatible while introducing SQLModel-backed persistence. Added focused parity tests plus full regression validation; all tests passed and default caller behavior remained unchanged.",
  "whatWasImplemented": "Added SQLModel table definitions and SQLite store/session helpers, implemented SQLiteRepository create/list/load/save and core entity CRUD, wired AppState/backend factory to use the new repository path, and added parity tests comparing SQLite-backed behavior against current expectations for project creation, loading, saving, character/location/script/fact/time-slot operations, and safe no-project-loaded failures.",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      {
        "command": "uv run ruff check src tests",
        "exitCode": 0,
        "observation": "All lint checks passed."
      },
      {
        "command": "uv run pytest tests/test_sqlite_repository.py -v",
        "exitCode": 0,
        "observation": "Focused SQLite parity tests passed."
      },
      {
        "command": "uv run pytest tests/ -v",
        "exitCode": 0,
        "observation": "Full regression suite passed."
      }
    ],
    "interactiveChecks": [
      {
        "action": "Opened the app's normal project flow after switching backend wiring and created/loaded a project.",
        "observed": "Project was immediately usable and reload showed the saved data correctly."
      }
    ]
  },
  "tests": {
    "added": [
      {
        "file": "tests/test_sqlite_repository.py",
        "cases": [
          {
            "name": "test_create_project_immediately_usable",
            "verifies": "SQLite-backed create flow preserves current_project usability."
          },
          {
            "name": "test_save_reload_preserves_core_entities",
            "verifies": "SQLite-backed save/load preserves core project state."
          }
        ]
      }
    ]
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- The feature requires changing mission boundaries, such as reintroducing startup JSON scanning or external database services.
- Existing tests fail for clearly unrelated reasons outside the feature scope.
- A required behavior is ambiguous, especially duplicate-import semantics or caller-visible AppState compatibility.
- The implementation reveals a broader architecture change is needed beyond the current feature description.