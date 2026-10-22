"""Setup phase (WP6): per-player setup, starting materials and starting resources.

Responsibilities (docs/STAGE1_PLAN.md §4.1, §9 WP6):

* ``@on_new_game``: give each player ``settings.economy.starting_materials``
  (taken from ``state.bank`` when ``starting_materials_from_bank``) and emit
  ``StartingMaterials`` + ``Hand`` per seat. (Settlers are landed by movement.)
* ``@connect(SIG_BUILT)``: for setup builds, decrement ``player.setup_remaining``,
  track ``last_setup_settlement`` / ``setup_settlements_built``; grant
  ``starting_resources`` for the first ``granting_settlements`` settlements
  (``StartingResources`` + ``Hand``); when nothing remains: ``setup_done = True``,
  ``SetupComplete`` and, if ``settings.settlers.leave_after_setup``, remove the
  player's settlers (cancel their ``timer_id``, ``SettlerLeft``).
* Clock start: on the first settlement anyone completes (``not state.clock_started``)
  set ``clock_started``, ``phase = "running"``, schedule ``TIMER_DICE_ROLL`` at
  ``now + settings.clock.roll_interval_ms`` (payload ``{}``), store
  ``roll_timer_id`` / ``next_roll_at`` and emit ``ClockStarted``.

No handlers are registered yet.
"""
from __future__ import annotations
