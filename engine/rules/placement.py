"""Placement legality (WP6): distance rule, connectivity, pieces, buildable sets.

Responsibilities (docs/STAGE1_PLAN.md §4.1, §9 WP6):

* Pure checks used by construction (raise ``RuleError`` with ``build.*`` codes,
  e.g. ``build.distance_rule``, ``build.not_connected``, ``build.no_pieces``).
* ``buildable(state, seat) -> {"roads": [...], "settlements": [...], "cities": [...]}``
  (sorted id lists), registered with ``views.register_buildable_provider``.
* ``@after_step``: recompute each seat's sets, compare with
  ``state.buildable_cache[seat]`` and emit ``Buildable`` (private) when changed,
  updating the cache.

No handlers are registered yet.
"""
from __future__ import annotations
