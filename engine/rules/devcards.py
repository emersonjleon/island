"""Development cards and Largest Army (stage 2).

* ``buy_dev_card``: a player whose setup is done pays ``economy.costs.dev_card`` to
  the bank and draws a random card from what is left of ``dev_cards.deck``
  (``state.rng``, one draw per purchase). Emits ``Hand`` then ``DevCardBought``.
  With ``vp_cards_must_be_played`` off a victory point card counts at once.
* ``play_dev_card``: the card must be in the hand and playable:

  - ``cooldown == "per_roll"``: bought before the latest dice roll, and no card
    played since that roll (one card per roll interval, victory points included);
  - ``cooldown == "ms"``: ``cooldown_ms`` passed since it was bought and since the
    player's last play.

  Cards: **knight** moves the robber to ``hex`` (a legal robber hex at distance
  1..``robber.knight_max_distance``) and steals ``robber.knight_steal`` random cards
  from ``victim``, a player with a building on that hex (the card's player picks;
  a single possible victim is picked for them); **victory point** adds
  ``dev_cards.victory_point_points``; **road building** gives
  ``dev_cards.road_building_roads`` free roads (built normally, at no cost; see
  :func:`engine.rules.placement.build_cost`); **year of plenty** takes
  ``dev_cards.year_of_plenty_cards`` named resources from the bank; **monopoly**
  takes every card of one resource from the other players.

  Emits ``DevCardPlayed`` (public) and the ``RobberMoved`` / ``Hand`` / ``Points`` /
  ``LargestArmy`` events that follow from it.

Largest Army (``victory.largest_army``): same award rules as Longest Road
(:func:`engine.rules.longest_road.next_holder`): at least ``min`` knights played,
the holder keeps it on a tie, a strictly larger army takes it.

State, in ``state.ext["devcards"]`` (JSON-safe, string seat keys):
``deck`` (kind -> cards left), ``hands`` (seat -> [{kind, at, roll}]),
``played`` (seat -> {kind: n}), ``last_play`` (seat -> {at, roll}),
``free_roads`` (seat -> n), ``vp_points`` (seat -> points from victory point
cards), ``army`` (holder seat or None).

Reject codes: ``dev.setup_not_done``, ``dev.deck_empty``, ``dev.cannot_afford``
{missing}, ``dev.no_card`` {card}, ``dev.too_new`` {card}, ``dev.cooldown`` {card},
``dev.not_playable`` {card}, ``dev.no_robber``, ``dev.need_hex``, ``dev.bad_hex``
{hex}, ``dev.too_far`` {hex, max}, ``dev.need_victim`` {choices}, ``dev.bad_victim``
{victim}, ``dev.need_resources`` {count}, ``dev.bank_short`` {missing},
``dev.need_resource``.
"""
from __future__ import annotations

from typing import Any

from engine.board import coords
from engine.commands import BuyDevCard, PlayDevCard
from engine.errors import RuleError
from engine.events import DevCardBought, DevCardPlayed, Event, Hand, LargestArmy, Points, RobberMoved
from engine.game import command_handler
from engine.rules import longest_road, placement, robber, victory
from engine.settings.enums import Cooldown, DevCardKind, InfoVisibility, Resource, Terrain
from engine.state import GameState
from engine.views import register_state_extension

__all__ = [
    "EXT_KEY", "deck_left", "hand", "knights", "army_holder", "vp_points", "roll_index", "card_ready",
    "player_ready", "playable", "on_buy", "on_play",
]

EXT_KEY = "devcards"
KNIGHT, VP, ROADS, PLENTY, MONOPOLY = (DevCardKind.KNIGHT, DevCardKind.VICTORY_POINT,
                                       DevCardKind.ROAD_BUILDING, DevCardKind.YEAR_OF_PLENTY,
                                       DevCardKind.MONOPOLY)


# ---------------------------------------------------------------- read-only
def _view(state: GameState) -> dict[str, Any]:
    return state.ext.get(EXT_KEY, {})


def deck_left(state: GameState) -> dict[str, int]:
    deck = _view(state).get("deck")
    if deck is None:
        return {k.value: n for k, n in state.settings.dev_cards.deck.items()}
    return dict(deck)


def hand(state: GameState, seat: int) -> list[dict[str, Any]]:
    return list(_view(state).get("hands", {}).get(str(seat), []))


def knights(state: GameState) -> dict[int, int]:
    played = _view(state).get("played", {})
    return {p.seat: int(played.get(str(p.seat), {}).get(KNIGHT.value, 0)) for p in state.players}


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
    if p.points >= state.settings.victory.target:
        victory.finish(state, seat, now_ms)
    return [Points(at=now_ms, seat=seat, points=p.points)]


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


@command_handler("buy_dev_card")
def on_buy(state: GameState, seat: int, cmd: BuyDevCard, now_ms: int) -> list[Event]:
    _check_active(state, seat)
    if sum(deck_left(state).values()) <= 0:
        raise RuleError("dev.deck_empty", {})
    p = state.player(seat)
    cost = {r: int(n) for r, n in state.settings.economy.costs.dev_card.items()}
    missing = placement.missing_resources(p.hand, {r: cost.get(r, 0) for r in Resource})
    if missing:
        raise RuleError("dev.cannot_afford", {"missing": missing})
    # ---- validated; mutate from here on
    ext = _ext(state)
    for r, n in cost.items():
        p.hand[r] -= n
        state.bank[r] += n
    kind = _draw(state, ext["deck"])
    ext["deck"][kind.value] -= 1
    ext["hands"].setdefault(str(seat), []).append({"kind": kind.value, "at": now_ms, "roll": roll_index(state)})
    events: list[Event] = [_hand_event(state, seat, now_ms),
                           DevCardBought(at=now_ms, seat=seat, card=kind, deck_left=sum(ext["deck"].values()))]
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
    limit = state.settings.robber.knight_max_distance
    if coords.hex_distance(board.hexes[start], board.hexes[h]) > limit:
        raise RuleError("dev.too_far", {"hex": h, "max": limit})
    near = sorted({b.seat for v in board.hex_vertices[h] if (b := state.buildings.get(v)) is not None} - {seat})
    if cmd.victim is not None:
        if cmd.victim not in near:
            raise RuleError("dev.bad_victim", {"victim": cmd.victim})
        return h, cmd.victim
    with_cards = [s for s in near if state.player(s).hand_count > 0]
    if len(with_cards) > 1:
        raise RuleError("dev.need_victim", {"choices": with_cards})
    return h, (with_cards[0] if with_cards else None)


def _plenty_take(state: GameState, cmd: PlayDevCard) -> dict[Resource, int]:
    count = state.settings.dev_cards.year_of_plenty_cards
    if cmd.resources is None or len(cmd.resources) != count:
        raise RuleError("dev.need_resources", {"count": count})
    want: dict[Resource, int] = {}
    for r in cmd.resources:
        want[r] = want.get(r, 0) + 1
    missing = {r.value: n - state.bank[r] for r, n in want.items() if n > state.bank[r]}
    if missing:
        raise RuleError("dev.bank_short", {"missing": missing})
    return {r: want[r] for r in Resource if r in want}


# ---------------------------------------------------------------- play
@command_handler("play_dev_card")
def on_play(state: GameState, seat: int, cmd: PlayDevCard, now_ms: int) -> list[Event]:
    _check_active(state, seat)
    kind = cmd.card
    index = _find_card(state, seat, kind, now_ms)
    target: tuple[int, int | None] | None = _knight_target(state, seat, cmd) if kind is KNIGHT else None
    plenty = _plenty_take(state, cmd) if kind is PLENTY else None
    if kind is MONOPOLY and cmd.resource is None:
        raise RuleError("dev.need_resource", {})
    # ---- validated; mutate from here on
    ext = _ext(state)
    ext["hands"][str(seat)].pop(index)
    played = ext["played"].setdefault(str(seat), {})
    played[kind.value] = played.get(kind.value, 0) + 1
    ext["last_play"][str(seat)] = {"at": now_ms, "roll": roll_index(state)}
    if kind is KNIGHT:
        assert target is not None
        return _play_knight(state, seat, target, now_ms)
    if kind is VP:
        return [DevCardPlayed(at=now_ms, seat=seat, card=kind)] + _score_vp(state, ext, seat, now_ms)
    if kind is ROADS:
        n = state.settings.dev_cards.road_building_roads
        ext["free_roads"][str(seat)] = ext["free_roads"].get(str(seat), 0) + n
        return [DevCardPlayed(at=now_ms, seat=seat, card=kind, roads=n)]
    if kind is PLENTY:
        assert plenty is not None
        p = state.player(seat)
        for r, n in plenty.items():
            state.bank[r] -= n
            p.hand[r] += n
        return [DevCardPlayed(at=now_ms, seat=seat, card=kind, took=plenty), _hand_event(state, seat, now_ms)]
    return _play_monopoly(state, seat, cmd.resource, now_ms)  # type: ignore[arg-type]


def _play_knight(state: GameState, seat: int, target: tuple[int, int | None], now_ms: int) -> list[Event]:
    h, victim = target
    start = state.robber_hex
    state.robber_hex = h
    stolen = 0
    hands: list[Event] = []
    if victim is not None:
        lost = robber.steal_random(state, victim, state.settings.robber.knight_steal)
        p = state.player(seat)
        for r, n in lost.items():
            p.hand[r] += n
        stolen = sum(lost.values())
        if stolen:
            hands = [_hand_event(state, victim, now_ms), _hand_event(state, seat, now_ms)]
    events: list[Event] = [DevCardPlayed(at=now_ms, seat=seat, card=KNIGHT, hex=h, victim=victim, stolen=stolen),
                           RobberMoved(at=now_ms, from_hex=start, to_hex=h), *hands]
    return events + _update_army(state, now_ms)


def _play_monopoly(state: GameState, seat: int, res: Resource, now_ms: int) -> list[Event]:
    me = state.player(seat)
    taken: dict[int, int] = {}
    for p in state.players:
        if p.seat != seat and p.hand[res] > 0:
            taken[p.seat] = p.hand[res]
            me.hand[res] += p.hand[res]
            p.hand[res] = 0
    events: list[Event] = [DevCardPlayed(at=now_ms, seat=seat, card=MONOPOLY, resource=res, taken=taken)]
    return events + [_hand_event(state, s, now_ms) for s in [*taken, seat]]


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
    knights played and the card count (``visibility.dev_cards``); for the viewer, their
    cards with when they were bought (``at``, ``roll``: the client works out which are
    playable, as the dice roll on), their last play and their free roads."""
    vis = state.settings.visibility.dev_cards
    players: dict[str, Any] = {}
    for p in state.players:
        cards = hand(state, p.seat)
        d: dict[str, Any] = {"knights": knights(state)[p.seat]}
        if p.seat == viewer:
            d["cards"] = [dict(c) for c in cards]
            d["last_play"] = _view(state).get("last_play", {}).get(str(p.seat))
            d["free_roads"] = placement.free_roads(state, p.seat)
        elif vis is InfoVisibility.OPEN:
            d["cards"] = [{"kind": c["kind"]} for c in cards]
        if p.seat == viewer or vis is not InfoVisibility.HIDDEN:
            d["count"] = len(cards)
        players[str(p.seat)] = d
    return {"deck_left": sum(deck_left(state).values()), "army": army_holder(state), "players": players}


register_state_extension("dev_cards", state_view)
