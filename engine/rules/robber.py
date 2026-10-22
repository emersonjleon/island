"""Robber (WP7): sevens, random steal percentage, random neighbour move.

Responsibilities (docs/STAGE1_PLAN.md §4.1, §9 WP7):

* ``on_seven(state, now_ms) -> list[Event]`` called by dice when the roll equals
  ``settings.clock.robber_roll`` and ``settings.robber.enabled``: steal
  ``steal_pct`` (rounded per ``steal_rounding``) at random from targets chosen by
  ``card_limit`` / ``require_over_limit`` / ``require_adjacent`` /
  ``adjacency_timing``; stolen cards go to the bank; emit ``RobberStole`` (private)
  + ``Hand``; move the robber to a random neighbouring land hex
  (``may_enter_desert``) and emit ``RobberMoved``.
* Later: knight moves (``move(by=seat, max_dist)``).

No handlers are registered yet.
"""
from __future__ import annotations
