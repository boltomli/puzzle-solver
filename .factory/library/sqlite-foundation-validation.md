# SQLite Foundation Validation Notes

- The milestone validator commands are sourced from `.factory/services.yaml`.
- Current validator set is:
  - `uv run pytest tests/ -v`
  - `uv run ruff check src tests`
  - `echo no typecheck configured`
- The repository currently has no dedicated typechecker configured, so scrutiny should record the typecheck step as intentionally absent rather than failed.
