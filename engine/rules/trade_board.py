"""Trade board (stage 2): players post offers at any time and anyone can accept.

* ``post_offer {give, get}``: needs ``trading.player_trades``, a finished setup and
  the ``give`` cards in hand right now (they are not set aside: the hand is checked
  again when someone accepts). At most ``trading.max_open_offers`` open offers per
  player. With ``trading.offer_expiry_ms`` the offer comes down by itself after that
  long. Emits ``OfferPosted``.
* ``cancel_offer {offer}``: the poster takes their own offer down. Emits
  ``OfferClosed`` (``"cancelled"``).
* ``accept_offer {offer}``: another player whose setup is done takes the offer; both
  hands must hold their side at that moment. The cards move at once and the offer
  comes down. Emits ``OfferClosed`` (``"accepted"``, ``by``) and both ``Hand`` events.
* A player who resigns loses their open offers (``"resigned"``, after the step).

Offers are public (``visibility.trade_offers = public``; private offers come later).

State, in ``state.ext["trade_board"]`` (JSON-safe): ``next`` (next offer id) and
``offers`` (id as a string -> {seat, give, get, at, expires_at, timer}).

Reject codes: ``offer.disabled``, ``offer.setup_not_done``, ``offer.too_many`` {max},
``offer.cannot_afford`` {missing}, ``offer.not_found`` {offer}, ``offer.not_yours``
{offer}, ``offer.own`` {offer}, ``offer.poster_short`` {missing}.
"""
from __future__ import annotations

from typing import Any

from engine.commands import AcceptOffer, CancelOffer, PostOffer
from engine.errors import RuleError
from engine.events import Event, Hand, OfferClosed, OfferPosted
from engine.game import after_step, command_handler, timer_handler
from engine.scheduler import Timer
from engine.settings.enums import Resource
from engine.state import GameState
from engine.views import register_state_extension

__all__ = ["EXT_KEY", "TIMER_OFFER_EXPIRE", "offers", "open_count", "missing", "on_post", "on_cancel",
           "on_accept"]

EXT_KEY = "trade_board"
TIMER_OFFER_EXPIRE = "offer_expire"   # payload {"offer"}


# ---------------------------------------------------------------- read-only
def offers(state: GameState) -> dict[int, dict[str, Any]]:
    """Open offers by id: {seat, give, get, at, expires_at} with ``Resource`` keys."""
    raw = state.ext.get(EXT_KEY, {}).get("offers", {})
    return {int(k): _decode(o) for k, o in sorted(raw.items(), key=lambda kv: int(kv[0]))}


def open_count(state: GameState, seat: int) -> int:
    return sum(1 for o in offers(state).values() if o["seat"] == seat)


def missing(state: GameState, seat: int, need: dict[Resource, int]) -> dict[str, int]:
    """What ``seat``'s hand lacks to pay ``need`` (empty when they can)."""
    hand = state.player(seat).hand
    return {r.value: n - hand[r] for r, n in need.items() if hand[r] < n}


def _decode(o: dict[str, Any]) -> dict[str, Any]:
    return {"seat": o["seat"], "give": {Resource(r): n for r, n in o["give"].items()},
            "get": {Resource(r): n for r, n in o["get"].items()}, "at": o["at"],
            "expires_at": o.get("expires_at")}


# ---------------------------------------------------------------- mutable
def _ext(state: GameState) -> dict[str, Any]:
    ext = state.ext.setdefault(EXT_KEY, {})
    ext.setdefault("next", 0)
    ext.setdefault("offers", {})
    return ext


def _find(state: GameState, offer_id: int) -> dict[str, Any]:
    o = offers(state).get(offer_id)
    if o is None:
        raise RuleError("offer.not_found", {"offer": offer_id})
    return o


def _close(state: GameState, offer_id: int, reason: str, now_ms: int, by: int | None = None) -> OfferClosed:
    raw = _ext(state)["offers"].pop(str(offer_id))
    state.timers.cancel(raw.get("timer"))
    o = _decode(raw)
    return OfferClosed(at=now_ms, offer=offer_id, seat=o["seat"], reason=reason, by=by,  # type: ignore[arg-type]
                       give=o["give"], get=o["get"])


@command_handler("post_offer")
def on_post(state: GameState, seat: int, cmd: PostOffer, now_ms: int) -> list[Event]:
    cfg = state.settings.trading
    if not cfg.player_trades:
        raise RuleError("offer.disabled")
    if not state.player(seat).setup_done:
        raise RuleError("offer.setup_not_done")
    if open_count(state, seat) >= cfg.max_open_offers:
        raise RuleError("offer.too_many", {"max": cfg.max_open_offers})
    short = missing(state, seat, dict(cmd.give))
    if short:
        raise RuleError("offer.cannot_afford", {"missing": short})
    ext = _ext(state)
    offer_id = ext["next"]
    ext["next"] = offer_id + 1
    expires = None if cfg.offer_expiry_ms is None else now_ms + cfg.offer_expiry_ms
    timer = None if expires is None else state.timers.schedule(expires, TIMER_OFFER_EXPIRE, {"offer": offer_id})
    ext["offers"][str(offer_id)] = {
        "seat": seat, "give": {r.value: n for r, n in cmd.give.items()},
        "get": {r.value: n for r, n in cmd.get.items()}, "at": now_ms, "expires_at": expires, "timer": timer,
    }
    return [OfferPosted(at=now_ms, offer=offer_id, seat=seat, give=dict(cmd.give), get=dict(cmd.get),
                        expires_at=expires)]


@command_handler("cancel_offer")
def on_cancel(state: GameState, seat: int, cmd: CancelOffer, now_ms: int) -> list[Event]:
    if _find(state, cmd.offer)["seat"] != seat:
        raise RuleError("offer.not_yours", {"offer": cmd.offer})
    return [_close(state, cmd.offer, "cancelled", now_ms)]


@command_handler("accept_offer")
def on_accept(state: GameState, seat: int, cmd: AcceptOffer, now_ms: int) -> list[Event]:
    o = _find(state, cmd.offer)
    poster = o["seat"]
    if poster == seat:
        raise RuleError("offer.own", {"offer": cmd.offer})
    if not state.player(seat).setup_done:
        raise RuleError("offer.setup_not_done")
    short = missing(state, seat, o["get"])
    if short:
        raise RuleError("offer.cannot_afford", {"missing": short})
    short = missing(state, poster, o["give"])
    if short:
        raise RuleError("offer.poster_short", {"missing": short})
    mine, theirs = state.player(seat).hand, state.player(poster).hand
    for r, n in o["give"].items():
        theirs[r] -= n
        mine[r] += n
    for r, n in o["get"].items():
        mine[r] -= n
        theirs[r] += n
    return [_close(state, cmd.offer, "accepted", now_ms, by=seat),
            Hand(at=now_ms, seat=poster, hand=dict(theirs)), Hand(at=now_ms, seat=seat, hand=dict(mine))]


@timer_handler(TIMER_OFFER_EXPIRE)
def on_expire(state: GameState, timer: Timer, now_ms: int) -> list[Event]:
    offer_id = timer.payload["offer"]
    if str(offer_id) not in state.ext.get(EXT_KEY, {}).get("offers", {}):
        return []
    return [_close(state, offer_id, "expired", now_ms)]


@after_step(order=200)
def drop_resigned(state: GameState, now_ms: int) -> list[Event]:
    """Offers of players who resigned come down."""
    gone = [i for i, o in offers(state).items() if state.player(o["seat"]).resigned]
    return [_close(state, i, "resigned", now_ms) for i in gone]


# ---------------------------------------------------------------- projection
def state_view(state: GameState, viewer: int | None) -> dict[str, Any]:
    """``state.trade_board`` of the protocol: the open offers, oldest first."""
    return {"offers": [
        {"id": i, "seat": o["seat"], "give": {r.value: n for r, n in o["give"].items()},
         "get": {r.value: n for r, n in o["get"].items()}, "at": o["at"], "expires_at": o["expires_at"]}
        for i, o in offers(state).items()
    ]}


register_state_extension("trade_board", state_view)
