# Ages of the Island — Game Design

Copy of the design doc (Claude Docs: https://claude.ai/artifact/2s1s47uJvTgW79Cpj3CheF), synced Oct 21, 2026. The doc is the source of truth; re-sync this copy after changes.

## Vision

Ages of the Island is Settlers of Catan played in real time: a server clock rolls the dice on a fixed interval, and every player builds at the same moment instead of waiting for a turn. Every game opens with settlers: characters each player walks around the island, like villagers in Age of Empires, to build their first two settlements. A planned variation keeps them for all building. There is no combat in the first version.

Design pillars:

- **Catan first.** The default preset uses the base game's board, costs, cards and scoring. Changes are only those needed for real-time play.
- **Everything is a setting.** Every number in this doc is a variable, and the value shown is only its default. Rules, timings, visibility and controls are lobby options. Settings can be saved as named presets.
- **Server decides.** The server owns the clock, the dice and the game state. Clients only send intentions (move here, build this).
- **Two views, one game.** A fast 2D view and a three.js 3D view draw the same state, and each player picks one.

## Classic foundation (base game rules)

The default preset copies the Catan base game for 3–4 players. Each value below is the default for a lobby setting.

**Board.** The standard board has 19 land hexes surrounded by sea. Bigger boards are available from the first version and scale every count below:

- 4 forest, 4 pasture, 4 fields, 3 hills, 3 mountains and 1 desert.
- 18 number tokens: one each of 2 and 12, and two each of 3, 4, 5, 6, 8, 9, 10 and 11.
- The red numbers 6 and 8 never sit on neighbouring hexes.
- 9 harbors: 4 generic 3:1 harbors and 5 resource-specific 2:1 harbors, one per resource.
- The robber starts on the desert.

| Terrain | Resource | Hexes |
| --- | --- | --- |
| Forest | Lumber | 4 |
| Pasture | Wool | 4 |
| Fields | Grain | 4 |
| Hills | Brick | 3 |
| Mountains | Ore | 3 |
| Desert | none | 1 |

**Fish.** Fish is a sixth resource, part of the game from the start. It comes from 6 fishing grounds: sea hexes along the coast, each with its own number token (4, 5, 6, 8, 9 and 10 by default). A settlement or city touching a fishing ground gets fish when that number is rolled, like any land hex. Fish pays for extra settlers, and any other cost can include fish through the settings.

**Bank.** The bank holds 19 cards of each resource. If it cannot pay every player owed a resource, nobody gets that resource on that roll. The exception is when only one player is owed it, who then gets what is left.

**Pieces per player.** Each player has 15 roads, 5 settlements and 4 cities. Building a city returns its settlement to the player's supply.

| Build | Cost | Points |
| --- | --- | --- |
| Road | 1 brick, 1 lumber | 0 |
| Settlement | 1 brick, 1 lumber, 1 wool, 1 grain | 1 |
| City (upgrades a settlement) | 2 grain, 3 ore | 2 |
| Development card | 1 wool, 1 grain, 1 ore | varies |

**Placement.**

- Settlements go on corners where three hexes meet. No settlement may sit on a corner next to another settlement (the distance rule).
- After setup, every road and settlement must connect to the player's own road network.
- A hex produces its resource for each adjacent settlement (1 card) and city (2 cards) when its number is rolled.

**Development cards.** The deck has 25 cards:

- 14 knights. Playing one lets that player move the robber up to 3 hexes away and steal 1 card (adjustable) from a player there. This is the only time a player controls the robber.
- 5 victory point cards. Each counts only once played, and playing one follows the same cooldown as any other card.
- 2 road building, which places 2 free roads.
- 2 year of plenty, which takes any 2 resources from the bank.
- 2 monopoly, which takes every card of one named resource from all players.

**Robber and sevens.** On a 7, nothing is produced. The robber takes a random 50% of the cards, rounded down, from every player holding more than 7. The robber then moves by itself to a random neighbouring hex and blocks its production. No player controls the dice or the robber.

**Trading.**

- With the bank: 4:1, from anywhere.
- At harbors: 3:1 or 2:1, for a player with a settlement or city on that harbor.
- With other players: any terms both sides accept.

**Winning.**

- Longest Road: 2 points for the longest unbroken road of at least 5 segments.
- Largest Army: 2 points for the most knights played, at least 3.
- First player to reach 10 points wins.

## Real-time adaptation

Turns are replaced by a clock that rolls two dice every 20 seconds by default. One roll stands in for one Catan turn. A 4-player game of about 60 rolls then lasts about 20 minutes plus setup. Each change below keeps the base rule's intent and is a lobby setting.

| Catan rule | Real-time version (default) | Options |
| --- | --- | --- |
| Players take turns | Everyone acts at once; the dice roll on a timer | Interval 5–120 s; pause on demand if all agree |
| Active player rolls | Server rolls; a countdown ring shows the next roll | Two dice, or a 36-card dice deck for even odds |
| Setup: snake order, 2 settlements and 2 roads each | No turn order: each player's settler walks out and builds both settlements with starting materials; the first to finish a spot claims it (see Settlers) | Snake-order picks by clicking, no walking; random start |
| Second settlement gives starting resources | Both of the first 2 settlements give starting resources | Off |
| Roller moves the robber on a 7 | Nobody: the robber moves by itself to a random neighbouring hex. A knight card lets its player move it up to 3 hexes | A player moves it on a 7 (seat rotation, random, or fewest points); robber off |
| Discard half above 7 cards | The robber takes a random 50% at once; nobody chooses | Card limit and percentage; rob everyone over the limit, or only those with a building next to the robber; off |
| Build only on your turn | Build whenever you can pay, anywhere connected to your road network | Settlers variation: a settler must walk to the site |
| One development card per turn, not the one just bought | One card per roll interval, victory point cards included; a new card unlocks at the next roll | Cooldown in seconds |
| Trade on your turn | Open trade board: post offers anytime; anyone can accept | Bank only; offers expire after N seconds |
| Two players want the same spot | First request the server receives wins; the loser gets a refund and a notice | none |
| Game ends at 10 points | Ends the moment someone reaches the target | Target 5–20; time limit, highest score wins |

## Settlers (characters you move)

Every game uses settlers to build the first two settlements. In the Settlers variation they stay for the whole game and do all the building. Settlers walk the island and build wherever they stand, so position and travel time become part of the strategy.

**Building the first settlements (every game).**

- Each player's settler lands at a random point on the coast. Landing points are spread evenly around the island.
- The settler walks from corner to corner to find the spots its player prefers. It builds the first settlement with a road next to it, then the second. The normal building rules apply, including the distance rule.
- Building takes the normal build time. If another player finishes on that corner, or a neighbouring one, first, the build is cancelled and refunded.
- Players start with enough materials to build 2 settlements and 2 roads. Each of the first 2 settlements also gives starting resources: 1 card from every neighbouring hex.
- The dice clock starts the moment anyone builds the first settlement, and it never waits. Players still walking produce nothing until their settlements stand.
- In the Classic preset the settler then leaves the map, and later building works from the road network. In the Settlers variation it stays.

**Movement.**

- Settlers walk on land, along hex edges and corners. Sea is impassable until a ships expansion.
- Walking on your own roads is faster: 2× speed by default. This gives roads a second purpose.
- Settlers of different players can pass through each other. There is no blocking or combat.
- Paths are found automatically, so a click on a distant corner walks there by the shortest route.

**Construction.**

- The settler must stand on the corner (settlement, city) or edge (road) being built.
- Resources are paid when building starts. A progress bar shows the build time.
- Cancelling refunds the full cost. Moving the settler away cancels the build.
- Development cards, trades and robber moves need no settler.

| Action | Build time (default) |
| --- | --- |
| Road | 3 s |
| Settlement | 8 s |
| City | 10 s |

**More settlers.** An extra settler costs 5 grain, 5 wool, 3 wood and 2 fish by default, up to 4 per player (more for bigger maps). A new settler appears at any of the player's settlements or cities. Settlers can improve productivity as well.

**Controls.** Keyboard and mouse work together, and every key can be rebound.

| Action | Keyboard | Mouse |
| --- | --- | --- |
| Move selected settler | W A S D or arrow keys | Right-click a spot to walk there |
| Select a settler | Tab cycles; 1–3 picks directly | Left-click it; drag a box to select several |
| Build road / settlement / city | R / E / C, then confirm with Enter | Right-click the corner or edge for a build menu |
| Buy development card | V | Card button in the hand panel |
| Open trade board | T | Trade button |
| Move the camera | Hold Shift with W A S D | Drag with the middle button; push to the screen edge |
| Zoom | + / − | Scroll wheel |
| Centre on selected settler | Space | Double-click its portrait |

Touch screens get tap to select, tap to move and long-press for the build menu. Gamepad support is a later option.

## Visibility options

Visibility has two kinds of settings. Game rules are set by the host and are the same for everyone. Display preferences are chosen by each player. The classic preset shows the whole board and hides only what Catan hides.

**Map visibility (game rule).**

| Mode | What players see | Default in |
| --- | --- | --- |
| Open map | Every hex, number, harbor, building and settler | Classic on standard boards |
| Growing sight | Only the land around your own roads, settlements and cities. The visible area grows as you build, and land once seen stays visible | Large islands (optional) |
| Explored | Like Growing sight, but settlers also reveal land as they walk | Explorer |
| Live fog | Like Explored, but other players' settlers and new buildings show only while in sight | Explorer (hard) |

Sight range is 1 hex around a road, a settlement or a settler, and 2 around a city. Each is adjustable. A "hidden numbers" option keeps a hex's number token secret until a building sits next to it.

**Information about other players (game rules).**

| Information | Classic default | Options |
| --- | --- | --- |
| Resource cards in hand | Count shown, types hidden | Fully open; fully hidden |
| Development cards | Count shown, types hidden | Open; hidden |
| Victory points | All points shown; unplayed VP cards don't count yet | Scores hidden until the end |
| Production log | Everyone sees who received what | Own production only |
| Trade offers | Visible to all | Private offers to chosen players |

**Display preferences (per player).**

- View: 2D top-down or 3D (three.js), switchable during play.
- Overlays: dot count (odds) on number tokens, dice history chart, settler paths and build ranges.
- Colour-blind palettes and pattern fills for player colours.
- Spectators can watch with the full map open or from one player's view.

## Customization

Every number in this doc is a customizable variable, and the code never hard-codes one. All of them live in one settings file per game, checked by the server when the game starts. Hosts pick a preset, change what they like, and can save the result or share it as a short code.

**Presets.**

| Preset | Purpose | Key settings |
| --- | --- | --- |
| Classic (default) | Base Catan, played in real time | Settlers walk to build the first 2 settlements from starting materials, then everything connects to your roads; open map, or Growing sight on large islands; 20 s rolls; 10 points |
| Settlers (variation) | Characters walk to build | As Classic, but a settler must stand on the site to build |
| Explorer (variation) | Discovery and scouting | Explored fog, hidden numbers, settlers, 20 s rolls |
| Blitz | Short games | 8 s rolls, 7 points |

**Setting groups.**

- **Players:** 2–6 players, with the larger board for 5–6. Seat order is random or set by the host.
- **Board:**
  - Layout: the beginner layout, random with the 6/8 rule, a fixed seed, or a saved custom map.
  - Number of each terrain, fishing grounds, number tokens and harbors.
  - Board size: any number of hexes, from the first version. Island shapes and a map editor come later; the land stays one connected island until a sea expansion.
- **Dice and clock:** roll interval, two dice or dice deck, pause after a 7, setup pick timer.
- **Economy:** cost of each build, card and settler, starting materials, starting resources per first settlement, bank size, bank and harbor ratios, hand limit on a 7.
- **Pieces:** roads, settlements and cities per player.
- **Robber:** on or off; on a 7 it randomly steals a percentage of materials (50% by default) from everyone holding more than 7 cards, or only from those with a building next to the robber; cards stolen per knight (1 by default); it moves randomly to neighbouring hexes, or up to 3 hexes when a knight card is used; and a "friendly robber" option that cannot target players with few points.
- **Development cards:** deck contents and play cooldown.
- **Settlers:** starting count, landing points, maximum, cost of extras, walking speed, road speed bonus, build times and build reach.
- **Visibility:** the rules in the Visibility section.
- **Victory:** points target, Longest Road and Largest Army thresholds, optional time limit.
- **Trading:** player trades on or off, offer expiry, private offers.

## Scope

Version 1 is the Classic preset, fully playable online in the 2D view by 2–4 people. Everything else builds on that.

| Stage | Contents |
| --- | --- |
| 1. Playable core | Accounts and login, lobby, random board of adjustable size with fish and fishing grounds, dice clock, settlers walking to build the first settlements (keyboard and mouse), resources, building on the road network, robber, bank trade, scoring, 2D view, English and Spanish interface |
| 2. Full base game | Development cards, Longest Road, Largest Army, player trading board, harbors, reconnecting after a dropped connection |
| 3. Customization and variations | All lobby settings, presets, share codes, large islands with Growing sight, Settlers variation, Explored and Live fog |
| 4. 3D view | three.js renderer on the same game state, camera controls |
| Later | 5–6 players, island shapes, map editor, computer players, ships, combat ("ages"), ranked games, gamepad |

## Decisions

- [x] Default preset: Classic. Settlers walk to build the first 2 settlements, wherever their player prefers; after that everything connects to the road network. Settlers doing all the building is a later variation.
- [x] Visibility: Growing sight, optional, for large islands.
- [x] Robber on a 7: nobody controls it; it moves to a random neighbouring hex. Only a knight card lets a player move it, up to 3 hexes.
- [x] Roll interval: 20 seconds.
- [x] Computer players: not in version 1.
- [x] Players need accounts to play.
- [x] Interface in English and Spanish from the start, with all text kept in translation files so more languages can be added later.
