"""Deterministic timer heap stored in the game state.

Entries are ``(due_ms, seq, id, kind, payload)``. Timers fire in ``(due_ms, seq)``
order, so timers due at the same millisecond fire in the order they were
scheduled. ``seq`` and ``id`` come from counters that are part of the serialised
state, so a restored scheduler hands out the same ids as the original would.

``cancel`` is lazy: the heap entry stays until popped and is skipped then.
Payloads must be JSON-safe dicts with string keys (they are serialised as-is).
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Any

from engine.errors import EngineError

__all__ = ["Timer", "Scheduler"]


@dataclass(frozen=True)
class Timer:
    due_ms: int
    seq: int
    id: int
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_list(self) -> list[Any]:
        return [self.due_ms, self.seq, self.id, self.kind, dict(self.payload)]


def _check_int(name: str, value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise EngineError(f"scheduler: {name} must be int, got {value!r}")
    return value


class Scheduler:
    """Timer heap. ``Scheduler()`` is empty; ids and seqs start at 1."""

    __slots__ = ("_heap", "_live", "_next_seq", "_next_id")

    def __init__(self) -> None:
        self._heap: list[tuple[int, int, int]] = []   # (due_ms, seq, id)
        self._live: dict[int, Timer] = {}
        self._next_seq = 1
        self._next_id = 1

    # ------------------------------------------------------------- mutation
    def schedule(self, due_ms: int, kind: str, payload: dict[str, Any] | None = None) -> int:
        """Add a timer and return its id."""
        _check_int("due_ms", due_ms)
        if due_ms < 0:
            raise EngineError("scheduler: due_ms must be >= 0")
        if not isinstance(kind, str) or not kind:
            raise EngineError("scheduler: kind must be a non-empty str")
        if payload is not None and not isinstance(payload, dict):
            raise EngineError("scheduler: payload must be a dict")
        timer = Timer(due_ms, self._next_seq, self._next_id, kind, dict(payload or {}))
        self._next_seq += 1
        self._next_id += 1
        self._live[timer.id] = timer
        heapq.heappush(self._heap, (timer.due_ms, timer.seq, timer.id))
        return timer.id

    def cancel(self, timer_id: int | None) -> bool:
        """Cancel a pending timer. Returns False if unknown, fired or already cancelled."""
        if timer_id is None:
            return False
        return self._live.pop(timer_id, None) is not None

    def pop_next(self, now_ms: int) -> Timer | None:
        """Remove and return the earliest live timer with ``due_ms <= now_ms``."""
        self._drop_cancelled()
        if self._heap and self._heap[0][0] <= now_ms:
            _, _, timer_id = heapq.heappop(self._heap)
            return self._live.pop(timer_id)
        return None

    def pop_due(self, now_ms: int) -> list[Timer]:
        """Remove and return all live timers with ``due_ms <= now_ms`` in order.

        Note: the orchestrator uses :meth:`pop_next` so that timers scheduled by a
        handler are interleaved correctly with the ones already due.
        """
        out: list[Timer] = []
        while (t := self.pop_next(now_ms)) is not None:
            out.append(t)
        return out

    # --------------------------------------------------------------- queries
    def next_due(self) -> int | None:
        """``due_ms`` of the earliest live timer, or None."""
        self._drop_cancelled()
        return self._heap[0][0] if self._heap else None

    def get(self, timer_id: int | None) -> Timer | None:
        return None if timer_id is None else self._live.get(timer_id)

    def pending(self, kind: str | None = None) -> list[Timer]:
        """Live timers (optionally of one kind) in firing order."""
        return sorted((t for t in self._live.values() if kind is None or t.kind == kind),
                      key=lambda t: (t.due_ms, t.seq))

    def __len__(self) -> int:
        return len(self._live)

    def _drop_cancelled(self) -> None:
        heap = self._heap
        while heap and heap[0][2] not in self._live:
            heapq.heappop(heap)

    # --------------------------------------------------------- serialisation
    def to_list(self) -> list[list[Any]]:
        """Live entries ``[due_ms, seq, id, kind, payload]`` in firing order."""
        return [t.to_list() for t in self.pending()]

    @classmethod
    def from_list(cls, entries: list[list[Any]], next_seq: int | None = None,
                  next_id: int | None = None) -> Scheduler:
        """Rebuild from :meth:`to_list` output. Counters default to max + 1."""
        sched = cls()
        max_seq = max_id = 0
        for entry in entries:
            due_ms, seq, timer_id, kind, payload = entry
            for name, v in (("due_ms", due_ms), ("seq", seq), ("id", timer_id)):
                _check_int(name, v)
            if timer_id in sched._live:
                raise EngineError(f"scheduler: duplicate timer id {timer_id}")
            timer = Timer(due_ms, seq, timer_id, str(kind), dict(payload))
            sched._live[timer_id] = timer
            sched._heap.append((due_ms, seq, timer_id))
            max_seq, max_id = max(max_seq, seq), max(max_id, timer_id)
        heapq.heapify(sched._heap)
        sched._next_seq = max_seq + 1 if next_seq is None else max(next_seq, max_seq + 1)
        sched._next_id = max_id + 1 if next_id is None else max(next_id, max_id + 1)
        return sched

    def to_dict(self) -> dict[str, Any]:
        """Full state including counters (what the codec stores)."""
        return {"next_seq": self._next_seq, "next_id": self._next_id, "timers": self.to_list()}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Scheduler:
        return cls.from_list(d["timers"], d["next_seq"], d["next_id"])
