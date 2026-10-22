"""Timed construction (WP6): escrow, cancel/refund, first-to-finish, builder policy.

Responsibilities (docs/STAGE1_PLAN.md §4.1 "The construction entity", §9 WP6):

* ``@command_handler("build")``: check placement, builder policy
  (``settings.settlers.builder_required``; setup builds need the settler standing
  on the target), cost (``settings.economy.costs``) and pieces; then move the cost
  from the hand into ``Construction.paid`` (escrow), reserve the piece
  (``pieces_left``), schedule ``TIMER_CONSTRUCTION_DONE`` (payload
  ``{"construction": id}``) at ``now + settings.build.time_ms.<kind>`` and emit
  ``ConstructionStarted`` + ``Hand``.
* ``@command_handler("cancel_build")``: refund ``refund_pct`` of the escrow (rest to
  the bank), return the piece, cancel the timer, ``ConstructionCancelled``.
* ``@timer_handler(TIMER_CONSTRUCTION_DONE)``: re-check placement; place the piece
  (``state.buildings`` / ``state.roads``; a city returns the settlement piece),
  pay the escrow to the bank, ``emit(state, SIG_BUILT, ...)``, then emit ``Built``
  with ``points_after = player.points``; cancel and refund conflicting
  constructions (reason ``"conflict"``).
* ``@connect(SIG_SETTLER_DEPARTING)``: cancel builds whose builder left
  (reason ``"builder_left"``).

Invariant: bank + hands + escrow is constant per resource.
No handlers are registered yet.
"""
from __future__ import annotations
