## Worker Skill — Puzzle Solver QoL

You are a worker implementing features for the Puzzle Solver application.

### Environment
- Working directory: `C:\exp\puzzle-solver`
- Python: `.venv\Scripts\python` (3.13)
- Test: `.venv\Scripts\python -m pytest tests/ -v`
- Package manager: uv

### Key Guidelines
1. Read AGENTS.md for full project context before starting
2. Read the specific files you need to modify BEFORE editing
3. Preserve existing code patterns (Chinese UI text, NiceGUI Quasar classes, closure factories for event handlers)
4. Run tests after making changes to verify no regressions
5. All state mutations go through `app_state` methods in `src/ui/state.py`
6. NiceGUI uses Quasar Vue components — use `.classes()` and `.props()` for styling
