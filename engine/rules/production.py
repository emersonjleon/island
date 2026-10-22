"""Production (WP7): resources for a roll, bank shortage rule, fishing grounds.

Responsibilities (docs/STAGE1_PLAN.md §4.1, §9 WP7):

* ``produce(state, roll, now_ms) -> list[Event]`` called by dice: for every hex in
  ``state.board.producing_hexes(roll)`` except ``state.robber_hex``, pay
  ``settings.economy.production_per.<settlement|city>`` per adjacent building;
  apply the classic shortage rule per resource (nobody gets it unless only one
  player is owed it, who gets what is left); emit ``Produced`` (gains per seat,
  skipped resource -> reason code) and a ``Hand`` per changed seat.

No handlers are registered yet.
"""
from __future__ import annotations
