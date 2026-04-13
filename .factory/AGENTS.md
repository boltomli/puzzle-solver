<coding_guidelines>
# AGENTS.md — Puzzle Solver QoL Mission

## Project Overview
Puzzle Solver is a Flet-based desktop/web application for script-based mystery games (剧本杀).
It uses a Character × Location × Time reasoning matrix with AI-powered deduction.

## Tech Stack
- **Python 3.13** via uv package manager
- **Flet** (Cross-platform UI framework — desktop + web)
- **Pydantic v2** for data models
- **OpenAI SDK** for LLM API calls
- **pytest** + **pytest-asyncio** for testing

## Project Structure
```
puzzle-solver/
├── main.py                    # Entry point (Flet app)
├── build.py                   # Flet packaging script
├── pyproject.toml             # Project config
├── .python-version            # 3.13
├── src/
│   ├── models/puzzle.py       # Pydantic data models
│   ├── services/
│   │   ├── config.py          # Config load/save (config.json)
│   │   ├── deduction.py       # AI + cascade deduction service
│   │   ├── llm_service.py     # OpenAI-compatible API client
│   │   └── prompt_engine.py   # Prompt assembly
│   ├── storage/json_store.py  # JSON file persistence
│   └── ui/
│       ├── app.py             # Flet main layout, tabs, project selector
│       ├── state.py           # AppState singleton (framework-agnostic)
│       └── pages/
│           ├── scripts.py     # Script management tab
│           ├── matrix.py      # Reasoning matrix tab
│           ├── manage.py      # Entity management tab
│           ├── review.py      # Deduction review tab
│           └── settings.py    # API settings tab
├── tests/                     # pytest test suite (156 tests)
│   ├── test_e2e.py            # E2E data flow tests
│   ├── test_state.py          # AppState business logic tests
│   ├── test_matrix.py         # build_matrix_data tests
│   ├── test_scripts.py        # Script helper function tests
│   ├── test_deduction.py      # Cascade deduction tests
│   ├── test_models.py         # Pydantic model tests
│   ├── test_storage.py        # JSON persistence tests
│   ├── test_llm_service.py    # LLM service tests
│   └── test_prompt_engine.py  # Prompt engine tests
└── .github/workflows/         # CI/CD
```

## Baseline Test Command
```bash
cd C:\exp\puzzle-solver && .venv\Scripts\python -m pytest tests/ -v
```
**Expected**: 156+ tests pass, 0 failures.

## Key Patterns

### Flet UI Patterns
- Main app function: `def main(page: ft.Page)` in `src/ui/app.py`
- Tab pages: `def build_<name>_tab(page: ft.Page) -> ft.Control` pattern
- State refresh: after `app_state` mutations, rebuild content + call `page.update()`
- Dialogs: create `ft.AlertDialog`, append to `page.overlay`, set `dlg.open = True`, call `page.update()`
- Async handlers: Flet supports `async def on_click(e)` directly
- Closures in loops use factory functions: `def make_handler(param): def handler(): ... return handler`

### State Management
- `app_state` is a module-level singleton `AppState()` in `src/ui/state.py`
- AppState is framework-agnostic (does NOT import flet)
- All mutations go through AppState methods (add_character, add_location, etc.)
- Each method calls `self.save()` — no callback notification system
- Flet UI layer calls `page.update()` directly after state changes

### Config
- `config.json` at project root stores API settings
- `load_config()` / `save_config()` in `src/services/config.py`

### Running the App
- Desktop mode: `python main.py`
- Web mode: `python main.py --web` (serves on http://localhost:8080)
- Or via env var: `PUZZLE_SOLVER_WEB=1 python main.py`

## Constraints
- Do NOT modify existing test files unless fixing a test that broke due to intentional behavior change
- Keep all UI text in Chinese (中文)
- Preserve existing code patterns and style
- `pyproject.toml` `requires-python = ">=3.13"` — do not change
- AppState must NOT import flet (framework-agnostic for testability)

## Important Implementation Notes

### Pure Logic Functions (tested, must preserve signatures)
- `build_matrix_data(project: Project) -> list[dict]` in `matrix.py` — tested by `test_matrix.py` (11 tests)
- `_create_single_deduction(proj, fact_dict, script_id) -> bool` in `scripts.py` — tested by `test_scripts.py`
- `_create_deductions_from_facts(proj, direct_facts, script_id) -> int` in `scripts.py` — tested by `test_scripts.py`
- `_is_api_configured() -> bool` in `scripts.py` — tested by `test_scripts.py`

### Flet Dialog Pattern
```python
def show_dialog(page, title, content_controls, actions):
    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text(title),
        content=ft.Column(content_controls, tight=True, spacing=10),
        actions=actions,
    )
    page.overlay.append(dlg)
    dlg.open = True
    page.update()
```

### Flet State Refresh Pattern
```python
def refresh():
    container.content = _build_content(page)
    page.update()
```

### Packaging
- Desktop: `python build.py` (uses `flet pack`)
- Web: `python build.py --web` (uses `flet publish`)
- CI/CD: GitHub Actions with `astral-sh/setup-uv@v5`, then `uv sync` + `uv run pytest`
</coding_guidelines>
