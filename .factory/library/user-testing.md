# User Testing

## Validation Surface

**Primary surface:** Flet web app at http://localhost:8080

**How to access:** Start with `.venv\Scripts\python main.py --web` — serves Flet web UI on port 8080. Auto-opens browser window.

**Test data:** Two project JSON files in `data/` directory:
- Small project (3.7 KB)
- Large project "red pearls" (39.9 KB, 890 lines) with characters, locations, time_slots, scripts, deductions

**Key pages to verify:**
- Project list / selector (app.py)
- Matrix view — character × time grid (matrix.py)
- Entity management — add/remove characters, locations, time slots (manage.py)
- Script management — add scripts, view analysis (scripts.py)
- Review — deduction history (review.py)

**Tools:** agent-browser for web mode verification, curl for health checks.

## Validation Concurrency

**Machine specs:** 16GB RAM, 8 cores/16 threads, ~3.8GB free
**Flet server footprint:** ~130MB (server + browser)
**agent-browser footprint:** ~300MB per instance
**Total per validator:** ~430MB

**Max concurrent validators:** 5 (5 × 430MB = 2.15GB, well within 3.8GB × 0.7 = 2.66GB budget)

## Testing Notes

- This is a refactoring mission — primary validation is behavioral compatibility
- All 212+ existing pytest tests serve as regression suite
- User testing confirms the app still renders and functions correctly
- No new UI features to test — just verify existing functionality preserved
