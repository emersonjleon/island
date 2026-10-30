# Ages of the Island

An online strategy game: Settlers of Catan ideas played in real time, like Age of Empires. A server clock rolls the dice, settlers walk the island to found the first settlements, and everything is customizable. Built with Django.

- Game design: [docs/GAME_DESIGN.md](docs/GAME_DESIGN.md)
- Stage 1 technical plan: [docs/STAGE1_PLAN.md](docs/STAGE1_PLAN.md)

## Status

Stage 1 in progress. The rules engine (`engine/`, pure Python) is complete through simulation and replay. The Django site has its skeleton and accounts (sign-up, login, password reset, profile, English/Spanish, key-binding storage); the lobby, game host and game page come next.

## Running the engine tests

```bash
python3 -m pip install "pydantic~=2.12"
python3 -m unittest discover -s engine -t . -p "test_*.py"
```

## Simulations and protocol contract

`engine/sim/` has headless bots (`RandomBot`, `GreedyBot`), a manual-clock runner that records the
command log, replay/resume helpers and state invariants. The suite in `engine/tests/simulation/`
plays full games, replays them from the log and from mid-game snapshots, and checks redaction.

`protocol/` (codes, JSON Schemas, golden fixtures for the TypeScript client) is generated:

```bash
python3 scripts/export_protocol.py          # regenerate
python3 scripts/export_protocol.py --check  # what the tests verify
```

## Running the site locally

```bash
python3 -m pip install -e .
python3 manage.py migrate          # SQLite by default (config/settings/dev.py)
python3 manage.py compilemessages  # needs gettext; Spanish catalogue in locale/es
python3 manage.py runserver        # ASGI through Daphne
```

Postgres and Redis (what production uses): `docker compose up -d`, then run with
`USE_POSTGRES=1 REDIS_URL=redis://localhost:6379/0`.

The client lives in `frontend/` (TypeScript, Vite):

```bash
cd frontend && npm install
npm run dev     # then start Django with VITE_DEV_SERVER=http://localhost:5173
npm run build   # writes static/dist/ with the manifest Django reads
npm test
```

Django tests: `DJANGO_SETTINGS_MODULE=config.settings.test python3 manage.py test common accounts lobby gamehost gameplay`
