"""Dice clock (WP7): the dice source and the roll timer.

Responsibilities (docs/STAGE1_PLAN.md §4.1, §9 WP7):

* ``@timer_handler(TIMER_DICE_ROLL)``: roll ``settings.clock.dice_count`` dice of
  ``dice_sides`` with ``state.rng``; set ``last_roll``, append the sum to
  ``dice_history``; schedule the next roll at ``now + roll_interval_ms`` (store
  ``roll_timer_id``, ``next_roll_at``); emit ``DiceRolled``; then run production
  (or the robber on ``settings.clock.robber_roll``).

The first roll is scheduled by setup when the first settlement is completed.
No handlers are registered yet.
"""
from __future__ import annotations
