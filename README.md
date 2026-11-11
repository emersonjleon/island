# Ages of the Island

An online strategy game: Settlers of Catan ideas played in real time, like Age of Empires. A server clock rolls the dice, settlers walk the island to found the first settlements, and everything is customizable. Built with Django.

- Game design: [docs/GAME_DESIGN.md](docs/GAME_DESIGN.md)
- Stage 1 technical plan: [docs/STAGE1_PLAN.md](docs/STAGE1_PLAN.md)

## Status

Stage 1 in progress. The rules engine (`engine/`, pure Python) is complete through simulation and replay. The Django site has its skeleton and accounts (sign-up, login, password reset, profile, English/Spanish, key-binding storage) and a lobby (create a game with a few settings, join, colours, ready, start, live seat updates) and the game host that runs started games; the game WebSocket and the game page come next.

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

Games are run by a separate process, the game host. It talks to the web process through the
channel layer, so it needs Redis (the in-memory layer does not cross processes):

```bash
REDIS_URL=redis://localhost:6379/0 python3 manage.py run_gamehost
```

It starts games the lobby marks `STARTING`, persists commands and snapshots, restores `RUNNING`
games after a restart, and snapshots every game on Ctrl-C / SIGTERM.

### Bots

The host can fill free seats with computer players in the lobby (**Add bot**, level easy, medium
or hard), so a game can start with one person. Bots run inside the game host process: each live
game asks its bots for intents on their own think interval and applies them like a player's
commands, so they are logged, snapshotted and replayed with everything else. The levels are
profiles in `engine/ai/levels.py`:

| Level | Thinks every | Plays |
| --- | --- | --- |
| Easy | 4 s | picks a random spot half the time, rarely trades |
| Medium | 2 s | best-yield spots, cities before settlements, trades for what it lacks |
| Hard | 0.8 s | also values new resources and usable harbors, spends cards before a seven |

In simulated two-bot games hard beats medium about 6 times in 10, and medium beats easy about
9 times in 10 (`engine/tests/test_ai_levels.py`).

The client lives in `frontend/` (TypeScript, Vite):

```bash
cd frontend && npm install
npm run dev     # then start Django with VITE_DEV_SERVER=http://localhost:5173
npm run build   # writes static/dist/ with the manifest Django reads
npm test
```

Django tests: `DJANGO_SETTINGS_MODULE=config.settings.test python3 manage.py test common accounts lobby gamehost gameplay`

## Two-player browser test

`e2e/` plays a whole short game in two browsers against the real web server, game host and
Redis: sign up, create and join in the lobby, place the setup pieces with the keyboard, wait for
a dice roll, then build until someone wins (about 20 seconds). `e2e/bots.cjs` also plays one
person against two bots added in the lobby. Every game it creates uses
`e2e/fast_game.json` (5 points to win, plenty of resources, quick builds) through
`e2e/settings.py`.

```bash
redis-server --daemonize yes                     # or docker compose up -d
(cd frontend && npm ci && npm run build)
(cd e2e && npm ci && npx playwright install chromium)
python3 e2e/run.py                               # screenshots and server logs in e2e/out/
```

CI runs it in the `e2e` job.
