# User Testing

## Validation Surface
- **pytest**: All tests run via `cd C:\exp\puzzle-solver && .venv\Scripts\python -m pytest tests/ -v`
- No browser/UI automated testing (Flet desktop apps lack mature automation tooling)
- Manual verification: workers confirm app starts with `python main.py --web`

## Validation Concurrency
- **pytest surface**: max concurrent validators = 5 (lightweight, ~50MB per process, 12GB headroom available)
- Tests are purely data-layer, no UI rendering, very fast (~2s total)

## Flow Validator Guidance: pytest
- Prefer the repo virtualenv Python at `C:\exp\puzzle-solver\.venv\Scripts\python.exe`.
- Keep validators read-only against application source; validation should execute tests and inspect files only.
- Pytest assertions here operate on temporary directories/fixtures, so concurrent runs are acceptable if they do not write to the same report path.
- Write each validator report to a unique file under `.factory/validation/<milestone>/user-testing/flows/`.
