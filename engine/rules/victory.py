"""Victory (WP7): points, target, game over.

Responsibilities (docs/STAGE1_PLAN.md §4.1, §9 WP7):

* ``@connect(SIG_BUILT)``: recompute ``player.points`` (cached) and emit ``Points``.
* ``@after_step`` (late order): when a player reaches ``settings.victory.target``
  set ``phase = "finished"``, ``winner``, ``finished_at = now``; cancel pending
  timers as needed; emit ``GameOver``.
* Later: Longest Road / Largest Army hooks.

No handlers are registered yet.
"""
from __future__ import annotations
