"""Settler movement (WP5): paths, per-edge stepping, interrupts.

Responsibilities (docs/STAGE1_PLAN.md §6, §9 WP5):

* ``@on_new_game``: create ``settings.settlers.start_count`` settlers per player at
  landing points (``state.next_id("settler")``, ``state.settlers``,
  ``player.settler_ids``) and emit ``SettlerLanded``.
* ``@command_handler("move_settler")``: validate (own settler, reachable vertex,
  e.g. codes ``move.not_your_settler``, ``move.unreachable``), then set
  ``settler.path`` and emit ``SettlerPath``; ``replace`` finishes the current edge
  first, ``append`` extends the queue.
* Each step: set ``settler.step`` (``SettlerStep``), schedule
  ``TIMER_SETTLER_ARRIVE`` (payload ``{"settler": id}``, store ``settler.timer_id``),
  emit ``SettlerStepEvent``; on leaving a vertex call
  ``emit(state, SIG_SETTLER_DEPARTING, now, settler=id, vertex=v)`` and include the
  returned events. Edge time: ``ms_per_edge``, divided by ``road_speed_pct`` / 100
  (integer maths) on the player's own road, computed when entering the edge.
* ``@timer_handler(TIMER_SETTLER_ARRIVE)``: move to ``step.to_v``, clear ``step``,
  ``SettlerArrived``, then start the next step if ``path`` is not empty.

No handlers are registered yet.
"""
from __future__ import annotations
