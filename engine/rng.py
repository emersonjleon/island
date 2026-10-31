"""Deterministic, serializable pseudo-random number generator.

PCG32 (PCG-XSH-RR 64/32, O'Neill 2014) in pure integer maths: no floats and
no dependence on the platform or on Python's ``random`` module, so the same
seed gives the same sequence everywhere. The whole state is two 64-bit ints,
exposed as a JSON-friendly list via :attr:`Rng.state`.
"""

from __future__ import annotations

from collections.abc import MutableSequence, Sequence
from typing import TypeVar

__all__ = ["Rng", "DEFAULT_STREAM"]

T = TypeVar("T")

_MASK64 = (1 << 64) - 1
_MASK32 = (1 << 32) - 1
_MULTIPLIER = 6364136223846793005
DEFAULT_STREAM = 54
"""Stream (sequence) selector used when none is given."""


class Rng:
    """PCG32 generator. ``Rng(seed)`` is fully determined by ``seed`` (and ``stream``)."""

    __slots__ = ("_state", "_inc")

    def __init__(self, seed: int, stream: int = DEFAULT_STREAM) -> None:
        if not isinstance(seed, int) or not isinstance(stream, int):
            raise TypeError("seed and stream must be int")
        # Reference pcg32_srandom_r: seeds wider than 64 bits are reduced mod 2**64.
        self._state = 0
        self._inc = ((stream << 1) | 1) & _MASK64
        self._next32()
        self._state = (self._state + (seed & _MASK64)) & _MASK64
        self._next32()

    # ----------------------------------------------------------------- state
    @property
    def state(self) -> list[int]:
        """JSON-serializable state: ``[state, inc]`` (two unsigned 64-bit ints)."""
        return [self._state, self._inc]

    @classmethod
    def from_state(cls, state: Sequence[int]) -> Rng:
        """Rebuild a generator from :attr:`state`; it continues the same sequence."""
        if len(state) != 2 or not all(isinstance(v, int) and not isinstance(v, bool) for v in state):
            raise ValueError("rng state must be [state, inc] ints")
        st, inc = state
        if not (0 <= st <= _MASK64 and 0 <= inc <= _MASK64) or inc % 2 == 0:
            raise ValueError("rng state out of range (inc must be odd 64-bit)")
        rng = cls.__new__(cls)
        rng._state = st
        rng._inc = inc
        return rng

    def copy(self) -> Rng:
        return Rng.from_state(self.state)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Rng) and self.state == other.state

    __hash__ = None  # type: ignore[assignment]  # mutable

    def __repr__(self) -> str:
        return f"Rng.from_state({self.state!r})"

    # ------------------------------------------------------------------ core
    def _next32(self) -> int:
        old = self._state
        self._state = (old * _MULTIPLIER + self._inc) & _MASK64
        xorshifted = (((old >> 18) ^ old) >> 27) & _MASK32
        rot = old >> 59
        return ((xorshifted >> rot) | (xorshifted << ((-rot) & 31))) & _MASK32

    def next_u32(self) -> int:
        """Next raw 32-bit output."""
        return self._next32()

    def getrandbits(self, k: int) -> int:
        """Uniform int with ``k`` random bits (``0 <= x < 2**k``)."""
        if k < 0:
            raise ValueError("k must be >= 0")
        result = 0
        produced = 0
        while produced < k:
            result = (result << 32) | self._next32()
            produced += 32
        return result >> (produced - k)

    # ------------------------------------------------------------ public API
    def randbelow(self, n: int) -> int:
        """Uniform int in ``[0, n)``; unbiased (rejection sampling)."""
        if n <= 0:
            raise ValueError("randbelow(n) needs n > 0")
        k = n.bit_length()
        while True:
            r = self.getrandbits(k)
            if r < n:
                return r

    def randint(self, a: int, b: int) -> int:
        """Uniform int in ``[a, b]`` inclusive."""
        if b < a:
            raise ValueError("randint(a, b) needs a <= b")
        return a + self.randbelow(b - a + 1)

    def choice(self, seq: Sequence[T]) -> T:
        if not seq:
            raise IndexError("choice from empty sequence")
        return seq[self.randbelow(len(seq))]

    def shuffle(self, items: MutableSequence[T]) -> None:
        """Shuffle in place (Fisher-Yates)."""
        for i in range(len(items) - 1, 0, -1):
            j = self.randbelow(i + 1)
            items[i], items[j] = items[j], items[i]

    def sample(self, seq: Sequence[T], k: int) -> list[T]:
        """``k`` distinct positions of ``seq`` in random order (partial Fisher-Yates)."""
        n = len(seq)
        if not 0 <= k <= n:
            raise ValueError("sample size out of range")
        pool = list(seq)
        for i in range(k):
            j = i + self.randbelow(n - i)
            pool[i], pool[j] = pool[j], pool[i]
        return pool[:k]

    def dice(self, n: int = 2, sides: int = 6) -> list[int]:
        """Roll ``n`` dice with ``sides`` faces each (callers pass values from settings)."""
        if n < 0 or sides < 1:
            raise ValueError("dice needs n >= 0 and sides >= 1")
        return [self.randint(1, sides) for _ in range(n)]
