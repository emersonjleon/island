"""Trading (WP7): bank 4:1 and harbor ratios.

``@command_handler("bank_trade")`` (:func:`on_bank_trade`): the player gives
``ratio x n`` cards of one resource and gets ``n`` cards of another from the bank.
The ratio is the best (lowest) of ``settings.economy.trade.bank_ratio`` and, when
``settings.trading.harbor_trade`` is on, the harbors on which the player owns a
finished settlement or city (``state.board.vertex_harbor``): a generic harbor gives
``settings.board.harbors.generic_ratio`` for any resource, a specific harbor
``specific_ratio`` for its own resource only. See :func:`best_ratio`.

Reject codes (checked in this order, nothing changes on reject):

* ``trade.setup_forbidden`` -- the player's own setup is not done and
  ``settings.setup.bank_trade_during_setup`` is off;
* ``trade.same_resource`` -- give and get name the same resource (normally
  caught by the command schema already);
* ``trade.bad_ratio`` -- ``give != ratio x get``; params ``{resource, ratio, give, get}``;
* ``trade.cannot_afford`` -- the hand lacks the given cards; params ``{resource, have, need}``;
* ``trade.bank_empty`` -- the bank lacks the requested cards; params ``{resource, have, need}``.

Events: ``Traded`` (public; ``via`` is ``"harbor"`` when a harbor beat the bank
ratio) then the player's private ``Hand``.
"""
from __future__ import annotations

from typing import Literal

from engine.commands import BankTrade
from engine.errors import RuleError
from engine.events import Event, Hand, Traded
from engine.game import command_handler
from engine.settings.enums import Resource
from engine.state import GameState

__all__ = ["best_ratio", "on_bank_trade", "owned_harbors"]


def owned_harbors(state: GameState, seat: int) -> list[int]:
    """Indexes into ``state.board.harbors`` where ``seat`` has a finished building."""
    vh = state.board.vertex_harbor
    found: set[int] = set()
    for v, b in state.buildings.items():
        if b.seat == seat and vh[v] is not None:
            found.add(vh[v])  # type: ignore[arg-type]
    return sorted(found)


def best_ratio(state: GameState, seat: int, give: Resource) -> tuple[int, Literal["bank", "harbor"]]:
    """``(ratio, via)``: the best ratio ``seat`` gets when giving ``give``."""
    s = state.settings
    ratio: int = s.economy.trade.bank_ratio
    via: Literal["bank", "harbor"] = "bank"
    if not s.trading.harbor_trade:
        return ratio, via
    hs = s.board.harbors
    for i in owned_harbors(state, seat):
        harbor = state.board.harbors[i]
        if harbor.resource is None:
            r = hs.generic_ratio
        elif harbor.resource == give:
            r = hs.specific_ratio
        else:
            continue
        if r < ratio:
            ratio, via = r, "harbor"
    return ratio, via


@command_handler("bank_trade")
def on_bank_trade(state: GameState, seat: int, cmd: BankTrade, now_ms: int) -> list[Event]:
    player = state.player(seat)
    if not player.setup_done and not state.settings.setup.bank_trade_during_setup:
        raise RuleError("trade.setup_forbidden")
    (give_res, give_n), = cmd.give.items()
    (get_res, get_n), = cmd.get.items()
    if give_res == get_res:
        raise RuleError("trade.same_resource", {"resource": give_res.value})
    ratio, via = best_ratio(state, seat, give_res)
    if give_n != ratio * get_n:
        raise RuleError("trade.bad_ratio", {"resource": give_res.value, "ratio": ratio, "give": give_n,
                                            "get": get_n})
    if player.hand[give_res] < give_n:
        raise RuleError("trade.cannot_afford", {"resource": give_res.value, "have": player.hand[give_res],
                                                "need": give_n})
    if state.bank[get_res] < get_n:
        raise RuleError("trade.bank_empty", {"resource": get_res.value, "have": state.bank[get_res],
                                             "need": get_n})
    player.hand[give_res] -= give_n
    state.bank[give_res] += give_n
    state.bank[get_res] -= get_n
    player.hand[get_res] += get_n
    return [
        Traded(at=now_ms, seat=seat, give={give_res: give_n}, get={get_res: get_n}, ratio=ratio, via=via),
        Hand(at=now_ms, seat=seat, hand=dict(player.hand)),
    ]
