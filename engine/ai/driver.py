"""Pacing for computer players: each bot decides once every ``think_ms`` of game time."""
from __future__ import annotations

from collections.abc import Iterable

from engine.ai.levels import LevelBot

__all__ = ["BotDriver"]


class BotDriver:
    """Keeps the next decision time of every bot.

    First decisions are staggered across one think interval so bots at the same
    level do not all act in the same millisecond.
    """

    def __init__(self, bots: Iterable[LevelBot], start_ms: int = 0) -> None:
        self.bots = sorted(bots, key=lambda b: b.seat)
        n = len(self.bots) or 1
        self.next_ms = {b.seat: start_ms + (i * b.level.think_ms) // n for i, b in enumerate(self.bots)}

    def __bool__(self) -> bool:
        return bool(self.bots)

    def next_wakeup(self) -> int | None:
        return min(self.next_ms.values()) if self.next_ms else None

    def due(self, now_ms: int) -> list[LevelBot]:
        """Bots whose turn to think has come (in seat order); each is rescheduled."""
        out = []
        for b in self.bots:
            if self.next_ms[b.seat] <= now_ms:
                self.next_ms[b.seat] = now_ms + b.level.think_ms
                out.append(b)
        return out
