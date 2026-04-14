---
name: refactor-worker
description: Implements Repository pattern refactoring features with TDD approach
---

# Refactor Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Features involving:
- Creating new Python modules (repository.py, cache_manager.py, json_repository.py)
- Refactoring existing modules (state.py, UI pages)
- Writing unit/integration tests for data layer operations
- Replacing ad-hoc patterns with centralized abstractions

## Required Skills

None — all work is Python backend code verified through pytest and ruff.

## Work Procedure

### Step 1: Understand the Feature

1. Read the feature description, preconditions, expectedBehavior, and verificationSteps carefully.
2. Read `.factory/library/architecture.md` for the target design.
3. Read `AGENTS.md` for constraints and boundaries.
4. If the feature modifies existing files, read those files FULLY before making any changes.
5. If the feature depends on files created by previous features, read those to understand the API surface.

### Step 2: Write Tests First (TDD — Red Phase)

1. Create the test file specified in verificationSteps (e.g., `tests/test_cache_manager.py`).
2. Write comprehensive test cases covering ALL items in expectedBehavior.
3. For each expected behavior item, write at least one test. For complex behaviors, write multiple tests covering happy path + edge cases.
4. Use `tmp_path` fixture for test isolation — create temp data directories, never use real `data/` directory.
5. Import the module you're about to create (it won't exist yet — that's expected).
6. Run the tests to confirm they fail: `.venv\Scripts\python -m pytest tests/test_<name>.py -v`
7. Verify failures are import/implementation errors, NOT test syntax errors.

### Step 3: Implement (Green Phase)

1. Create or modify the source files.
2. Follow patterns from existing code (read `src/ui/state.py` for naming conventions, method patterns).
3. For new files: add `from __future__ import annotations`, use type hints everywhere.
4. Implement incrementally — get one group of tests passing at a time.
5. Run tests frequently: `.venv\Scripts\python -m pytest tests/test_<name>.py -v`

### Step 4: Verify Thoroughly

1. Run ALL tests (not just new ones): `.venv\Scripts\python -m pytest tests/ -v --tb=short`
2. Run ruff on modified/new files: `.venv\Scripts\ruff check <files>`
3. If any existing test fails, the refactoring has a bug — fix it WITHOUT modifying the test file.
4. For features that modify UI pages: verify that `build_matrix_data` and related pure functions still produce correct output by running `tests/test_matrix.py`.
5. For the e2e-web-verification feature: start the app in web mode, verify port 8080 responds, then kill the process.

### Step 5: Manual Verification

1. Review your own code for:
   - Missing type hints
   - Inconsistent method signatures (compare with current AppState API)
   - Missing cache invalidation after mutations
   - Missing save() calls after mutations
2. Spot-check: pick 2-3 representative test scenarios and trace the data flow mentally.
3. If the feature touches AppState: verify the module-level singleton `app_state = AppState()` still works.

## Example Handoff

```json
{
  "salientSummary": "Implemented CacheManager with 7 index types (by-id, by-name, label-map, rejection-map, 3 dedup sets). Wrote 28 tests in test_cache_manager.py covering all index operations, invalidation, rebuild, rapid mutations, and edge cases. All 240 tests pass (28 new + 212 existing). Ruff clean.",
  "whatWasImplemented": "src/storage/cache_manager.py: CacheManager class with rebuild(project), invalidate_character(action, char), invalidate_location(action, loc), invalidate_time_slot(action, ts), invalidate_fact(action, fact), invalidate_deduction(action, ded, fact=None, rejection=None), invalidate_rejection(action, rej). Seven index categories: char_by_id, loc_by_id, ts_by_id, char_by_name, loc_by_name, ts_label_map, rejection_map, plus fact_index/pending_index/rejection_index sets. Also created src/storage/repository.py with Repository Protocol defining 25 methods matching AppState API.",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      {"command": ".venv\\Scripts\\python -m pytest tests/test_cache_manager.py -v", "exitCode": 0, "observation": "28 tests passed"},
      {"command": ".venv\\Scripts\\python -m pytest tests/ -q", "exitCode": 0, "observation": "240 passed in 3.8s"},
      {"command": ".venv\\Scripts\\ruff check src/storage/cache_manager.py src/storage/repository.py", "exitCode": 0, "observation": "All checks passed"}
    ],
    "interactiveChecks": []
  },
  "tests": {
    "added": [
      {"file": "tests/test_cache_manager.py", "cases": [
        {"name": "test_rebuild_populates_char_by_id", "verifies": "char_by_id index built on rebuild"},
        {"name": "test_invalidate_add_character", "verifies": "adding character updates char_by_id and char_by_name"},
        {"name": "test_rapid_mutations_consistent", "verifies": "burst of add/remove leaves indexes consistent"}
      ]}
    ]
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- A precondition file doesn't exist (previous feature not completed)
- Existing tests fail and the cause is NOT in your feature's scope
- Method signature conflict between Repository Protocol and current AppState
- CacheManager can't replicate an ad-hoc map's exact behavior (semantic mismatch)
- Feature scope is larger than expected (e.g., more files need changes than listed)
