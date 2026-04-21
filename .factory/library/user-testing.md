# User Testing

## Validation Surface

**Primary automated surface:** pytest + ruff against repository/state/integration behavior.

**Interactive surface:** Flet app in web mode at `http://localhost:8080` for key manual smoke checks only.

**Key user-visible flows to smoke manually:**
- create a new project
- load an existing SQLite-backed project
- explicitly import a legacy JSON file
- verify imported project appears in normal project list
- edit scripts/entities and reload
- accept/reject deductions and verify matrix/review state remains coherent

**Important mission constraint:** startup must not scan legacy JSON directories automatically; JSON appears only through explicit import.

## Validation Concurrency

This mission is primarily pytest-driven. Interactive validation is light and sequential.

- Automated validator surface (`pytest`): up to 5 concurrent validators is acceptable for this repository size
- Interactive/manual smoke (`flet-web`): 1 at a time

## Testing Notes

- Existing regression tests are the primary compatibility oracle.
- This mission does not add a UI automation framework.
- Performance validation is smoke-threshold based using representative seeded data, not strict benchmarking.
