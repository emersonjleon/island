"""Engine exceptions.

* :class:`RuleError` -- a player intention is not allowed. ``code`` is a dotted
  i18n key (e.g. ``build.distance_rule``), ``params`` a JSON-safe dict of values
  the client interpolates. Never put prose in either.
* :class:`EngineError` -- an internal bug or a host contract violation (e.g. time
  going backwards in ``advance``). Never shown to players as a rule message.
"""
from __future__ import annotations

from typing import Any

__all__ = ["RuleError", "EngineError"]


class RuleError(Exception):
    """A rejected intention: ``code`` (i18n key) plus JSON-safe ``params``."""

    def __init__(self, code: str, params: dict[str, Any] | None = None) -> None:
        super().__init__(code, params or {})
        self.code = code
        self.params: dict[str, Any] = dict(params or {})

    def to_dict(self) -> dict[str, Any]:
        """``{"code": ..., "params": {...}}`` as sent in a ``reject`` message."""
        return {"code": self.code, "params": self.params}

    def __repr__(self) -> str:
        return f"RuleError({self.code!r}, {self.params!r})"

    def __str__(self) -> str:
        return f"{self.code} {self.params}" if self.params else self.code


class EngineError(Exception):
    """Internal engine bug or misuse of the engine API (not a player error)."""
