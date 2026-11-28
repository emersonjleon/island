"""Development cards and Largest Army (stage 2).

* ``buy_dev_card``: a player whose setup is done pays ``economy.costs.dev_card`` to
  the bank and draws a random card from what is left of ``dev_cards.deck``
  (``state.rng``, one draw per purchase). With ``dev_cards.refill`` an empty deck is
  replaced by a fresh copy of ``dev_cards.deck`` before the draw. Emits ``Hand`` then ``DevCardBought``.
  With ``vp_cards_must_be_played`` off a victory point card counts at once.
* ``play_dev_card``: the card must be in the hand and playable:

  - ``cooldown == "per_roll"``: bought before the latest dice roll, and no card
    played since that roll (one card per roll interval, victory points included);
  - ``cooldown == "ms"``: ``cooldown_ms`` passed since it was bought and since the
    player's last play.

  Cards: **knight** moves the robber to ``hex`` (a legal robber hex at distance
  1..``robber.knight_max_distance``) and steals ``robber.knight_steal`` random cards
  from ``victim``, a player with a building on that hex (the card's player picks;
  a single possible victim is picked for them; players still in setup are spared
  with ``robber.spare_setup``); **victory point** adds
  ``dev_cards.victory_point_points``; **road building** gives
  ``dev_cards.road_building_roads`` free roads (built normally, at no cost; see
  :func:`engine.rules.placement.build_cost`); **year of plenty** takes
  ``dev_cards.year_of_plenty_cards`` named resources from the bank; **monopoly**
  takes every card of one resource from the other players (players still in setup
  are spared with ``robber.spare_setup``).

  Emits ``DevCardPlayed`` (public) and the ``RobberMoved`` / ``Hand`` / ``Points`` /
  ``LargestArmy`` events that follow from it.

Advanced developments (ages with ``ages.dev_tiers``, docs/AGES_DESIGN.md): ``buy_dev_card``
with ``tier`` 2 or 3 draws from ``dev_cards.deck_tier2`` / ``deck_tier3`` (each its own deck,
refilled like the first) for ``economy.costs.dev_card_tier2`` / ``dev_card_tier3``, from that
age on. The one-card-per-roll rule is shared by every tier. Cards:

* **veteran knight** / **elite knight**: a knight that moves the robber up to
  ``dev_cards.veteran_max_distance`` / ``elite_max_distance`` hexes and steals
  ``strong_knight_steal`` cards, or ``strong_knight_hoard_steal`` from a victim holding
  more than their robber card limit; each counts as one knight for the Largest Army;
* **fishing fleet**, **merchant**, **great market**, **architect**: effects that last a
  few rolls (:mod:`engine.rules.dev_effects`); the architect names ``resources`` (no fish,
  ``architect_discount`` of them) taken off the next city or megacity;
* **causeway**: ``causeway_roads`` free roads, like road building;
* **bountiful harvest**: ``harvest_cards`` named resources from the bank, at most
  ``harvest_max_fish`` fish;
* **tribute**: each player with more points (not spared) gives ``tribute_cards`` random cards.

Largest Army (``victory.largest_army``): same award rules as Longest Road
(:func:`engine.rules.longest_road.next_holder`): at least ``min`` knights played,
the holder keeps it on a tie, a strictly larger army takes it.

State, in ``state.ext["devcards"]`` (JSON-safe, string seat keys):
``deck`` (kind -> cards left), ``decks`` (tier "2"/"3" -> kind -> cards left), ``refills`` (fresh decks shuffled in),
``tier_refills`` / ``drawn`` (tier -> refills / kind -> cards drawn, for tiers 2 and 3), ``hands`` (seat -> [{kind, at, roll}]),
``played`` (seat -> {kind: n}), ``last_play`` (seat -> {at, roll}),
``free_roads`` (seat -> n), ``vp_points`` (seat -> points from victory point
cards), ``army`` (holder seat or None), ``effects`` (see :mod:`engine.rules.dev_effects`).
A hand entry of tier 2 or 3 carries ``tier``.

Reject codes: ``dev.setup_not_done``, ``dev.deck_empty``, ``dev.cannot_afford``
{missing}, ``dev.no_card`` {card}, ``dev.too_new`` {card}, ``dev.cooldown`` {card},
``dev.not_playable`` {card}, ``dev.no_robber``, ``dev.need_hex``, ``dev.bad_hex``
{hex}, ``dev.blocked_by_settler`` {hex}, ``dev.too_far`` {hex, max}, ``dev.need_victim`` {choices}, ``dev.bad_victim``
{victim}, ``dev.need_resources`` {count}, ``dev.bank_short`` {missing},
``dev.need_resource``, ``dev.no_tiers`` {tier}, ``dev.tier_locked`` {tier, age}, ``dev.too_much_fish``
{max}, ``dev.no_fish_discount``.
"""
from __future__ import annotations

from typing import Any

from engine.board import coords
from engine.commands import BuyDevCard, PlayDevCard
from engine.errors import RuleError
from engine.events import DevCardBought, DevCardPlayed, Event, Hand, LargestArmy, RobberMoved
from engine.game import command_handler
from engine.rules import age_state, dev_effects, longest_road, placement, robber, victory
from engine.settings.enums import Cooldown, DevCardKind, InfoVisibility, Resource, Terrain
from engine.state import GameState
from engine.views import register_state_extension

__all__ = [
    "EXT_KEY", "KNIGHT_KINDS", "tiers_enabled", "tier_deck", "tier_cost", "buy_error", "deck_left", "hand", "knights", "army_holder", "vp_points", "roll_index", "card_ready",
    "player_ready", "playable", "on_buy", "on_play",
]

EXT_KEY = "devcards"
KNIGHT, VP, ROADS, PLENTY, MONOPOLY = (DevCardKind.KNIGHT, DevCardKind.VICTORY_POINT,
                                       DevCardKind.ROAD_BUILDING, DevCardKind.YEAR_OF_PLENTY,
                                       DevCardKind.MONOPOLY)
VETERAN, ELITE, FLEET, MERCHANT, GREAT_MARKET, ARCHITECT, CAUSEWAY, HARVEST, TRIBUTE = (
    DevCardKind.VETERAN_KNIGHT, DevCardKind.ELITE_KNIGHT, DevCardKind.FISHING_FLEET, DevCardKind.MERCHANT,
    DevCardKind.GREAT_MARKET, DevCardKind.ARCHITECT, DevCardKind.CAUSEWAY, DevCardKind.BOUNTIFUL_HARVEST,
    DevCardKind.TRIBUTE)
KNIGHT_KINDS = (KNIGHT, VETERAN, ELITE)       # each counts as one knight for the Largest Army
EFFECT_ROLLS = {FLEET: "fleet_rolls", MERCHANT: "merchant_rolls", GREAT_MARKET: "great_market_rolls",
                ARCHITECT: "architect_rolls"}
TIERS = (1, 2, 3)


# ---------------------------------------------------------------- read-only
def _view(state: GameState) -> dict[str, Any]:
    return state.ext.get(EXT_KEY, {})


def tiers_enabled(state: GameState) -> bool:
    """Advanced developments are on: ages with ``ages.dev_tiers``."""
    return age_state.enabled(state) and state.settings.ages.dev_tiers


def tier_deck(state: GameState, tier: int) -> dict[DevCardKind, int]:
    """The full deck of ``tier`` (``dev_cards.deck`` for tier 1)."""
    cfg = state.settings.dev_cards
    return dict(cfg.deck if tier == 1 else cfg.deck_tier2 if tier == 2 else cfg.deck_tier3)


def tier_cost(state: GameState, tier: int) -> dict[Resource, int]:
    costs = state.settings.economy.costs
    cost = costs.dev_card if tier == 1 else costs.dev_card_tier2 if tier == 2 else costs.dev_card_tier3
    return {r: int(cost.get(r, 0)) for r in Resource}


def deck_left(state: GameState, tier: int = 1) -> dict[str, int]:
    if tier == 1:
        deck = _view(state).get("deck")
    else:
        deck = _view(state).get("decks", {}).get(str(tier))
    if deck is None:
        return {k.value: n for k, n in tier_deck(state, tier).items()}
    return dict(deck)


def hand(state: GameState, seat: int) -> list[dict[str, Any]]:
    return list(_view(state).get("hands", {}).get(str(seat), []))


def knights(state: GameState) -> dict[int, int]:
    """Knights played per seat (veteran and elite knights count one each)."""
    played = _view(state).get("played", {})
    return {p.seat: sum(int(played.get(str(p.seat), {}).get(k.value, 0)) for k in KNIGHT_KINDS)
            for p in state.players}


def army_holder(state: GameState) -> int | None:
    return _view(state).get("army")


def vp_points(state: GameState, seat: int) -> int:
    return int(_view(state).get("vp_points", {}).get(str(seat), 0))


def roll_index(state: GameState) -> int:
    """Dice rolls so far; a card bought at roll ``n`` is playable from roll ``n + 1``."""
    return len(state.dice_history)


def card_ready(state: GameState, card: dict[str, Any], now_ms: int) -> bool:
    """The card is old enough: bought before the latest roll (or ``cooldown_ms`` ago)."""
    cfg = state.settings.dev_cards
    if cfg.cooldown is Cooldown.MS:
        return card["at"] + (cfg.cooldown_ms or 0) <= now_ms
    return card["roll"] < roll_index(state)


def player_ready(state: GameState, seat: int, now_ms: int) -> bool:
    """No card played since the latest roll (or within ``cooldown_ms``)."""
    cfg = state.settings.dev_cards
    last = _view(state).get("last_play", {}).get(str(seat))
    if last is None:
        return True
    if cfg.cooldown is Cooldown.MS:
        return last["at"] + (cfg.cooldown_ms or 0) <= now_ms
    return last["roll"] < roll_index(state)


def playable(state: GameState, seat: int, card: dict[str, Any], now_ms: int) -> bool:
    """Whether ``card`` (an entry of ``seat``'s hand) may be played now."""
    if card["kind"] == VP.value and not state.settings.dev_cards.vp_cards_must_be_played:
        return False
    return card_ready(state, card, now_ms) and player_ready(state, seat, now_ms)


# ---------------------------------------------------------------- mutable
def _ext(state: GameState) -> dict[str, Any]:
    ext = state.ext.setdefault(EXT_KEY, {})
    ext.setdefault("deck", deck_left(state))
    for key in ("hands", "played", "last_play", "free_roads", "vp_points"):
        ext.setdefault(key, {})
    ext.setdefault("army", None)
    return ext


def _add_points(state: GameState, seat: int, delta: int, now_ms: int) -> list[Event]:
    if delta == 0:
        return []
    p = state.player(seat)
    p.points += delta
    if p.points >= state.settings.victory.target and not p.resigned:
        victory.finish(state, seat, now_ms)
    return [victory.points_changed(state, seat, now_ms)]


def _hand_event(state: GameState, seat: int, now_ms: int) -> Hand:
    return Hand(at=now_ms, seat=seat, hand=dict(state.player(seat).hand))


def _check_active(state: GameState, seat: int) -> None:
    if not state.player(seat).setup_done:
        raise RuleError("dev.setup_not_done", {})


# ---------------------------------------------------------------- buy
def _draw(state: GameState, deck: dict[str, int]) -> DevCardKind:
    pick = state.rng.randbelow(sum(deck.values()))
    for kind in DevCardKind:                       # fixed order: deterministic
        n = deck.get(kind.value, 0)
        if pick < n:
            return kind
        pick -= n
    raise AssertionError("unreachable: pick within deck total")


def buy_error(state: GameState, seat: int, tier: int = 1) -> RuleError | None:
    """Why ``seat`` cannot buy a ``tier`` development now, or None."""
    if not state.player(seat).setup_done:
        return RuleError("dev.setup_not_done", {})
    if tier > 1:
        if not tiers_enabled(state):
            return RuleError("dev.no_tiers", {"tier": tier})
        age = age_state.age_of(state, seat)
        if age < tier:
            return RuleError("dev.tier_locked", {"tier": tier, "age": age})
    full = sum(tier_deck(state, tier).values())
    refill = state.settings.dev_cards.refill and full > 0
    if sum(deck_left(state, tier).values()) <= 0 and not refill:
        return RuleError("dev.deck_empty", {})
    missing = placement.missing_resources(state.player(seat).hand, tier_cost(state, tier))
    if missing:
        return RuleError("dev.cannot_afford", {"missing": missing})
    return None


@command_handler("buy_dev_card")
def on_buy(state: GameState, seat: int, cmd: BuyDevCard, now_ms: int) -> list[Event]:
    tier = cmd.tier
    err = buy_error(state, seat, tier)
    if err is not None:
        raise err
    # ---- validated; mutate from here on
    p = state.player(seat)
    ext = _ext(state)
    for r, n in tier_cost(state, tier).items():
        p.hand[r] -= n
        state.bank[r] += n
    if tier == 1:
        deck = ext["deck"]
    else:
        deck = ext.setdefault("decks", {}).setdefault(str(tier), deck_left(state, tier))
    if sum(deck.values()) <= 0:
        deck.clear()
        deck.update({k.value: n for k, n in tier_deck(state, tier).items()})
        if tier == 1:
            ext["refills"] = int(ext.get("refills", 0)) + 1
        else:
            refills = ext.setdefault("tier_refills", {})
            refills[str(tier)] = int(refills.get(str(tier), 0)) + 1
    kind = _draw(state, deck)
    deck[kind.value] -= 1
    if tier > 1:
        drawn = ext.setdefault("drawn", {}).setdefault(str(tier), {})
        drawn[kind.value] = int(drawn.get(kind.value, 0)) + 1
    entry: dict[str, Any] = {"kind": kind.value, "at": now_ms, "roll": roll_index(state)}
    if tier > 1:
        entry["tier"] = tier
    ext["hands"].setdefault(str(seat), []).append(entry)
    events: list[Event] = [_hand_event(state, seat, now_ms),
                           DevCardBought(at=now_ms, seat=seat, card=kind, deck_left=sum(deck.values()), tier=tier)]
    if kind is VP and not state.settings.dev_cards.vp_cards_must_be_played:
        events += _score_vp(state, ext, seat, now_ms)
    return events


def _score_vp(state: GameState, ext: dict[str, Any], seat: int, now_ms: int) -> list[Event]:
    pts = state.settings.dev_cards.victory_point_points
    ext["vp_points"][str(seat)] = ext["vp_points"].get(str(seat), 0) + pts
    return _add_points(state, seat, pts, now_ms)


# ---------------------------------------------------------------- play: checks
def _find_card(state: GameState, seat: int, kind: DevCardKind, now_ms: int) -> int:
    """Index in the hand of the oldest playable ``kind`` card."""
    cards = hand(state, seat)
    owned = [i for i, c in enumerate(cards) if c["kind"] == kind.value]
    if not owned:
        raise RuleError("dev.no_card", {"card": kind.value})
    if kind is VP and not state.settings.dev_cards.vp_cards_must_be_played:
        raise RuleError("dev.not_playable", {"card": kind.value})
    ready = [i for i in owned if card_ready(state, cards[i], now_ms)]
    if not ready:
        raise RuleError("dev.too_new", {"card": kind.value})
    if not player_ready(state, seat, now_ms):
        raise RuleError("dev.cooldown", {"card": kind.value})
    return ready[0]


def _robber_hex_ok(state: GameState, h: int) -> bool:
    gb = state.board
    rs = state.settings.robber
    if gb.board.is_land(h):
        return gb.terrain[h] is not Terrain.DESERT or rs.may_enter_desert
    return h in gb.fishing and rs.may_enter_fishing


def knight_reach(state: GameState, kind: DevCardKind) -> int:
    """Hexes a ``kind`` knight may move the robber."""
    cfg = state.settings.dev_cards
    if kind is VETERAN:
        return cfg.veteran_max_distance
    if kind is ELITE:
        return cfg.elite_max_distance
    return state.settings.robber.knight_max_distance


def _knight_target(state: GameState, seat: int, cmd: PlayDevCard) -> tuple[int, int | None]:
    """Checked (hex, victim) of a knight; victim None when there is nobody to rob."""
    start = state.robber_hex
    if start is None or not state.settings.robber.enabled:
        raise RuleError("dev.no_robber", {})
    if cmd.hex is None:
        raise RuleError("dev.need_hex", {})
    board = state.board.board
    h = cmd.hex
    if h >= len(board.hexes) or h == start or not _robber_hex_ok(state, h):
        raise RuleError("dev.bad_hex", {"hex": h})
    from engine.rules import settlers
    if h in settlers.blocked_hexes(state):
        raise RuleError("dev.blocked_by_settler", {"hex": h})
    limit = knight_reach(state, cmd.card)
    if coords.hex_distance(board.hexes[start], board.hexes[h]) > limit:
        raise RuleError("dev.too_far", {"hex": h, "max": limit})
    owners = {b.seat for v in board.hex_vertices[h] if (b := state.buildings.get(v)) is not None}
    near = sorted(s for s in owners if s != seat and not robber.is_spared(state, s))
    if cmd.victim is not None:
        if cmd.victim not in near:
            raise RuleError("dev.bad_victim", {"victim": cmd.victim})
        return h, cmd.victim
    with_cards = [s for s in near if state.player(s).hand_count > 0]
    if len(with_cards) > 1:
        raise RuleError("dev.need_victim", {"choices": with_cards})
    return h, (with_cards[0] if with_cards else None)


def _named(cmd: PlayDevCard, count: int) -> dict[Resource, int]:
    """``cmd.resources`` counted per resource; exactly ``count`` entries."""
    if cmd.resources is None or len(cmd.resources) != count:
        raise RuleError("dev.need_resources", {"count": count})
    want: dict[Resource, int] = {}
    for r in cmd.resources:
        want[r] = want.get(r, 0) + 1
    return want


def _plenty_take(state: GameState, cmd: PlayDevCard) -> dict[Resource, int]:
    """Year of plenty or bountiful harvest: the named resources, if the bank has them."""
    cfg = state.settings.dev_cards
    if cmd.card is HARVEST:
        want = _named(cmd, cfg.harvest_cards)
        if want.get(Resource.FISH, 0) > cfg.harvest_max_fish:
            raise RuleError("dev.too_much_fish", {"max": cfg.harvest_max_fish})
    else:
        want = _named(cmd, cfg.year_of_plenty_cards)
    missing = {r.value: n - state.bank[r] for r, n in want.items() if n > state.bank[r]}
    if missing:
        raise RuleError("dev.bank_short", {"missing": missing})
    return {r: want[r] for r in Resource if r in want}


def _architect_discount(state: GameState, cmd: PlayDevCard) -> dict[Resource, int]:
    want = _named(cmd, state.settings.dev_cards.architect_discount)
    if Resource.FISH in want:
        raise RuleError("dev.no_fish_discount", {})
    return {r: want[r] for r in Resource if r in want}


# ---------------------------------------------------------------- play
@command_handler("play_dev_card")
def on_play(state: GameState, seat: int, cmd: PlayDevCard, now_ms: int) -> list[Event]:
    _check_active(state, seat)
    kind = cmd.card
    index = _find_card(state, seat, kind, now_ms)
    target: tuple[int, int | None] | None = _knight_target(state, seat, cmd) if kind in KNIGHT_KINDS else None
    plenty = _plenty_take(state, cmd) if kind in (PLENTY, HARVEST) else None
    discount = _architect_discount(state, cmd) if kind is ARCHITECT else None
    if kind is MONOPOLY and cmd.resource is None:
        raise RuleError("dev.need_resource", {})
    # ---- validated; mutate from here on
    ext = _ext(state)
    ext["hands"][str(seat)].pop(index)
    played = ext["played"].setdefault(str(seat), {})
    played[kind.value] = played.get(kind.value, 0) + 1
    ext["last_play"][str(seat)] = {"at": now_ms, "roll": roll_index(state)}
    if kind in KNIGHT_KINDS:
        assert target is not None
        return _play_knight(state, seat, kind, target, now_ms)
    if kind is VP:
        return [DevCardPlayed(at=now_ms, seat=seat, card=kind)] + _score_vp(state, ext, seat, now_ms)
    if kind in (ROADS, CAUSEWAY):
        cfg = state.settings.dev_cards
        n = cfg.road_building_roads if kind is ROADS else cfg.causeway_roads
        ext["free_roads"][str(seat)] = ext["free_roads"].get(str(seat), 0) + n
        return [DevCardPlayed(at=now_ms, seat=seat, card=kind, roads=n)]
    if kind in EFFECT_ROLLS:
        n = int(getattr(state.settings.dev_cards, EFFECT_ROLLS[kind]))
        extra = {} if discount is None else {"resources": [r.value for r, k in discount.items() for _ in range(k)]}
        dev_effects.add(state, seat, kind, n, **extra)
        return [DevCardPlayed(at=now_ms, seat=seat, card=kind, rolls=dev_effects.left(state, seat, kind),
                              discount=discount or {})]
    if kind is TRIBUTE:
        return _play_tribute(state, seat, now_ms)
    if kind in (PLENTY, HARVEST):
        assert plenty is not None
        p = state.player(seat)
        for r, n in plenty.items():
            state.bank[r] -= n
            p.hand[r] += n
        return [DevCardPlayed(at=now_ms, seat=seat, card=kind, took=plenty), _hand_event(state, seat, now_ms)]
    return _play_monopoly(state, seat, cmd.resource, now_ms)  # type: ignore[arg-type]


def knight_steal(state: GameState, kind: DevCardKind, victim: int) -> int:
    """Cards a ``kind`` knight steals from ``victim``: veteran and elite knights take more
    from a player holding over their robber card limit."""
    if kind is KNIGHT:
        return state.settings.robber.knight_steal
    cfg = state.settings.dev_cards
    limit = state.settings.robber.card_limit + age_state.card_limit_bonus(state, victim)
    return cfg.strong_knight_hoard_steal if state.player(victim).hand_count > limit else cfg.strong_knight_steal


def _play_knight(state: GameState, seat: int, kind: DevCardKind, target: tuple[int, int | None],
                 now_ms: int) -> list[Event]:
    h, victim = target
    start = state.robber_hex
    state.robber_hex = h
    stolen = 0
    hands: list[Event] = []
    if victim is not None:
        lost = robber.steal_random(state, victim, knight_steal(state, kind, victim))
        p = state.player(seat)
        for r, n in lost.items():
            p.hand[r] += n
        stolen = sum(lost.values())
        if stolen:
            hands = [_hand_event(state, victim, now_ms), _hand_event(state, seat, now_ms)]
    events: list[Event] = [DevCardPlayed(at=now_ms, seat=seat, card=kind, hex=h, victim=victim, stolen=stolen),
                           RobberMoved(at=now_ms, from_hex=start, to_hex=h), *hands]
    return events + _update_army(state, now_ms)


def _play_monopoly(state: GameState, seat: int, res: Resource, now_ms: int) -> list[Event]:
    me = state.player(seat)
    taken: dict[int, int] = {}
    for p in state.players:
        if p.seat != seat and p.hand[res] > 0 and not robber.is_spared(state, p.seat):
            taken[p.seat] = p.hand[res]
            me.hand[res] += p.hand[res]
            p.hand[res] = 0
    events: list[Event] = [DevCardPlayed(at=now_ms, seat=seat, card=MONOPOLY, resource=res, taken=taken)]
    return events + [_hand_event(state, s, now_ms) for s in [*taken, seat]]


def _play_tribute(state: GameState, seat: int, now_ms: int) -> list[Event]:
    """Each player with more points than ``seat`` (not spared, not resigned) gives
    ``dev_cards.tribute_cards`` random cards (fewer if they hold fewer)."""
    me = state.player(seat)
    n = state.settings.dev_cards.tribute_cards
    taken: dict[int, int] = {}
    for p in state.players:
        if p.seat == seat or p.resigned or p.points <= me.points or robber.is_spared(state, p.seat):
            continue
        lost = robber.steal_random(state, p.seat, n)
        for r, k in lost.items():
            me.hand[r] += k
        if lost:
            taken[p.seat] = sum(lost.values())
    events: list[Event] = [DevCardPlayed(at=now_ms, seat=seat, card=TRIBUTE, taken=taken)]
    return events + [_hand_event(state, s, now_ms) for s in [*taken, seat] if taken]


def _update_army(state: GameState, now_ms: int) -> list[Event]:
    ext = _ext(state)
    cfg = state.settings.victory.largest_army
    counts = knights(state)
    old = ext["army"]
    new = longest_road.next_holder(old, counts, cfg.min)
    ext["army"] = new
    events: list[Event] = [LargestArmy(at=now_ms, seat=new, previous=old, knights=counts)]
    if new != old:
        if old is not None:
            events += _add_points(state, old, -cfg.points, now_ms)
        if new is not None and state.phase != "finished":
            events += _add_points(state, new, cfg.points, now_ms)
    return events


# ---------------------------------------------------------------- projection
def state_view(state: GameState, viewer: int | None) -> dict[str, Any]:
    """``state.dev_cards`` of the protocol: deck size, Largest Army, per player the
    knights played, the effects on (kind -> rolls left, public) and the card count
    (``visibility.dev_cards``; with advanced developments also per tier, and every deck's size); for the viewer, their
    cards with when they were bought (``at``, ``roll``: the client works out which are
    playable, as the dice roll on), their last play and their free roads."""
    vis = state.settings.visibility.dev_cards
    players: dict[str, Any] = {}
    for p in state.players:
        cards = hand(state, p.seat)
        d: dict[str, Any] = {"knights": knights(state)[p.seat], "effects": dev_effects.effects_of(state, p.seat)}
        if p.seat == viewer:
            d["cards"] = [dict(c) for c in cards]
            d["last_play"] = _view(state).get("last_play", {}).get(str(p.seat))
            d["free_roads"] = placement.free_roads(state, p.seat)
        elif vis is InfoVisibility.OPEN:
            d["cards"] = [{"kind": c["kind"]} for c in cards]
        if p.seat == viewer or vis is not InfoVisibility.HIDDEN:
            d["count"] = len(cards)
            if tiers_enabled(state):
                d["tiers"] = {str(t): sum(1 for c in cards if c.get("tier", 1) == t) for t in TIERS}
        players[str(p.seat)] = d
    view: dict[str, Any] = {"deck_left": sum(deck_left(state).values()), "army": army_holder(state), "players": players}
    if tiers_enabled(state):
        view["decks_left"] = {str(t): sum(deck_left(state, t).values()) for t in TIERS}
    return view


register_state_extension("dev_cards", state_view)
