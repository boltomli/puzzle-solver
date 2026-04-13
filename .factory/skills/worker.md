## Worker Skill — Puzzle Solver E2E + Flet Rewrite

You are a worker implementing features for the Puzzle Solver application.

### Environment
- Working directory: `C:\exp\puzzle-solver`
- Python: `.venv\Scripts\python` (3.13, Windows)
- Test command: `.venv\Scripts\python -m pytest tests/ -v`
- Package manager: uv (`uv sync` to install deps)
- OS: Windows (use `\` in paths, PowerShell commands)

### Key Guidelines
1. Read the mission AGENTS.md for full project context before starting
2. Read the specific files you need to modify BEFORE editing
3. **DO NOT MODIFY**: `src/models/puzzle.py`, `src/services/*`, `src/storage/json_store.py`, `config.json`
4. All UI text must be in **Chinese** (中文)
5. All state mutations go through `app_state` methods in `src/ui/state.py`
6. AppState must NOT import flet — keep it framework-agnostic
7. Preserve pure-logic functions tested by existing tests:
   - `build_matrix_data()` in `src/ui/pages/matrix.py` (tested by test_matrix.py)
   - `_create_single_deduction()`, `_create_deductions_from_facts()`, `_is_api_configured()` in `src/ui/pages/scripts.py` (tested by test_scripts.py)
8. Run tests after every change to catch regressions early
9. Use absolute paths when running commands (Windows)

### Flet Patterns
- Entry: `ft.app(target=main)` where `main(page: ft.Page)`
- Tabs: `ft.Tabs` with `ft.TabBar` + `ft.TabBarView`
- Dialog: `ft.AlertDialog` → `page.overlay.append(dlg)` → `dlg.open = True` → `page.update()`
- Snackbar: `page.snack_bar = ft.SnackBar(ft.Text("msg"))` → `page.snack_bar.open = True`
- After state changes: rebuild relevant controls and call `page.update()`
- Async handlers: `async def on_click(e):` is supported directly
