import time


class TokenBucket:
    """``rate`` tokens per second, bursts up to ``burst``."""

    def __init__(self, rate: float, burst: int, clock=time.monotonic):
        self.rate = rate
        self.burst = burst
        self.clock = clock
        self.tokens = float(burst)
        self.updated = clock()

    def take(self) -> bool:
        now = self.clock()
        self.tokens = min(self.burst, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False
