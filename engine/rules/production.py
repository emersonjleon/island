"""Production (WP7): resources for a roll, bank shortage rule, fishing grounds.

:func:`produce` is called by dice for every roll that is not the robber roll:

* every hex of ``state.board.producing_hexes(roll)`` (land hexes and fishing
  grounds) except ``state.robber_hex`` pays each adjacent finished building
  ``settings.economy.production_per.settlement`` / ``.city`` cards of its resource;
* classic shortage rule, per resource: if the bank cannot pay everyone owed that
  resource, nobody gets it, unless only one player is owed it, who then gets what
  is left;
* one ``Produced`` event (``gains``: seat -> non-zero resources received;
  ``skipped``: resource -> reason, see ``SKIP_*``), then one private ``Hand`` per
  seat that received something, in seat order. ``Produced`` is emitted even when
  nothing is produced.
"""
from __future__ import annotations

from engine.events import Event, Hand, Produced
from engine.settings.enums import BuildKind, Resource
from engine.state import GameState

__all__ = ["SKIP_BANK_PARTIAL", "SKIP_BANK_SHORTAGE", "SKIP_ROBBER", "owed_by_resource", "pay_out", "produce"]

SKIP_ROBBER = "robber"
"""The robber's hex would have paid this resource to someone (and nothing overrode it)."""
SKIP_BANK_SHORTAGE = "bank_shortage"
"""The bank could not pay everyone owed this resource, so nobody got it."""
SKIP_BANK_PARTIAL = "bank_partial"
"""Only one player was owed this resource and got less than owed (what the bank had left)."""

Owed = dict[Resource, dict[int, int]]


def _amount(state: GameState, kind: BuildKind) -> int:
    per = state.settings.economy.production_per
    if kind is BuildKind.SETTLEMENT:
        return per.settlement
    if kind is BuildKind.CITY:
        return per.city
    return 0


def _hex_owed(state: GameState, hex_id: int) -> dict[int, int]:
    """seat -> cards one hex pays its adjacent buildings (zero amounts dropped)."""
    out: dict[int, int] = {}
    for v in state.board.board.hex_vertices[hex_id]:
        b = state.buildings.get(v)
        if b is None:
            continue
        n = _amount(state, b.kind)
        if n > 0:
            out[b.seat] = out.get(b.seat, 0) + n
    return out


def owed_by_resource(state: GameState, roll: int) -> tuple[Owed, set[Resource]]:
    """``(owed, robbed)``: resource -> seat -> cards owed for ``roll``, and the resources
    the robber's hex blocked for at least one building."""
    board = state.board
    owed: Owed = {}
    robbed: set[Resource] = set()
    for h in board.producing_hexes(roll):
        res = board.hex_resource(h)
        if res is None:
            continue
        per_seat = _hex_owed(state, h)
        if not per_seat:
            continue
        if h == state.robber_hex:
            robbed.add(res)
            continue
        dest = owed.setdefault(res, {})
        for seat, n in per_seat.items():
            dest[seat] = dest.get(seat, 0) + n
    return owed, robbed


def pay_out(state: GameState, owed: Owed) -> tuple[dict[int, dict[Resource, int]], dict[Resource, str]]:
    """Apply the classic shortage rule and move cards from the bank to the hands.
    Returns ``(gains, skipped)`` (gains only with non-zero entries)."""
    gains: dict[int, dict[Resource, int]] = {}
    skipped: dict[Resource, str] = {}
    for res in Resource:
        per_seat = owed.get(res)
        if not per_seat:
            continue
        total = sum(per_seat.values())
        available = state.bank[res]
        if total <= available:
            paid = dict(per_seat)
        elif len(per_seat) == 1 and available > 0:
            (seat, _), = per_seat.items()
            paid = {seat: available}
            skipped[res] = SKIP_BANK_PARTIAL
        else:
            skipped[res] = SKIP_BANK_SHORTAGE
            continue
        for seat, n in paid.items():
            state.bank[res] -= n
            state.players[seat].hand[res] += n
            gains.setdefault(seat, {})[res] = n
    return gains, skipped


def produce(state: GameState, roll: int, now_ms: int) -> list[Event]:
    """Pay out ``roll``; returns ``[Produced, Hand...]``."""
    owed, robbed = owed_by_resource(state, roll)
    gains, skipped = pay_out(state, owed)
    for res in robbed:
        skipped.setdefault(res, SKIP_ROBBER)
    gains_sorted = {seat: {r: g[r] for r in Resource if r in g} for seat, g in sorted(gains.items())}
    skipped_sorted = {r: skipped[r] for r in Resource if r in skipped}
    events: list[Event] = [Produced(at=now_ms, roll=roll, gains=gains_sorted, skipped=skipped_sorted)]
    for seat in gains_sorted:
        events.append(Hand(at=now_ms, seat=seat, hand=dict(state.players[seat].hand)))
    return events
