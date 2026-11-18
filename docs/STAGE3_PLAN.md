# Stage 3 plan: customization and variations

Stage 3 of `docs/GAME_DESIGN.md` ("Scope"): all lobby settings, presets, share codes,
large islands with Growing sight, the Settlers variation, and Explored / Live fog.
Stage 1 and 2 are done (see `docs/STAGE1_PLAN.md`). Presets and a 20-rule custom
game already exist (`lobby/presets.py`, `engine/settings/presets/`).

The work is split into work packages (WP19–WP25), one pull request each, built in
this order. Each one leaves the game playable.

## Ground rules

- The engine rules in `CLAUDE.md` still apply (pure, deterministic, every number in
  `GameSettings`, error codes not sentences).
- **Stage gate.** `IMPLEMENTED_STAGE` becomes 2 in WP19 (stage 2 is done), so hosts
  may change stage-2 settings. A stage-3 field or enum value is unlocked one by one,
  as the package that implements it lands, by listing it in
  `engine/settings/models.py` `EARLY_FEATURES`. When stage 3 is complete,
  `IMPLEMENTED_STAGE` becomes 3 and the list is emptied.
- Every user-facing string in English and Spanish.

## Work packages

### WP19 Share codes (foundation)
- Engine `engine/settings/share.py`: `encode_share_code(preset, overrides)` and
  `decode_share_code(code)`. Format `<preset>.<schema_version>.<payload>`, payload =
  `base64url(zlib(canonical_json(overrides)))`, empty when nothing changes.
  Size limits on the code and on the unpacked JSON; older schema versions are
  migrated; errors are codes (`settings.share.*`).
- `IMPLEMENTED_STAGE = 2`.
- Lobby: the game page shows the game's code with "copy code" and "copy link"
  buttons. The create form takes a pasted code (or `?config=<code>` in the link)
  and creates the game from it. The game page lists changed rules for every game
  type, not only Custom.
- Owns: `engine/settings/share.py`, its tests, lobby form/view/template changes.

### WP20 Every setting in the lobby
- A settings editor built from the settings JSON schema (labels, bounds, enum
  choices, stage), grouped like the design's setting groups, covering every
  implemented field. The 20 quick rules stay as the simple view; "all settings"
  opens the full list.
- The host can still change settings on the game page until the game starts; the
  other seats see the change live and lose their "ready".
- Saved configurations: `lobby.SettingsPreset` (owner, name, preset, overrides);
  "save" on the game page, "my configurations" on the create form.
- Spanish and English labels for every setting (`settings.*` keys).
- Owns: `lobby/settings_editor.py`, `frontend/src/lobby/editor.ts`, the model and
  migration, templates.

### WP21 Growing sight and hidden numbers (engine)
- `engine/rules/visibility.py`: per seat `seen` hexes (never shrinks) and
  `visible` hexes (in sight now), from `visibility.sight` around roads,
  settlements, cities and megacities; stored in `state.ext["visibility"]`,
  updated on `SIG_BUILT`.
- `visibility.map = growing` and `hidden_numbers` unlocked.
- Per-viewer board: hexes, numbers, harbors and fishing grounds never seen are
  left out of the `board` message and arrive in a `reveal` event when first seen.
  `project_state` and `filter_events` drop buildings, roads, constructions, robber
  moves and production on hexes the viewer has not seen. Spectators see everything.
- Bots keep reading the full state (they are not told what they cannot see in
  this stage; noted as a later fix).
- Tests: no leak of unseen hexes or numbers in any message for any seat, over
  seeded games.

### WP22 Fog and the growing view in the client
- 2D renderer: unseen sea of cloud, seen-but-not-in-sight land dimmed, in sight
  normal. `reveal` events add hexes with a short fade.
- Growing view: the camera starts framed on the player's own area and its limits
  grow with the seen area; "centre on my land" key.
- Large-island presets (`huge`) default to Growing sight; the create form and
  game page say when a game uses it.

### WP23 Settlers variation
- `buy_settler` command (cost `economy.costs.settler`, `settlers.max`), new settlers
  appear at an own building (`settlers.spawn_at`).
- `settlers.builder_required = always`, `leave_after_setup = false`,
  `build_reach_edges`: a settler must stand on (or near) the site to build.
- Client: buy button, settler list and selection (Tab / 1–3 exist), build menu
  limited to sites a settler can reach.
- Bots: buy and walk settlers to their chosen sites.
- New preset `settlers`.
- Questions for Emerson before building: settler price, walking speed on long
  islands, whether settlers can be lost.

### WP24 Explored and Live fog
- `explored`: settlers also reveal land as they walk (sight per step).
- `live_fog`: other players' settlers and new buildings show only while in sight;
  their old buildings stay as last seen.
- New preset `explorer` (Explored fog, hidden numbers, settlers, 20 s rolls).
- Client: last-seen buildings drawn faded.

### WP25 Remaining stage-3 rule options (to confirm with Emerson)
- Small rules marked stage 3 in the settings: dice deck, beginner layout, game
  time limit, scores hidden until the end, private trade offers, friendly robber,
  robber moved by the player on a 7, pause after a 7, extra dice / sides.
- Each is unlocked when built; then `IMPLEMENTED_STAGE = 3`.

## Order and dependencies

WP19 → WP20. WP21 → WP22 → WP24. WP23 → WP24. WP25 last; parts of it can go
earlier if Emerson asks.
