# Ages of the Island: Stage 1 implementation plan

I read all of `/home/claude/GAME_DESIGN.md`. There is no repo yet, so every path below is relative to a new repo root. The sandbox had no access to PyPI or npm, so I could not check current versions. The versions below come from my own knowledge (cutoff mid-2026). The bootstrap package (WP0) should pin them in lockfiles (`uv.lock`, `package-lock.json`).

The plan rests on five choices:
- **Separate rules engine.** A pure-Python engine with no Django imports. Its time is discrete and event-driven (integer game milliseconds), and it is deterministic given a seed and the list of commands.
- **Separate game host process.** One `gamehost` process owns live games, one asyncio task per game. The Channels consumers only check and forward player intentions.
- **Postgres for durable data, Redis for messaging.** Postgres holds accounts, games, snapshots and the command log. Redis holds the channel layer and process leases. Live state lives only in game host memory.
- **One source of rules.** The client never re-implements rules. The server sends events that carry their resulting values, plus each player's list of currently legal build spots.
- **Shared client state.** The client state store and board geometry are independent of rendering. The PixiJS 2D renderer and a later three.js renderer both implement the same `Renderer` interface.

---

## 1. Tech stack (pin at bootstrap)

| Layer | Choice | Version to pin | Why |
|---|---|---|---|
| Language | Python | 3.13.x (installed locally: 3.13.16) | Current stable. Good asyncio performance. |
| Web framework | Django | 5.2 LTS (`~=5.2`) | LTS support until April 2028. Auth, i18n and admin are built in. Django 6.0 also works if Channels supports it at bootstrap. |
| Real time | Channels + channels-redis | `channels~=4.3`, `channels-redis~=4.3` | Required by the brief and the right fit anyway: Django session auth on WebSockets, groups for fan-out, and an in-memory layer for tests. I see no reason to choose something else. |
| ASGI server | Daphne | `daphne~=4.2` | Gives `runserver` ASGI support in development. Can be swapped for `uvicorn[standard]` in production without code changes. |
| Validation and schemas | Pydantic v2 | `pydantic~=2.12` (2.13.5 installed locally) | Settings, commands and events are typed models. They export JSON Schema, which drives TypeScript type generation and later an auto-generated settings form. Pure Python, so the engine stays free of Django. |
| Database | PostgreSQL + psycopg 3 | PG 16 (installed locally), `psycopg[binary]~=3.2` | JSONB for settings, snapshots and the command log. |
| Cache and messaging | Redis | 7.x (7.0.15 installed locally), `redis~=5.2` or newer | Channel layer, game host leases, presence. |
| Python tooling | uv, ruff, mypy (strict on `engine/`), pytest, pytest-django, pytest-asyncio, hypothesis | latest at bootstrap | Fast lockfile; property tests for board and rule invariants. |
| Frontend language | TypeScript + Vite | TS 5.x, Vite 7.x, Node 22 LTS (installed locally: 22.22) | Fast development server. Builds into Django static files through a `manifest.json`. |
| 2D rendering | PixiJS | 8.x | WebGL/WebGPU batching, a scene graph, hit areas, smooth pan and zoom, and text, all of which plain Canvas would need hand-written. It keeps large boards smooth. "Faster 2D" means fewer GPU needs than 3D, not raw Canvas. |
| HUD | Preact + @preact/signals | 10.x / 2.x | About 4 kB. Reactive panels (hand, countdown ring, log, build menu) without a heavy framework. |
| Client i18n | i18next | 25.x | JSON catalogues, plurals and interpolation; namespaces avoid merge conflicts. |
| Client tests | Vitest + Playwright | Vitest 3.x, Playwright 1.5x | Unit tests for reducers and input; one end-to-end smoke test with two browsers. |
| Type generation | json-schema-to-typescript | 15.x | Generates TS types from the Pydantic protocol schemas. CI fails if the generated output differs. |
| Stage 4 | three | latest r1xx | Not installed in stage 1. |

Login uses Django's built-in auth views plus a simple sign-up view. django-allauth can be added later for social login.

---

## 2. Repository layout

```
ages-of-the-island/
├── pyproject.toml / uv.lock / manage.py / docker-compose.yml (postgres, redis)
├── Procfile (web: daphne, gamehost: manage.py run_gamehost)
├── config/                       # Django project
│   ├── settings/{base,dev,test,prod}.py
│   ├── urls.py                   # includes every app's urls (created up front with stubs)
│   └── asgi.py                   # ProtocolTypeRouter: http + websocket (lobby.routing, gameplay.routing)
├── engine/                       # PURE PYTHON. No Django/Channels imports (enforced by a test)
│   ├── settings/                 # Pydantic GameSettings, groups, validation, presets/*.json, migrations, share-code codec
│   ├── board/
│   │   ├── coords.py             # axial hex coords, canonical vertex/edge keys, adjacency maths
│   │   ├── topology.py           # Board: dense int ids for hexes/vertices/edges plus adjacency tables
│   │   ├── generator.py          # shape, terrain, tokens (6/8 rule), fishing grounds, harbors, robber start
│   │   └── walkgraph.py          # land walking graph and Dijkstra/A* pathfinding
│   ├── state.py                  # GameState dataclasses (players, hands, bank, buildings, settlers, constructions, robber, clock, rng, timers)
│   ├── rng.py                    # serialisable PCG32/splitmix (state = one int) -> deterministic replays
│   ├── scheduler.py              # timer heap stored in the state: (due_ms, seq, kind, payload)
│   ├── commands.py               # Pydantic intent models (move_settler, build, cancel_build, bank_trade, ...)
│   ├── events.py                 # Pydantic event models (dice_rolled, settler_step, construction_*, produced, ...)
│   ├── errors.py                 # RuleError(code, params). Codes are i18n keys, never prose
│   ├── game.py                   # orchestrator: new_game / apply / advance / next_wakeup; handler registry
│   ├── rules/
│   │   ├── setup.py              # per-player setup phase, landing points, starting materials and resources
│   │   ├── movement.py           # settler paths, per-edge stepping, interrupts
│   │   ├── placement.py          # legality: distance rule, connectivity, pieces; buildable sets
│   │   ├── construction.py       # timed builds, escrow, cancel/refund, first-to-finish conflicts, builder policy
│   │   ├── dice.py               # dice source (two dice; deck later), roll timer
│   │   ├── production.py         # production, bank shortage rule, fishing grounds
│   │   ├── robber.py             # 7 handling, random steal %, random neighbour move (knight hook later)
│   │   ├── trade.py              # bank 4:1, harbor ratios
│   │   └── victory.py            # points, target, game over (longest road/army hooks later)
│   ├── views.py                  # project_state(state, viewer), filter_events(events, viewer, state): hidden hands, fog later
│   ├── codec.py                  # dump/load GameState <-> JSON-able dict; state_hash()
│   └── sim/                      # headless bots + simulation runner for tests
├── accounts/                     # custom User (AbstractUser), sign-up, profile: language, key bindings, UI prefs
├── lobby/                        # Game + GamePlayer records, lobby views/templates, LobbyConsumer (live seat updates), start flow
├── gamehost/                     # runtime: GameRunner per game, clocks, leases, persistence, fan-out; run_gamehost command;
│                                 # models GameSnapshot, GameCommand
├── gameplay/                     # GameConsumer (WebSocket), routing, /play/<id>/ page view serving the client bundle
├── templates/ static/ locale/{en,es}/LC_MESSAGES/django.po
├── protocol/                     # exported JSON Schemas + golden message fixtures shared by Python and TS tests
└── frontend/
    ├── package.json / vite.config.ts / tsconfig.json
    └── src/
        ├── entries/{game.ts, lobby.ts}
        ├── protocol/             # generated TS types (do not edit), message guards
        ├── net/                  # WebSocket client, reconnect, intent ids, clock sync
        ├── state/                # GameStore: board topology, mirrored state, event reducers, selectors
        ├── board/                # geometry: world coordinates of hexes/vertices/edges (renderer-agnostic)
        ├── sim/                  # client-time interpolation (settler positions, progress bars, countdown)
        ├── render/               # Renderer interface + picking types
        ├── render2d/             # PixiJS implementation
        ├── input/                # action map, rebindable bindings, keyboard/mouse/box select, build mode
        ├── ui/                   # Preact HUD: hand, countdown ring, build menu, bank trade, log, scores, notices, key settings
        ├── i18n/                 # i18next init, language detection from <html lang>
        └── locales/{en,es}/{common,hud,input,board,errors,events}.json
```

Each app has one purpose:
- `accounts`: identity and preferences.
- `lobby`: game records before and after play, and the lobby page.
- `gamehost`: live simulation and its durability.
- `gameplay`: the WebSocket edge and the game page.
- `engine`: all rules.

`config/urls.py`, `config/asgi.py`, `INSTALLED_APPS` and stub `urls.py`/`routing.py` files are all created in WP0. Later packages therefore never edit the shared config files.

---

## 3. Data model: what lives where, and when it is persisted

**Django models (Postgres)**

| Model (app) | Fields (main) | Written when |
|---|---|---|
| `accounts.User(AbstractUser)` | display_name, preferred_language, keybindings (JSON), ui_prefs (JSON: renderer 2d/3d, palette) | Sign-up and profile edits |
| `lobby.Game` | public code (short slug), host FK, status (`LOBBY`, `STARTING`, `RUNNING`, `FINISHED`, `ABORTED`), preset name, settings (JSONB), settings_schema_version, seed, created/started/finished, engine_version | Lobby actions; status set by the game host at start and end |
| `lobby.GamePlayer` | game, user, seat (0..n-1), colour, ready, joined_at, final_points, is_winner | Joining, ready, results at game end |
| `gamehost.GameSnapshot` | game, event_seq, cmd_seq, game_ms, state (JSONB, from `engine.codec.dump`), state_hash, created_at | Game start, every dice roll (configurable), game end, graceful shutdown. Keep the last K plus the final one |
| `gamehost.GameCommand` | game, cmd_seq, game_ms, seat, payload (JSONB) | Append-only. Buffered in memory and flushed every ~1 s and before each snapshot |
| `lobby.SettingsPreset` (stage 3) | owner (nullable = built-in), name, settings, version | Not in stage 1 |

**In memory (game host process)**: the live `GameState` of each running game, its scheduler heap, the outgoing event sequence numbers and the unflushed command buffer.

**Redis**: the channel layer, plus three kinds of keys:
- `gamehost:lease:<game_id>`: which game host owns the game, with a TTL of about 10 s, refreshed every 3 s.
- `presence:<game_id>`: which seats are connected, with a TTL.
- `gamehost:route:<game_id>`: the channel name of the owning host. Stage 1 can use one fixed name, `gamehost`.

**Recovering after a crash or restart.** On startup, `run_gamehost` finds `RUNNING` games whose lease has expired and takes the lease. It then loads the latest snapshot and replays the `GameCommand` rows with `cmd_seq` greater than the snapshot's (deterministic: commands carry their game time and the RNG is part of the state). The game clock resumes at the last `game_ms`, so downtime counts as a pause and nobody loses dice rolls to the outage. Finally it broadcasts `state` with `resumed: true`.

At most about 1 s of unflushed commands can be lost. A stricter option is to append commands to a Redis Stream synchronously.

On SIGTERM the host flushes, snapshots every game and releases its leases.

---

## 4. Game engine design

### 4.1 Engine API (pure, synchronous, unit-testable)

```python
new_game(settings: GameSettings, seats: list[SeatInfo], seed: int) -> tuple[GameState, list[Event]]
apply(state, seat: int, cmd: Command, now_ms: int) -> list[Event]   # raises RuleError(code, params); no partial mutation
advance(state, now_ms: int) -> list[Event]                          # fires all due timers in (due_ms, seq) order
next_wakeup(state) -> int | None                                    # earliest timer due_ms
views.project_state(state, viewer) -> dict                          # per-seat or spectator snapshot
views.filter_events(events, viewer, state) -> list[dict]            # redaction (hand types, fog later)
codec.dump(state) / codec.load(dict) / codec.state_hash(state)
```

Engine rules:
- **No clock of its own.** Time is always passed in as `now_ms`, in integer game milliseconds.
- **No I/O, no global randomness.** All randomness comes from `state.rng`.
- **Check first, then change.** `apply` validates everything before it mutates anything.
- **Timers fire at their scheduled time, not when the loop wakes up.** If the host wakes 7 ms late, the dice still roll at exactly `t=20000`, so the schedule never drifts.
- **Handler registry.** `game.py` registers command handlers (`"build"` → `construction.start_build`) and timer handlers (`"dice"`, `"settler_arrive"`, `"construction_done"`). Rule modules own their handlers, which lets WP5, WP6 and WP7 work in parallel.

**Timer kinds in stage 1:** `dice_roll`, `settler_arrive` (end of one edge), `construction_done`. Later stages add `devcard_unlock`, `trade_offer_expire`, `pause_end` and `time_limit`, all through the same scheduler with no new loop.

**The "construction" entity.** It unifies setup builds, network builds (Classic) and settler builds (Settlers variation):
- Fields: `{id, seat, kind, target(vertex|edge), builder(settler_id|None), paid(escrow), piece_reserved, started_ms, done_ms}`.
- A policy decides whether a builder is required: `builder_policy(state, seat, kind) -> "settler"|"none"`. Classic requires a settler only during that player's setup; the Settlers variation always requires one.
- **First to finish wins.** When a `construction_done` timer fires, placement is checked again. On success the engine cancels and refunds every conflicting in-progress construction: the same vertex or a neighbouring vertex for settlements, the same edge for roads. Ties at the same millisecond are broken by the timer sequence number (earlier start wins), which is deterministic.
- Moving the builder settler away cancels the build with a full refund. The refund percentage is a setting.
- Pieces are reserved when a build starts and returned on cancel. Resources are held in escrow, so the conservation invariant is: bank + hands + escrow = constant.

**Setup phase is tracked per player.** Each player has `setup.remaining = {settlement: 2, road: 2}`. During setup:
- Settlements follow only the distance rule.
- A road must touch that player's newly built settlement (a setting).
- Each completed setup settlement grants 1 card per neighbouring producing hex, including fishing grounds (a setting).

When `remaining` reaches zero, Classic removes the settler (`settler_left`) and switches the player to network building. The first completed settlement by anyone schedules the first `dice_roll` at `t + roll_interval`. After that, every roll schedules the next one, and nothing ever waits.

### 4.2 Game loop (one asyncio task per game, inside the `gamehost` process)

```
async def run(game):
    while not state.finished:
        wake = engine.next_wakeup(state)
        timeout = clamp(wake - clock.now(), 0, MAX_IDLE)  (or None)
        cmd = await inbox.get() with timeout              # asyncio.Queue fed by the channel-layer receiver
        now = clock.now()                                 # monotonic -> game_ms (pausable offset)
        events = engine.advance(state, now)               # timers due before the command first
        if cmd: events += engine.apply(...)  or reject → send reject to cmd.reply_channel
               log command (cmd_seq, now, seat, payload) to buffer; ack
        stamp events with seq; fan-out per audience; maybe snapshot
```

- **Why a separate process rather than the ASGI workers:**
  - A game needs exactly one owner. With several ASGI workers, an in-process loop needs sticky routing anyway.
  - Simulation load stays apart from socket load.
  - Restarting web workers does not disturb games.
  - It scales by sharding: `gamehost.<n>`, with the shard chosen by the lease or route key.
- **Size estimate.** A game produces a few events per second, so one asyncio process should handle hundreds of games. CPU-heavy work (pathfinding on large boards) stays in milliseconds.
- **Timing.** `clock.now()` uses `time.monotonic_ns()` plus an offset per game, which allows pausing. asyncio sleep jitter (about 1–5 ms) is harmless because timers fire at their logical time. Tests swap in `ManualClock`.
- **Start flow.** The lobby sets status `STARTING` and sends `{"type":"game.start","game_id"}` to `gamehost`. The host also scans for `STARTING` games every 5 s in case the message was lost. The host builds the state, snapshots it, sets status `RUNNING` and tells the lobby group to redirect players to `/play/<code>/`.
- **Messages from consumer to host** (over the channel layer): `game.intent` (with `reply_channel`, seat and payload), `game.sync` (asks for the projected state plus the topology for that seat), `game.presence`.
- **Fan-out from host to clients.** Each event batch is sent to one group per audience: `g.<id>.seat.<n>` for each seat and `g.<id>.spect` for spectators. Each audience gets its own `views.filter_events(...)` output. In stage 1 the batches differ only in redacted hands, but this is the hook that fog of war plugs into later.
- **Sequence numbers.** Each seat's stream has its own `seq`. A client that sees a gap sends `sync`. This is also how stage 2 reconnection works, and it nearly comes for free, so a page refresh should already work in stage 1.

### 4.3 Protocol (JSON over WebSocket, `proto: 1`)

**Client to server** (`cid` is an intent id generated by the client and echoed in `ack`/`reject`):

```json
{"t":"hello","proto":1,"lang":"es"}
{"t":"sync","from_seq":1532}
{"t":"ping","c":1729.55}
{"t":"intent","cid":"a17","a":"move_settler","settler":3,"to_vertex":41,"mode":"replace"}
{"t":"intent","cid":"a18","a":"move_settler","settler":3,"to_vertex":42,"mode":"append"}
{"t":"intent","cid":"a19","a":"build","kind":"settlement","vertex":41,"settler":3}
{"t":"intent","cid":"a20","a":"build","kind":"road","edge":88}
{"t":"intent","cid":"a21","a":"build","kind":"city","vertex":17}
{"t":"intent","cid":"a22","a":"cancel_build","construction":12}
{"t":"intent","cid":"a23","a":"bank_trade","give":{"lumber":4},"get":{"ore":1}}
```

Later stages add `buy_dev_card`, `play_dev_card`, `post_offer`, `accept_offer`, `buy_settler` and `vote_pause` to the same envelope.

**Server to client:**

```json
{"t":"welcome","game":"K7QX2","seat":2,"proto":1,"now":53210,"settings":{...}}
{"t":"board","hexes":[{"id":0,"q":0,"r":0,"terrain":"fields","token":8}, ...],
 "vertices":[{"id":0,"q":0,"r":0,"c":"N","hexes":[0,5,6],"adj_v":[..],"adj_e":[..]}, ...],
 "edges":[{"id":0,"v":[0,1],"hexes":[0,5]}, ...],
 "fishing":[{"hex":31,"token":5}], "harbors":[{"edge":64,"type":"generic","ratio":3}]}
{"t":"state","seq":1532,"now":53210,"state":{ "phase":"running","next_roll_at":60000,"bank":{...},
   "players":[{"seat":2,"hand":{"lumber":2,"brick":1,...},"pieces":{...},"points":2,"setup":{...}},
              {"seat":0,"hand_count":5,"points":3}],
   "buildings":[...],"settlers":[...],"constructions":[...],"robber":9,"buildable":{"roads":[..],"settlements":[..],"cities":[..]}}}
{"t":"events","seq":1533,"now":60004,"events":[
  {"k":"dice_rolled","at":60000,"dice":[3,4],"sum":7,"next_roll_at":80000},
  {"k":"robber_stole","at":60000,"seat":2,"lost":{"wool":2,"ore":1},"hand_after":{...}},
  {"k":"robber_stole","at":60000,"seat":0,"lost_count":4,"hand_count_after":4},
  {"k":"robber_moved","at":60000,"from":9,"to":4},
  {"k":"produced","at":80000,"roll":8,"gains":{"2":{"grain":2}},"skipped":{"ore":"bank_shortage"}},
  {"k":"hand","seat":2,"hand":{...}},
  {"k":"settler_step","at":53990,"settler":3,"from":40,"to":41,"t0":53990,"t1":55490},
  {"k":"settler_path","settler":3,"path":[40,41,42]},
  {"k":"construction_started","id":12,"seat":2,"kind":"settlement","vertex":41,"t0":55500,"t1":63500,"paid":{...}},
  {"k":"construction_cancelled","id":11,"seat":1,"reason":"conflict","refund":{...}},
  {"k":"built","seat":2,"kind":"settlement","vertex":41,"points_after":3},
  {"k":"settler_left","settler":3},
  {"k":"buildable","roads":[..],"settlements":[..],"cities":[..]},
  {"k":"game_over","at":912000,"winner":2,"points":{"0":7,"1":5,"2":10}}]}
{"t":"ack","cid":"a19"}
{"t":"reject","cid":"a19","code":"build.distance_rule","params":{"vertex":41}}
{"t":"notice","code":"game.resumed","params":{}}
{"t":"pong","c":1729.55,"now":53995}
```

The `robber_stole` example shows the same fact as seat 2 (owner) and seat 0 (others) receive it. `buildable` is private to its seat.

Three principles for events:
1. **Events carry resulting values** (`hand_after`, `points_after`). Client reducers are just assignments and never apply rules.
2. **Settlers move one edge per event**, with exact `t0`/`t1`. Clients interpolate, and fog can later drop steps outside a player's sight.
3. **Text is never sent.** Messages carry codes and parameters, and the client translates them.

The engine computes each seat's `buildable` set and sends it privately whenever it changes. This lets the client highlight legal spots without copying the placement rules.

**Clock sync.** The client sends `ping` about every 5 s and keeps the sample with the lowest round-trip time to estimate the offset. All countdowns and animations use the estimated server game time.

**Edge checks in the consumer.** It authenticates through Django sessions (`AuthMiddlewareStack`) and maps the user to a seat; spectators may only send `sync`. It checks message size and shape against the Pydantic command models, rate-limits (for example 20 intents/s per connection) and forwards the intent. Gameplay validation happens only in the engine.

---

## 5. Settings schema outline (`engine/settings`)

The settings are one Pydantic model, `GameSettings`, with nested groups:
- Every field has a default, `ge`/`le` bounds and `json_schema_extra={"label": "settings.dice.roll_interval", "stage": 1}`.
- `schema_version: int`, with a migration chain `migrations.py: {1: v1_to_v2, ...}` that runs before validation.
- Presets are JSON files holding only the differences from the defaults; `classic.json` is effectively empty.
- Validation at game start includes checks across fields: terrain total = land hexes, tokens = producing hexes, red tokens placeable, player count within the board's limits.
- **Fields from later stages are not silently ignored.** A validator rejects any non-default value for a field whose `stage` is greater than the server's `IMPLEMENTED_STAGE`.
- Share code (stage 3) = `base64url(zlib(canonical_json(diff_vs_preset)))` + preset id + version.

```
GameSettings
  schema_version: 1          preset: "classic"
  players:   min 2, max 4, seat_order: random|host
  board:
    land_hexes: 19 (7..250)     shape: spiral (stage 1) | hexagon | custom (later)
    layout: random | beginner (stage 3) | seeded        seed: int|null
    terrain_counts: {forest 4, pasture 4, fields 4, hills 3, mountains 3, desert 1} | "auto-scale"
    terrain_resource: {forest: lumber, pasture: wool, fields: grain, hills: brick, mountains: ore}
    number_tokens: {2:1,3:2,4:2,5:2,6:2,8:2,9:2,10:2,11:2,12:1} | "auto-scale"
    red_numbers: [6,8]   red_may_touch: false   red_rule_includes_fishing: true
    fishing_grounds: {count 6, tokens [4,5,6,8,9,10], min_gap 1}
    harbors: {generic 4, specific {lumber 1, wool 1, grain 1, brick 1, ore 1, fish 0}, generic_ratio 3, specific_ratio 2}
    robber_start: desert | random_land
  clock:
    roll_interval_ms 20000 (5000..120000)  dice_mode: two_dice | deck (stage 3)
    start_trigger: first_settlement   pause_after_seven_ms 0   allow_vote_pause false (stage 3)
    setup_pick_timer_ms (snake mode, stage 3)
  economy:
    costs: road{brick 1,lumber 1}, settlement{brick,lumber,wool,grain 1}, city{grain 2, ore 3},
           dev_card{wool,grain,ore 1}, settler{grain 5, wool 5, lumber 3, fish 2}
    production_per: {settlement 1, city 2}
    starting_materials: {brick 4, lumber 4, wool 2, grain 2}   starting_materials_from_bank: true
    starting_resources: {granting_settlements 2, cards_per_hex 1, include_fishing true}
    bank: {per_resource 19 (or map)}   shortage_rule: classic
    trade: {bank_ratio 4}
  pieces:    {roads 15, settlements 5, cities 4}
  build:     {time_ms: {road 3000, settlement 8000, city 10000}, network_builds_timed: true, refund_pct 100,
              conflict: first_to_finish}
  setup:     {mode: settlers | snake_click | random (stage 3), settlements 2, roads 2, road_touches_new_settlement true}
  robber:    {enabled true, card_limit 7, steal_pct 50, rounding floor,
              require_over_limit true, require_adjacent false,
              move_on_seven: random_neighbour | player (stage 3), may_enter_fishing false,
              knight_max_distance 3, knight_steal 1, friendly_min_points 0}
  settlers:  {start_count 1, max 4, landing: even_coast, ms_per_edge 1500 (default to confirm), road_speed_mult 2.0,
              build_reach_edges 0, leave_after_setup true, builder_required: setup_only | always, spawn_at: own_building}
  visibility:{map: open | growing | explored | live_fog, sight {road 1, settlement 1, city 2, settler 1},
              hidden_numbers false, hands: counts | open | hidden, dev_cards: counts | open | hidden,
              scores: shown | hidden_until_end, production_log: all | own, trade_offers: public | private_allowed}
  victory:   {target 10 (5..20), longest_road {min 5, points 2}, largest_army {min 3, points 2}, time_limit_ms null}
  trading:   {player_trades true, offer_expiry_ms null, private_offers false}
  dev_cards: {deck {knight 14, victory_point 5, road_building 2, year_of_plenty 2, monopoly 2},
              cooldown: per_roll | ms, cooldown_ms null, road_building_roads 2, year_of_plenty_cards 2}
```

Server operational values (snapshot frequency, rate limits, lease TTL) are Django settings, not game settings. The six resources are an engine enum; costs, counts and mappings are all data.

---

## 6. Board, coordinates, generator and pathfinding

**Coordinates.** Hexes are pointy-top (the familiar Catan rows) in axial coordinates `(q, r)`. The six neighbours are E(+1,0), W(−1,0), NE(+1,−1), NW(0,−1), SE(0,+1) and SW(−1,+1).

- **Vertices** are canonically `(q, r, N|S)`, the top or bottom corner of a hex. Every other corner maps onto one of these:
  - NE(q,r) = S(q+1, r−1)
  - NW(q,r) = S(q, r−1)
  - SE(q,r) = N(q, r+1)
  - SW(q,r) = N(q−1, r+1)
- **Edges** are canonically `(q, r, NE|E|SE)`, and the opposite directions map onto these:
  - SW(q,r) = NE(q−1, r+1)
  - W(q,r) = E(q−1, r)
  - NW(q,r) = SE(q, r−1)
- `coords.py` provides `canon_vertex`, `canon_edge`, `vertex_hexes`, `vertex_neighbors`, `edge_vertices`, `edge_hexes`, `hex_distance` and `hex_ring`/`spiral`.
- **Wire ids.** `topology.Board` sorts the canonical keys and assigns dense integer ids, then precomputes adjacency arrays. The protocol uses the integer ids. The `board` message includes the coordinates, so any renderer can lay the board out without extra calculation.
- **World geometry** (client, shared by 2D and 3D): hex size 1, `x = √3·(q + r/2)`, `y = 1.5·r`. The 3D view maps `(x, y)` to `(x, 0, y)`.

**Generator** (`generator.py`, deterministic from `seed` and settings):
1. **Land.** Take the first N hexes of a spiral from the origin. The result is always connected and roughly round, and N=19 gives exactly the standard board. A random-blob or custom shape can be added in stage 3 behind the same `shape` setting.
2. **Sea.** All non-land hexes within distance 1 of land (2 if harbors or fishing need room).
3. **Terrain.** If set to `auto-scale`, scale the default counts to N by largest remainder. Then shuffle.
4. **Number tokens.** Place the red tokens first on non-desert hexes, using a random greedy choice that rejects adjacent red hexes, with up to K restarts. If that fails, raise `BoardGenerationError`; game-start validation calls it, so a bad configuration is caught in the lobby. Then shuffle the remaining tokens onto the remaining hexes.
5. **Fishing grounds.** Pick sea hexes adjacent to land, evenly spaced around the coastline with a minimum gap and a random offset. Assign the fishing tokens, applying the red rule across land and fish if that setting is on.
6. **Harbors.** Walk the coastline cycle of coastal edges (land on one side, sea on the other). Pick evenly spaced edges that share no vertex and avoid fishing-ground hexes where possible. Assign types by shuffle. The two vertices of the edge are the harbor's vertices.
7. **Robber** starts on the desert (a random one if there are several; none if there is no desert).

Invariant tests with hypothesis cover sizes 7..250 and many seeds: land connected, counts exact, red rule holds, harbors not adjacent, fishing grounds on sea next to land.

**Walking graph and pathfinding** (`walkgraph.py`):
- **Nodes** are vertices touching at least one land hex. **Edges** are hex edges with at least one adjacent land hex, so coastal edges are walkable and sea is impassable. A ships expansion later only changes this predicate.
- **Cost** of an edge = `ms_per_edge / (road_speed_mult if own road on edge else 1)`.
- **Search.** A* with heuristic `euclid(v, goal) / edge_length × ms_per_edge / road_speed_mult`. The graph has under 2k nodes even on large boards, so this is trivially fast.
- **Committed path, per-edge timing.** The path is fixed when the command arrives. Each edge's time is calculated when the settler enters it, so a road finished mid-walk speeds up the next edges.
- **Interrupts.** A new `replace` move while mid-edge finishes the current edge, then re-paths from its end vertex. Reversing mid-edge is a later refinement; the state stores `(edge, t0, t1)` so it is possible.
- **Keyboard movement.** The client picks the neighbouring vertex whose screen direction best matches the pressed key (within 90°) and sends `append`. While the key is held, the client queues the next step as each step starts, so walking is continuous without the server tracking key state. This also works with a rotated 3D camera because the direction is computed on the client.
- **Landing points.** Order the coastal walkable vertices around the coastline cycle, then choose N evenly spaced points with a random offset.
- **Reuse later.** Fog sight uses the same graph and hex distances. The Settlers variation and extra settlers reuse movement unchanged. Longest Road (stage 2) is a DFS over each player's road edges, broken by opponents' buildings.

---

## 7. Frontend architecture (2D) and i18n

**Data flow:** `net` → `state.GameStore` → `sim` → `render` and `ui`; `input` → `net` intents.

- **`net/`.** A WebSocket client with exponential reconnect. On reconnect it sends `sync` with the last seq. It keeps a table of pending intents by `cid` (for optimistic hints and reject notices) and handles clock sync.
- **`state/`.** `GameStore` holds the board topology (static) and the mirrored state. It applies event reducers, which only assign fields; there is no rule logic in the client. It exposes signals or selectors. It has no DOM, Pixi or three imports, so the 3D renderer can reuse it unchanged.
- **`board/geometry.ts`.** World positions of hexes, vertices and edges, plus neighbour-direction helpers for keyboard moves.
- **`sim/`.** Given the estimated server time: settler world position (interpolating `settler_step` t0→t1), construction progress, the countdown to `next_roll_at`.
- **`render/Renderer`** is the interface every renderer implements:

```ts
mount(el: HTMLElement): void
update(store: GameStore, sim: SimView, dt: number): void
pick(screenX: number, screenY: number): PickResult
camera: { pan; zoom; centerOn(worldPt) }
setOverlays(opts)
destroy(): void
```

  `PickResult` is one of `{kind: "vertex" | "edge" | "hex" | "settler", id}`.
- **`render2d/` (PixiJS).** Layers for terrain, tokens, fishing grounds and harbors, roads, buildings, construction progress bars, settlers, highlights (`buildable` spots, path preview) and selection. The world container transform is the camera. Picking uses a geometric nearest-vertex/edge search in world coordinates (renderer-independent, shared with 3D through `board/`), plus Pixi hit areas for settlers.
- **`input/`.** An `ActionMap` connects bindings to abstract actions:
  - `move_dir`, `select_next`, `select_index(n)`
  - `build_mode(road|settlement|city)`, `confirm`, `cancel`
  - `buy_dev_card` (disabled in stage 1), `open_trade`
  - `camera_pan` (Shift+WASD, middle-drag, screen edge), `zoom` (+/− and wheel), `center_selected` (Space, double-click portrait)
  - right-click a vertex/edge → move, or build menu; left-click/box select

  Bindings are a JSON map, defaulting to the design's Controls table. They are stored in `localStorage` and synced to `User.keybindings`, and the HUD has a rebind screen. Pointer Events are used throughout so touch (tap and long-press) can be added later.
  - **Build mode:** highlight the `buildable` spots for that kind (within the builder's reach during setup). Tab or arrows cycle candidates nearest the selected settler or cursor; Enter confirms.
- **`ui/` (Preact).** Hand panel (with bank trade dialog), countdown ring, dice history, event log, scoreboard, build progress, notices (translated reject codes), game-over screen, language switcher and key-binding editor. The HUD is DOM over the canvas, so it is reusable unchanged with three.js.

**i18n:**
- **Server pages** (accounts, lobby): Django gettext. Settings: `LANGUAGES=[("en","English"),("es","Español")]`, `LocaleMiddleware`, `set_language`, and `User.preferred_language` applied at login. Catalogues live in `locale/{en,es}/LC_MESSAGES/django.po`. Only WP0 and WP17 run `makemessages`, to avoid merge conflicts.
- **Game client:** i18next with JSON namespaces `locales/{lang}/{common,hud,input,board,errors,events}.json`. Each frontend package owns its namespace. The language comes from `<html lang>` set by Django.
- **Coverage checks:**
  - CI checks that every key exists in every language.
  - CI checks that every engine `RuleError` code and event/notice code has an `errors.*`/`events.*` key; a Python test exports the codes to `protocol/codes.json`.
- **Adding a language** = one entry in `LANGUAGES` + one `.po` + one locale folder.
- The engine only sends codes and parameters, never sentences.

---

## 8. Testing strategy

1. **Engine unit tests** (pytest, no Django):
   - coords and canonicalisation
   - topology counts (19 hexes → 54 vertices, 72 edges)
   - generator invariants (hypothesis)
   - placement rules (distance rule, connectivity, pieces)
   - construction conflicts (same and neighbouring vertex, simultaneous finish, cancel on settler move)
   - movement timing with and without roads
   - production, the bank shortage rule in all three cases, fishing grounds
   - robber percentage, rounding and targeting options
   - trade ratios and settings validation and migration
2. **Invariant properties, checked after every step:**
   - resource conservation (bank + hands + escrow = constant)
   - pieces conservation
   - no two settlements adjacent
   - every non-setup building connected
   - points recompute equals the cached points
   - scheduler heap ordered
3. **Simulation:** `engine/sim` bots (random-legal and greedy) play full 2–4 player games under `ManualClock` across many seeds and board sizes. Assertions: the game ends, invariants hold, there are no exceptions, and duration is in the expected range of rolls. This doubles as a tool for balancing the setting defaults.
4. **Determinism and persistence:**
   - `codec.load(codec.dump(s))` gives the same `state_hash`.
   - Replaying the command log from any snapshot reproduces the final hash.
   - A test with "kill" mid-game, restore and continue reaches the same state as an uninterrupted run.
5. **Visibility:** `filter_events` never leaks resource types of other seats when `hands=counts`. These tests become the base for the fog tests later.
6. **Game host:** a runner with `ManualClock` and in-memory channel layer: timer precision (logical times exact), command ordering, rejects, snapshot and command flush, lease takeover.
7. **Channels:** `WebsocketCommunicator` tests for auth, seat mapping, spectator restrictions, rate limit, `sync`/gap recovery, and two clients racing to the same vertex.
8. **Contract:** Python writes golden messages to `protocol/fixtures/*.json`. TS tests feed them through `GameStore` reducers. CI checks that the generated TS types are up to date.
9. **Frontend unit tests (Vitest):** reducers, interpolation, geometry and picking, key-binding conflicts, direction-to-neighbour mapping, i18n key completeness.
10. **End-to-end (Playwright):** two browser contexts sign up, create and join a game, place settlements with the keyboard, see a dice roll, and play to the end with a shortened target (a test preset with fast rolls).
11. **Load smoke test:** spawn 200 simulated games in one game host and measure loop lag.

---

## 9. Stage 1 work packages (ordered; parallel waves)

The ownership rule: each package owns the listed files exclusively. Shared registries are created as stubs by an earlier package so later packages do not edit the same files.

**Wave 0**
- **WP0 Bootstrap.**
  - Goal: a runnable empty project, CI and the development stack.
  - Owns: `pyproject.toml`, `uv.lock`, `manage.py`, `config/**`, `docker-compose.yml`, `Procfile`, `.github/workflows/**`, `pre-commit`, empty app skeletons (`accounts`, `lobby`, `gamehost`, `gameplay` with stub `urls.py`, `routing.py`, `apps.py`), `accounts/models.py` (custom User, which must exist before the first migration), `engine/__init__.py` plus a test forbidding Django imports in `engine`, `frontend/package.json`, `vite.config.ts`, `tsconfig.json`, entry stubs, the Vite manifest template tag, the i18n framework settings, the initial `locale/` and `frontend/src/i18n/` setup.
  - Depends on: nothing.

**Wave 1 (parallel)**
- **WP1 Settings schema.**
  - Goal: `GameSettings` with all groups, bounds, stage markers, rejection of later-stage values, cross-field validation hooks, `presets/classic.json`, the migrations scaffold, JSON Schema export.
  - Owns: `engine/settings/**`, `engine/rng.py`.
  - Depends on: WP0.
- **WP2 Coordinates and topology.**
  - Goal: canonical vertex/edge keys, adjacency, dense-id `Board`, spiral and ring helpers.
  - Owns: `engine/board/coords.py`, `engine/board/topology.py` and their tests.
  - Depends on: WP0.
- **WP9 Accounts.**
  - Goal: sign-up, login and logout, password reset, profile (language, key bindings JSON endpoint), base templates and layout, language switcher.
  - Owns: `accounts/**` except the model fields created in WP0 (WP9 may add migrations), `templates/base.html`, `templates/accounts/**`.
  - Depends on: WP0.

**Wave 2 (parallel)**
- **WP3 Board generator.**
  - Goal: steps 1–7 of §6, `BoardGenerationError`, hypothesis invariants.
  - Owns: `engine/board/generator.py`.
  - Depends on: WP1, WP2.
- **WP4 State, scheduler, protocol and orchestrator skeleton.**
  - Goal: the `GameState` dataclasses with all stage 1 fields, plus placeholder fields or extension slots for dev cards, offers and visibility.
  - Also: `scheduler.py`, `codec.py` (dump, load, hash), `commands.py`, `events.py` (Pydantic, with JSON Schema export to `protocol/`), `errors.py` base, `game.py` with the handler registry and the `new_game`/`apply`/`advance` contract.
  - Also: stub modules `engine/rules/*.py` with the declared function signatures, and `views.py` with an open-map identity projection plus hand redaction.
  - Owns: `engine/state.py`, `scheduler.py`, `codec.py`, `commands.py`, `events.py`, `errors.py`, `game.py`, `views.py` (initial), `engine/rules/__init__.py`, `protocol/schema/**`.
  - Depends on: WP1, WP2. It can run alongside WP3 by using `Board` from WP2 and a trivial fixed test board.
- **WP10 Lobby and game records.**
  - Goal: `Game` and `GamePlayer` models; lobby list, create (preset + a few stage 1 overrides: board size, roll interval, target), join, leave, colour, ready; host start (validates through `GameSettings` and a dry-run generator call); LobbyConsumer for live seats; the `game.start` message plus the `STARTING` status.
  - Owns: `lobby/**`, `templates/lobby/**`, `frontend/src/entries/lobby.ts`.
  - Depends on: WP1. It needs WP3 only for the dry-run, which can be stubbed until WP3 lands.

**Wave 3 (parallel)**
- **WP5 Movement.**
  - Goal: `walkgraph.py` (A*, landing points), `rules/movement.py` (`move_settler` replace/append, `settler_arrive` timer, step and path events, road speed, the "settler left vertex" callback that construction uses).
  - Owns: `engine/board/walkgraph.py`, `engine/rules/movement.py`.
  - Depends on: WP3, WP4.
- **WP6 Setup, placement and construction.**
  - Goal: per-player setup, distance and connectivity rules, `buildable` sets, timed construction with escrow, cancel and refund, first-to-finish conflicts, builder policy, starting materials and starting resources, settler leaves after setup, first settlement starts the dice clock.
  - Owns: `engine/rules/setup.py`, `placement.py`, `construction.py`.
  - Depends on: WP4. It uses movement only through the declared callback, so it runs in parallel with WP5.
- **WP7 Economy loop.**
  - Goal: the dice timer, production with the shortage rule and fishing grounds, robber on 7 (percentage, targets, random neighbour move), bank and harbor trade, victory and `game_over`.
  - Owns: `engine/rules/dice.py`, `production.py`, `robber.py`, `trade.py`, `victory.py`.
  - Depends on: WP4.
- **WP11 Game host runtime.**
  - Goal: the `run_gamehost` command, `GameRunner` loop (§4.2), `MonotonicClock`/`ManualClock`, leases, `GameSnapshot`/`GameCommand` models, flushing, restore and replay, the STARTING scan, fan-out to seat/spectator groups, game end (results written to `GamePlayer`, status `FINISHED`), graceful shutdown.
  - Owns: `gamehost/**`.
  - Depends on: WP4 (API contract) and WP10 (the `Game` model). It can be developed against a stub engine.
- **WP13 Frontend foundation.**
  - Goal: generated protocol types, `net/` (reconnect, clock sync, intents), `state/` GameStore and reducers, `board/geometry.ts`, `sim/` interpolation, `render/Renderer.ts` interface and picking types, contract tests against `protocol/fixtures`.
  - Owns: `frontend/src/{protocol,net,state,board,sim,render}/**`, `frontend/src/locales/*/common.json`.
  - Depends on: WP4.

**Wave 4 (parallel)**
- **WP8 Visibility, simulation and replay.**
  - Goal: the final `views.py` (seat and spectator projections, redaction per the `visibility` settings), `engine/sim/` bots, the full-game simulation suite, invariant checks, replay-determinism tests, export of `protocol/codes.json` and the golden fixtures.
  - Owns: `engine/views.py` (taken over from WP4), `engine/sim/**`, `engine/tests/simulation/**`, `protocol/fixtures/**`.
  - Depends on: WP5, WP6, WP7.
- **WP12 Game WebSocket edge.**
  - Goal: `GameConsumer` (auth, seat map, spectators, message validation, rate limit, forwarding, group membership, ack/reject relay, `sync`), `gameplay/routing.py`, the `/play/<code>/` view and template that loads the game bundle with the user's bindings and language, Channels tests with an in-process runner.
  - Owns: `gameplay/**`, `templates/gameplay/**`.
  - Depends on: WP11.
- **WP14 2D renderer.**
  - Goal: the PixiJS implementation of `Renderer` (§7), camera, picking, highlights, progress bars, settler animation, path preview.
  - Owns: `frontend/src/render2d/**`, `frontend/src/locales/*/board.json`.
  - Depends on: WP13.
- **WP15 Input and controls.**
  - Goal: `ActionMap`, default bindings from the Controls table, rebinding storage and sync, keyboard and mouse handlers, box select, build mode with candidate cycling, keyboard movement queueing.
  - Owns: `frontend/src/input/**`, `frontend/src/locales/*/input.json`.
  - Depends on: WP13. Uses `Renderer.pick` through the interface, so it is parallel with WP14.
- **WP16 HUD.**
  - Goal: the Preact UI (§7), bank trade dialog, notices from reject codes, game-over screen, key-binding editor screen, `entries/game.ts` composition (store + renderer + input + UI).
  - Owns: `frontend/src/ui/**`, `frontend/src/entries/game.ts`, `frontend/src/locales/*/{hud,errors,events}.json`.
  - Depends on: WP13.

**Wave 5**
- **WP17 Translation pass.**
  - Goal: run `makemessages`/`compilemessages`; write the full Spanish `.po` and Spanish JSON catalogues; CI completeness checks (JSON keys in every language; every engine code translated); check language switching end to end.
  - Owns: `locale/**`, `frontend/src/locales/es/**`, `scripts/i18n_check.*`.
  - Depends on: WP8 (codes), WP14–WP16.
- **WP18 Integration, end-to-end tests and deployment.**
  - Goal: Playwright two-player smoke test with a fast test preset, the 200-game load smoke for the game host, Dockerfile, production settings (static files, allowed hosts, secure WebSocket origin check), process layout (web, gamehost, redis, postgres), README for running locally, fixes to integration bugs found.
  - Owns: `e2e/**`, `Dockerfile`, `deploy/**`, `README.md`. It may make small fixes in other packages' files, coordinated with their owners.
  - Depends on: everything.

**Critical path:** WP0 → WP1/WP2 → WP4 → WP6 → WP8 → WP17/WP18. The Django track (WP9 → WP10 → WP11 → WP12) and the frontend track (WP13 → WP14/15/16) run beside the engine track. Harbor trade is pulled into WP7 because it is about 30 lines and the generator already places harbors; drop it if stage 1 scope must stay strictly as the design says.

**How later stages plug in without rewrites:**
- **Development cards and knights:** state fields, an `rules/devcards.py` module, a cooldown timer kind, and `robber.move(by=seat, max_dist)`.
- **Trading board:** an `offers` entity with expiry timers and private-audience redaction in `views`.
- **Presets and share codes:** the settings package plus the `SettingsPreset` model.
- **Growing sight and fog:** a `visibility.py` module that keeps each seat's seen and visible hex sets, plus a `views.filter_events` that drops or reveals events.
- **Settlers variation:** `builder_required="always"`, `leave_after_setup=false`, a `buy_settler` command.
- **3D view:** `render3d/` implementing `Renderer` with the same store, geometry, picking and HUD.

---

## 10. Key risks and open questions for the user

**Open questions (the design is ambiguous here)**
1. **Build times in Classic after setup.** Do network builds also take the 3/8/10 s build time, with progress bars? My proposed default is yes (setting `network_builds_timed`). Instant builds would be the alternative.
2. **Settler walking speed.** The design gives no value. Proposed: 1.5 s per edge, 0.75 s on own roads.
3. **Players who never build.** What if a player never places their setup settlements (AFK or disconnected)? Options: nothing (they just produce nothing), auto-place after a timeout, or remove them from the game.
4. **Rest of the game during setup.** Can a player still in setup trade their starting materials with the bank, or build on the network? Proposed: bank trade allowed; network building only after their own setup is complete.
5. **Robber targeting.** Should "only players with a building next to the robber" also require being over the card limit? Proposed: two independent flags. Also: is adjacency judged before the robber moves (proposed: yes)? Can the robber move onto fishing grounds or the desert (proposed: land only, desert included)? Do stolen cards go back to the bank (proposed: yes)?
6. **Starting materials.** Are they taken from the bank (which affects the shortage rule) or created? Proposed: from the bank.
7. **Fishing tokens and the 6/8 rule.** Do the 6/8 tokens on fishing grounds count toward the "not adjacent" rule with land hexes? Proposed: yes.
8. **Larger boards.** How should tokens, harbors and fishing grounds scale? Proposed: auto-scale proportionally with a largest-remainder method, with explicit counts overriding.
9. **Harbors.** Pull harbor trade into stage 1 (cheap) or keep it in stage 2 as the design says?
10. **Reconnection.** It is listed in stage 2, but the snapshot and `sync` design gives basic reconnect almost for free. Include page-refresh recovery in stage 1?
11. **Deployment.** What is the target (single VPS with docker-compose, PaaS, university server)? This decides process supervision and whether a single game host shard is enough at first.
12. **Django version.** 5.2 LTS (proposed) or 6.0?

**Technical risks**
- **Latency fairness.** "First request wins" and "first to finish wins" favour players with low latency. Mitigation: the server timestamp decides, so latency effects stay small at 3–10 s build times. Show conflict notices clearly.
- **Single game host process.** It is a single point of failure in stage 1. Mitigation: leases, snapshot and replay, and a supervisor restart (at most about 1 s of commands lost). Shard later.
- **Determinism discipline.** Any use of `random`, `time`, dict ordering that depends on hashing, or float maths in rule decisions breaks replay. Enforce it with the replay test in CI and a lint rule that bans `random`/`time` imports in `engine/`.
- **Two-language type contract.** Python and TS types could drift apart. Mitigation: generated types plus golden fixtures in CI.
- **Generator feasibility.** The 6/8 rule and harbor spacing can be impossible on odd configurations. Mitigation: retry with restarts, plus validation in the lobby before start.
- **Keyboard movement on a three-neighbour vertex graph.** Some key directions have no good neighbour. Mitigation: a 90° tolerance, plus the click-to-walk pathfinding as the main control.
- **Event volume with many settlers or large boards.** Per-edge step events are small (about 100 bytes, roughly one per second per walking settler), so this is fine for stage 1. Batch per loop iteration.
- **Trademark and IP.** Game mechanics are not protected, but avoid the "Catan" name, its art and its card designs in the shipped game and repo.
