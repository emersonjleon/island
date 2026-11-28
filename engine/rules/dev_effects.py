"""Development effects that last a few dice rolls (advanced developments, ages).

Fishing fleet, merchant, great market and architect put an effect on their player,
kept in ``state.ext["devcards"]["effects"]`` as seat -> kind -> ``{"until": roll}``
(the architect also keeps the ``resources`` it takes off). ``roll`` counts dice rolls
(``len(state.dice_history)``). An effect played at roll ``r`` for ``n`` rolls has
``until = r + n``: it shows ``until - rolls`` rolls left and is on while that is
above 0, so it covers the rest of the current roll and the next ``n - 1`` ones. The
fishing fleet's extra fish come with each of the next ``n`` rolls (``until >= roll``
when that roll produces). Playing the same card again adds ``n`` rolls, up to
``dev_cards.effect_max_pct`` percent of ``n`` from now.

This module only reads and writes ``ext``; it imports no other rule, so trade,
production and building can ask it without import cycles.
"""
from __future__ import annotations

from typing import Any

from engine.settings.enums import DevCardKind, Resource
from engine.state import GameState

__all__ = ["EXT_KEY", "rolls", "left", "active", "effects_of", "add", "fleet_fish", "market_ratio",
           "architect_discount", "use_architect"]

EXT_KEY = "devcards"
FLEET, MERCHANT, GREAT_MARKET, ARCHITECT = (DevCardKind.FISHING_FLEET, DevCardKind.MERCHANT,
                                            DevCardKind.GREAT_MARKET, DevCardKind.ARCHITECT)
PERCENT = 100


def rolls(state: GameState) -> int:
    return len(state.dice_history)


def _effects(state: GameState, seat: int) -> dict[str, Any]:
    return state.ext.get(EXT_KEY, {}).get("effects", {}).get(str(seat), {})


def left(state: GameState, seat: int, kind: DevCardKind) -> int:
    """Rolls left of ``seat``'s ``kind`` effect (0: off)."""
    e = _effects(state, seat).get(kind.value)
    return max(0, int(e["until"]) - rolls(state)) if e else 0


def active(state: GameState, seat: int, kind: DevCardKind) -> bool:
    return left(state, seat, kind) > 0


def effects_of(state: GameState, seat: int) -> dict[str, int]:
    """Kind -> rolls left, for the effects of ``seat`` that are on."""
    return {k: n for k in _effects(state, seat) if (n := left(state, seat, DevCardKind(k))) > 0}


def add(state: GameState, seat: int, kind: DevCardKind, n: int, **extra: Any) -> int:
    """Start (or lengthen) ``seat``'s ``kind`` effect by ``n`` rolls; returns its new ``until``."""
    now = rolls(state)
    effects = state.ext.setdefault(EXT_KEY, {}).setdefault("effects", {}).setdefault(str(seat), {})
    old = effects.get(kind.value)
    start = max(int(old["until"]), now) if old else now
    cap = now + n * state.settings.dev_cards.effect_max_pct // PERCENT
    until = min(start + n, cap)
    effects[kind.value] = {"until": until, **extra}
    return until


def fleet_fish(state: GameState, seat: int) -> int:
    """Extra fish per own building on a fishing ground producing at the current roll."""
    e = _effects(state, seat).get(FLEET.value)
    if e and int(e["until"]) >= rolls(state):
        return state.settings.dev_cards.fleet_fish
    return 0


def market_ratio(state: GameState, seat: int) -> int | None:
    """The bank ratio a merchant or great market gives ``seat`` now, else None."""
    if active(state, seat, MERCHANT) or active(state, seat, GREAT_MARKET):
        return state.settings.dev_cards.market_ratio
    return None


def architect_discount(state: GameState, seat: int) -> dict[Resource, int]:
    """Cards taken off ``seat``'s next city or megacity (empty when no architect is on)."""
    if not active(state, seat, ARCHITECT):
        return {}
    out: dict[Resource, int] = {}
    for key in _effects(state, seat)[ARCHITECT.value].get("resources", []):
        r = Resource(key)
        out[r] = out.get(r, 0) + 1
    return out


def use_architect(state: GameState, seat: int) -> None:
    """The discount was used (a city or megacity started): the architect ends."""
    _effects(state, seat).pop(ARCHITECT.value, None)
