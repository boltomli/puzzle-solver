# User Testing

## Validation Surface
- **pytest**: All tests run via `cd D:\exp\puzzle-solver && .venv\Scripts\python -m pytest tests/ -v`
- No browser/UI automated testing (Flet desktop apps lack mature automation tooling)
- Validation is purely through automated tests

## Validation Concurrency
- **pytest surface**: max concurrent validators = 5 (lightweight, ~50MB per process, 12GB headroom available)
- Tests are purely data-layer, no UI rendering, very fast (~3s total)

## Flow Validator Guidance: pytest
- Use the repo virtualenv Python at `D:\exp\puzzle-solver\.venv\Scripts\python.exe`
- Keep validators read-only against application source; validation should execute tests and inspect files only
- Pytest assertions operate on temporary directories/fixtures, so concurrent runs are safe
