"""Game time in integer milliseconds. Each game has its own clock that starts at the
game's current time, so time the host was down counts as a pause."""
import time


class MonotonicClock:
    def __init__(self, start_ms: int = 0):
        self._offset = start_ms
        self._t0 = time.monotonic_ns()

    def now(self) -> int:
        return self._offset + (time.monotonic_ns() - self._t0) // 1_000_000


class ManualClock:
    """Tests: time moves only when told to."""

    def __init__(self, start_ms: int = 0):
        self.ms = start_ms

    def now(self) -> int:
        return self.ms

    def advance(self, ms: int) -> None:
        self.ms += ms
