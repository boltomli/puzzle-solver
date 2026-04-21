# Environment

**What belongs here:** Required env vars, external API keys/services, dependency quirks, platform-specific notes.
**What does NOT belong here:** Service ports/commands (use `.factory/services.yaml`).

---

## Python Environment
- Python 3.13 (see `.python-version`)
- Virtual env at `.venv/` (Windows: `.venv\Scripts\python`)
- Package manager: uv (`uv sync` to install)
- No external services required (standalone desktop app)

## Platform Notes
- Primary dev environment: Windows 10/11
- Flet supports both desktop and web mode
- Web mode: `python main.py --web` serves on port 8080
- Desktop mode: `python main.py` opens native window

## API Configuration
- `config.json` at project root stores OpenAI-compatible API settings
- API key required only for AI deduction features (not for core data management)

## Storage Migration Notes
- Active mission storage backend target: local SQLite file(s)
- No external database or cache services are allowed for this mission
- Legacy JSON project files are imported only through explicit user action
- Default startup path must not scan legacy JSON project directories
