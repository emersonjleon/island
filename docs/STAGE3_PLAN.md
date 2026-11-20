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
- `engine/sight.py` (pure helpers) and `engine/rules/visibility.py` (an
  `after_step` hook): per seat `seen` hexes (never shrinks) in
  `state.ext["visibility"]`, from `visibility.sight` around the seat's roads,
  settlements, cities and megacities. Settlers see around them too: with Growing
  sight only until the player's first settlements are done, with Explored / Live
  fog always. In sight now (`in_sight`) is worked out from the pieces.
- `hidden_numbers`: a token shows once a building stands next to its hex
  (`ext["visibility"]["numbers"]`, `numbers_revealed` event).
- Per-viewer board (`engine.sight.board_for`, sent by `gamehost.core.sync`):
  only seen hexes and the vertices, edges, fishing grounds and harbors on them,
  with `partial: true`; vertices and edges list only seen hexes. New land arrives
  in a private `revealed` event with the board there and the pieces on it.
  `project_state` and `filter_events` drop other players' buildings, roads,
  constructions, settlers (and their paths) and the robber on unseen hexes.
  Spectators see everything.
- Bots keep reading the full state (they are not told what they cannot see in
  this stage; noted as a later fix).
- Tests: no leak of unseen hexes, pieces or numbers in any message for any seat,
  over seeded games (`engine/tests/test_visibility.py`).
- `visibility.map = growing` and `hidden_numbers` stay locked in the lobby until
  WP22 can draw them; WP22 adds them to `EARLY_FEATURES`.

### WP22 Fog and the growing view in the client
- The client keeps the board by id (`indexBoard`, holes for unseen land) and
  grows it with `revealed` and `numbers_revealed`; pieces on new land replace
  what it had there. Pieces, settlers and paths on unknown places are not drawn.
- 2D renderer: two rings of cloud round the seen land; a hidden number shows as
  "?". The camera starts framed on the player's own area (at least 8 hex radii)
  and does not jump when new land appears.
- `visibility.map = growing`, `visibility.hidden_numbers` and `visibility.sight`
  are in `EARLY_FEATURES`, so the lobby offers them (all settings). Huge defaults
  to Growing sight; its description, the game page and the code preview say so.
- e2e `fog.cjs`: a code link with Growing sight and hidden numbers, play now
  against bots, walk to reveal land, nothing out of sight reaches the page.
- Dimming land that is seen but no longer in sight moves to WP24 (Live fog),
  where it matters.

### WP23 Settlers variation
Emerson's answers (Nov 19, 2026): you see the land around your settlers,
buildings and roads; settlers are not lost (maybe later); a settler has a price
that includes fish and can be changed; settlers also do something else (gather
materials around them on their own numbers, block the robber), and this grows
with the ages (docs/AGES_DESIGN.md).

Split in two pull requests.

**WP23a engine**
- Sight: settlers always see around them (`visibility.sight.settler`), with every
  fog mode, not only before the first settlements.
- `buy_settler` command, only when settlers stay (`settlers.leave_after_setup =
  false`): pays `economy.costs.settler` (default 1 lumber, 1 wool, 1 grain,
  2 fish), up to `settlers.max`; the settler appears at one of the player's
  buildings (`settlers.spawn_at`). Codes `settler.*`.
- `settlers.builder_required = always` stays locked for now: building from the
  network keeps working, settlers gather and guard.
- Gathering (`settlers.gather`, off by default): each settler has its own numbers,
  given by its order among the player's settlers from `settlers.gather_rolls`
  (default `[[3], [11], [2, 12]]`: each 2 in 36, the same chance). On that roll a
  settler at rest (not walking, not building) takes `settlers.gather_cards` (1) of
  each producing hex around its corner from the bank (fishing grounds count, the
  robber's hex and the desert do not). Event `settlers_gathered` (like `produced`,
  follows `visibility.production_log`).
- Robber: `settlers.block_robber` (off by default): the robber cannot move onto a
  hex with a settler on one of its corners (random moves pick another neighbour;
  a knight gets `dev.blocked_by_settler`).
- Ages hook (built with WP26): `settlers.build_unconnected` = `none` / `coast` /
  `any`. Mar: a settler can build a settlement on the beach without a road;
  Dorada: anywhere.

**WP23b client, bots and preset**
- Settler button in the hand bar (key B) with the price, "n/max" and the next
  settler's numbers; each own settler shows its numbers in a pill under it;
  gathering in the log.
- Bots buy a settler when they have nothing to build and park each idle settler
  on the corner near their buildings that touches the most producing hexes.
- New preset `settlers`: settlers stay, gather and block the robber; max 3.
- The settler settings are unlocked through `EARLY_FEATURES` (all but
  `build_reach_edges` and `builder_required = always`).

### WP24 Explored and Live fog
- Settlers' sight by map: Growing sight, where a settler stops; Explored and Live
  fog, also while it walks.
- `live_fog`: other players' settlers, constructions and the robber show only
  while in sight now; other players' buildings and roads out of sight stay as last
  seen (`ext.visibility.memory`). A private `sight` event gives the hexes in sight
  whenever they change; land coming back into sight is sent again in `revealed`.
- The fog lifts at the end of every fog game (`lift_fog`, after victory).
- New preset `explorer`: Explored, hidden numbers, settlers that stay, gather
  and guard. `visibility.map = explored / live_fog` unlocked early.
- Client: land seen but out of sight is veiled under Live fog, so what stands
  there reads as remembered; the fog is a soft mist (no hex tiles).

### WP25 Remaining stage-3 rule options (to confirm with Emerson)
- Small rules marked stage 3 in the settings: dice deck, beginner layout, game
  time limit, scores hidden until the end, private trade offers, friendly robber,
  robber moved by the player on a 7, pause after a 7, extra dice / sides.
- Each is unlocked when built; then `IMPLEMENTED_STAGE = 3`.

## Order and dependencies

WP19 → WP20. WP21 → WP22 → WP24. WP23 → WP24. WP25 last; parts of it can go
earlier if Emerson asks.
