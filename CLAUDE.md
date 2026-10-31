# Ages of the Island — notes for coding agents

Real-time Catan-style game. Design: `docs/GAME_DESIGN.md`. Architecture and work packages (WP0–WP18): `docs/STAGE1_PLAN.md`. Read both before changing code.

## Engine rules (`engine/`)
- Pure Python 3.13. Only allowed third-party import: `pydantic` (v2). No Django, Channels, `random`, `time`, `datetime`, threads or I/O. A test enforces this.
- Deterministic: all randomness comes from `engine.rng.Rng` stored in the game state; all time is integer game milliseconds passed in as `now_ms`.
- **No hard-coded game numbers.** Every cost, count, ratio, time or limit comes from `GameSettings` (`engine/settings`). If you need a new number, add a settings field with a default.
- Errors are `engine.errors.RuleError(code, params)`; codes are dotted i18n keys (e.g. `build.distance_rule`), never sentences. Events carry codes and values, never text.
- No floats in rule decisions (use ints / integer maths; percentages as int percent).
- Keep functions small and typed. Prefer plain dataclasses for state.

## Tests
- Tests live in `engine/tests/` (and `engine/<pkg>/tests/` if you prefer), files named `test_*.py`, written as `unittest.TestCase` classes so they run with both `unittest` and `pytest`.
- Run all engine tests: `python3 -m unittest discover -s engine -t . -p "test_*.py"`
- `pytest`/`hypothesis` are not installed in the dev workspace; use seeded loops for property-style tests.

## Django site
- Settings: `config/settings/{base,dev,test,prod}.py`. Dev uses SQLite and the in-memory channel layer unless `USE_POSTGRES` / `REDIS_URL` are set.
- `config/urls.py`, `config/asgi.py` and `INSTALLED_APPS` already include every app; apps fill in their own `urls.py` / `routing.py`.
- Tests: `DJANGO_SETTINGS_MODULE=config.settings.test python3 manage.py test common accounts lobby gamehost gameplay`.
- User-facing strings use gettext; add Spanish to `locale/es/LC_MESSAGES/django.po` (`.mo` files are not committed; run `compilemessages`).
- Frontend: `frontend/` (Vite + TS); `{% load vite %}{% vite_entry "game" %}` emits the bundle tags.

## Ownership
Each work package owns the files listed for it in `docs/STAGE1_PLAN.md` §9. Do not edit files owned by another package; if you need a change there, say so in your report.
