"""Trading (WP7): bank 4:1 and harbor ratios.

Responsibilities (docs/STAGE1_PLAN.md §4.1, §9 WP7):

* ``@command_handler("bank_trade")``: best ratio for the given resource
  (``settings.economy.trade.bank_ratio``, or a harbor the player has a building on
  when ``settings.trading.harbor_trade``; see ``state.board.vertex_harbor``);
  require ``give == ratio * get``, the hand to hold ``give`` and the bank to hold
  ``get`` (codes ``trade.*``); respect ``settings.setup.bank_trade_during_setup``;
  emit ``Traded`` + ``Hand``.

No handlers are registered yet.
"""
from __future__ import annotations
