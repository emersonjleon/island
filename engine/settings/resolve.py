"""Resolve the "auto" board counts of :class:`BoardSettings` for a board size.

Reference: the standard 19-land-hex board. Auto counts scale from it with
integer maths only:

* **Deserts** = ``round_half_up(land * 1 / 19)``. So 7..9 land hexes have no
  desert, 10..28 have one, and so on (19 -> 1). Deserts are computed first so a
  desert appears exactly when the standard ratio rounds to >= 1.
* **Producing terrains** share the remaining hexes by the largest-remainder
  (Hamilton) method on the standard 4/4/4/3/3 split; ties go to the earlier
  terrain in the order forest, pasture, fields, hills, mountains.
* **Number tokens**: one per producing land hex, largest remainder on the
  standard multiset; ties go to the token closer to the robber roll (7), then
  the lower number (order 6, 8, 5, 9, 4, 10, 3, 11, 2, 12).
* **Fishing grounds / generic harbors** = ``round_half_up(land * std / 19)``.
  Fishing tokens cycle through ``fishing_grounds.tokens`` in their given order.
* **Specific harbors** are never scaled: ``harbors.specific`` is used as is.

Explicit values in the settings always win over auto values.
At 19 land hexes every auto count equals the standard exactly.
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

from .enums import PRODUCING_TERRAINS, Resource, Terrain

if TYPE_CHECKING:
    from .models import BoardSettings, GameSettings

__all__ = [
    "STANDARD_LAND_HEXES", "STANDARD_TERRAIN_COUNTS", "STANDARD_NUMBER_TOKENS",
    "STANDARD_FISHING_GROUNDS", "STANDARD_GENERIC_HARBORS",
    "ResolvedBoardCounts", "resolve_board_counts", "scale_counts", "scale_round",
]

K = TypeVar("K", bound=Hashable)

# The standard (classic) board that every auto count scales from.
STANDARD_LAND_HEXES = 19
STANDARD_TERRAIN_COUNTS: dict[Terrain, int] = {
    Terrain.FOREST: 4, Terrain.PASTURE: 4, Terrain.FIELDS: 4,
    Terrain.HILLS: 3, Terrain.MOUNTAINS: 3, Terrain.DESERT: 1,
}
STANDARD_NUMBER_TOKENS: dict[int, int] = {2: 1, 3: 2, 4: 2, 5: 2, 6: 2, 8: 2, 9: 2, 10: 2, 11: 2, 12: 1}
STANDARD_FISHING_GROUNDS = 6
STANDARD_GENERIC_HARBORS = 4


@dataclass(frozen=True, slots=True)
class ResolvedBoardCounts:
    terrain_counts: dict[Terrain, int]
    """Every terrain, desert included, in ``Terrain`` order; sums to ``land_hexes``."""
    number_tokens: tuple[int, ...]
    """One token value per producing land hex, sorted ascending."""
    fishing_count: int
    fishing_tokens: tuple[int, ...]
    """One token per fishing ground (``len == fishing_count``)."""
    harbors_generic: int
    harbors_specific: dict[Resource, int]
    """Every resource, in ``Resource`` order."""

    @property
    def land_hexes(self) -> int:
        return sum(self.terrain_counts.values())

    @property
    def producing_land_hexes(self) -> int:
        return self.land_hexes - self.terrain_counts[Terrain.DESERT]

    @property
    def harbors_total(self) -> int:
        return self.harbors_generic + sum(self.harbors_specific.values())


def scale_round(standard: int, land_hexes: int) -> int:
    """``round_half_up(standard * land_hexes / STANDARD_LAND_HEXES)`` in integers."""
    return (2 * standard * land_hexes + STANDARD_LAND_HEXES) // (2 * STANDARD_LAND_HEXES)


def scale_counts(base: Sequence[tuple[K, int]], total: int) -> dict[K, int]:
    """Scale ``base`` counts to sum to ``total`` (largest remainder; ties by ``base`` order)."""
    base_sum = sum(c for _, c in base)
    if total < 0:
        raise ValueError("total must be >= 0")
    if base_sum <= 0:
        raise ValueError("base counts must sum to > 0")
    result: dict[K, int] = {}
    remainders: list[tuple[int, int, K]] = []
    for index, (key, count) in enumerate(base):
        quota = count * total
        result[key] = quota // base_sum
        remainders.append((-(quota % base_sum), index, key))
    missing = total - sum(result.values())
    for _, _, key in sorted(remainders)[:missing]:
        result[key] += 1
    return result


def _auto_terrain_counts(land_hexes: int) -> dict[Terrain, int]:
    deserts = scale_round(STANDARD_TERRAIN_COUNTS[Terrain.DESERT], land_hexes)
    producing = scale_counts([(t, STANDARD_TERRAIN_COUNTS[t]) for t in PRODUCING_TERRAINS], land_hexes - deserts)
    return {t: (deserts if t is Terrain.DESERT else producing[t]) for t in Terrain}


def _auto_number_tokens(producing: int, robber_roll: int) -> tuple[int, ...]:
    order = sorted(STANDARD_NUMBER_TOKENS, key=lambda n: (abs(n - robber_roll), n))
    scaled = scale_counts([(n, STANDARD_NUMBER_TOKENS[n]) for n in order], producing)
    return _expand(scaled)


def _expand(counts: Mapping[int, int]) -> tuple[int, ...]:
    return tuple(sorted(n for n, c in counts.items() for _ in range(c)))


def _cycle(tokens: Sequence[int], count: int) -> tuple[int, ...]:
    if count and not tokens:
        raise ValueError("fishing ground tokens must not be empty")
    return tuple(tokens[i % len(tokens)] for i in range(count))


def resolve_board_counts(settings: GameSettings | BoardSettings) -> ResolvedBoardCounts:
    """Concrete terrain, token, fishing-ground and harbor counts for these settings."""
    board: BoardSettings = getattr(settings, "board", settings)  # type: ignore[assignment]
    clock = getattr(settings, "clock", None)
    if clock is None:
        from .models import ClockSettings  # local import: models imports this module

        clock = ClockSettings()
    robber_roll = clock.robber_roll
    land = board.land_hexes

    if board.terrain_counts is None:
        terrain = _auto_terrain_counts(land)
    else:
        terrain = {t: board.terrain_counts.get(t, 0) for t in Terrain}
    producing = sum(c for t, c in terrain.items() if t is not Terrain.DESERT)

    if board.number_tokens is None:
        tokens = _auto_number_tokens(producing, robber_roll)
    else:
        tokens = _expand(board.number_tokens)

    fg = board.fishing_grounds
    fishing_count = scale_round(STANDARD_FISHING_GROUNDS, land) if fg.count is None else fg.count
    hb = board.harbors
    generic = scale_round(STANDARD_GENERIC_HARBORS, land) if hb.generic is None else hb.generic
    return ResolvedBoardCounts(
        terrain_counts=terrain,
        number_tokens=tokens,
        fishing_count=fishing_count,
        fishing_tokens=_cycle(fg.tokens, fishing_count),
        harbors_generic=generic,
        harbors_specific={r: hb.specific.get(r, 0) for r in Resource},
    )
