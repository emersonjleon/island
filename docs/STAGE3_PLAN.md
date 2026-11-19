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
- 2D renderer: unseen sea of cloud, seen-but-not-in-sight land dimmed, in sight
  normal. `reveal` events add hexes with a short fade.
- Growing view: the camera starts framed on the player's own area and its limits
  grow with the seen area; "centre on my land" key.
- Large-island presets (`huge`) default to Growing sight; the create form and
  game page say when a game uses it.

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
- `buy_settler` command: pays `economy.costs.settler` (default 1 lumber, 1 wool,
  1 grain, 2 fish), up to `settlers.max`; the settler appears at one of the
  player's buildings (`settlers.spawn_at`). Codes `settler.*`.
- `settlers.leave_after_setup = false` and `settlers.builder_required = always`
  (unlocked): a settler must stand on the site to build, settlement and city.
- Gathering (`settlers.gather`, off by default): each settler has its own numbers,
  given by its order among the player's settlers from `settlers.gather_rolls`
  (default `[[3], [11], [2, 12]]`: each 2 in 36, the same chance). On that roll a
  settler at rest (not walking, not building) takes `settlers.gather_cards` (1) of
  each producing hex around its corner from the bank (fishing grounds count, the
  robber's hex and the desert do not). Event `settlers_gathered` (like `produced`,
  follows `visibility.production_log`).
- Robber: `settlers.block_robber` (off by default): the robber cannot move onto a
  hex with a settler on one of its corners (random moves pick another neighbour;
  a knight gets `robber.blocked_by_settler`).
- Ages hook (built with WP26): `settlers.build_unconnected` = `none` / `coast` /
  `any`. Mar: a settler can build a settlement on the beach without a road;
  Dorada: anywhere.

**WP23b client, bots and preset**
- Buy button with the price, settler list and selection (Tab / 1–3 exist), each
  settler's numbers shown on its token, gathering in the log.
- Bots buy settlers when they can, send them to their chosen sites and park the
  others where they gather most.
- New preset `settlers`: settlers stay, build, gather and block the robber;
  max 3 settlers.

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
