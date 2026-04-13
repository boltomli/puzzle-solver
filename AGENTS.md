# AGENTS.md — Puzzle Solver QoL Mission

## Project Overview
Puzzle Solver is a NiceGUI-based desktop/web application for script-based mystery games (剧本杀).
It uses a Character × Location × Time reasoning matrix with AI-powered deduction.

## Tech Stack
- **Python 3.13** via uv package manager
- **NiceGUI** (Web/desktop UI framework, uses Quasar/Vue under the hood)
- **Pydantic v2** for data models
- **OpenAI SDK** for LLM API calls
- **pywebview** for native desktop window
- **pytest** + **pytest-asyncio** for testing

## Project Structure
```
puzzle-solver/
├── main.py                    # Entry point (create_app)
├── build.py                   # PyInstaller build script (NEW)
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
│       ├── state.py           # AppState singleton
│       ├── theme.py           # Layout, tabs, project selector
│       └── pages/
│           ├── scripts.py     # Script management tab
│           ├── matrix.py      # Reasoning matrix tab
│           ├── manage.py      # Entity management tab
│           ├── review.py      # Deduction review tab
│           └── settings.py    # API settings tab
├── tests/                     # pytest test suite (114 tests)
└── .github/workflows/         # CI/CD (NEW)
```

## Baseline Test Command
```bash
cd C:\exp\puzzle-solver && .venv\Scripts\python -m pytest tests/ -v
```
**Expected**: 114+ tests pass, 0 failures.

## Key Patterns

### NiceGUI UI Patterns
- Pages use `@ui.refreshable` decorators for reactive content
- Dialogs created with `with ui.dialog() as dlg, ui.card():` pattern
- State changes go through `app_state` methods which call `save()` + `_notify()`
- Closures in loops use factory functions: `def make_handler(param): def handler(): ... return handler`

### State Management
- `app_state` is a module-level singleton `AppState()` in `src/ui/state.py`
- All mutations go through AppState methods (add_character, add_location, etc.)
- `_notify()` triggers registered UI refresh callbacks

### Config
- `config.json` at project root stores API settings
- `load_config()` / `save_config()` in `src/services/config.py`

## Constraints
- Do NOT modify existing test files unless fixing a test that broke due to intentional behavior change
- Keep all UI text in Chinese (中文)
- Preserve existing code patterns and style
- `pyproject.toml` `requires-python = ">=3.13"` — do not change
- Always use `reload=False` in `ui.run()` calls (required for PyInstaller)
- When adding NiceGUI components, use Quasar classes (`q-pa-md`, `q-mb-sm`, etc.)

## Important Implementation Notes

### Feature 1 (Auto Script Analysis)
- The existing `_run_script_analysis()` and `_show_analysis_results_dialog()` in scripts.py are the foundation
- For direct_facts → Deductions: create `Deduction` objects with appropriate fields, mapping character_name/location_name back to IDs from the project
- Time slots from analysis: `time_references[].time_slot` values in HH:MM format

### Feature 2 (Settings Optimization)
- NiceGUI combo: use `ui.select(...).props('use-input')` with options list, or `new_value_mode='add'`
- OpenAI SDK `client.models.list()` returns an async iterator; collect into list of model IDs
- Some providers (Ollama) don't need API key — pass `api_key="no-key"` as default

### Feature 3 (UI Optimization)
- Tab badge: NiceGUI tabs support `ui.badge()` inside tab or use `.props()` to add Quasar badge
- API banner: use `ui.banner()` or a styled `ui.card()` at top of tab content

### Feature 4 (PyInstaller + CI/CD)
- build.py pattern: `subprocess.call(["python", "-m", "PyInstaller", ...])` with nicegui path discovery
- GitHub Actions: use `astral-sh/setup-uv@v5` for uv, then `uv sync` + `uv run pytest`
- For release: `uv pip install pyinstaller` then `uv run python build.py`
