"""Board generator (plan §6, work package WP3).

``generate_board(settings, rng)`` turns ``GameSettings`` into a ``GeneratedBoard``:

1. **Land**: the first ``land_hexes`` hexes of the spiral, surrounded by
   ``sea_margin`` rings of sea (``Board.spiral_island``). Only the ``spiral``
   shape exists in stage 1.
2. **Terrain**: the resolved terrain counts, shuffled over the land hexes.
3. **Fishing grounds**: sea hexes next to land, taken in outer-coastline order,
   evenly spaced with a random rotation offset. ``fishing_grounds.min_gap`` is
   the minimum number of hexes *between* two fishing grounds, so their hex
   distance must be at least ``min_gap + 1`` (0 = adjacent grounds allowed).
4. **Number tokens**: red tokens (``red_numbers``) go first, by random greedy
   choice with restarts, so that no two red hexes are adjacent (unless
   ``red_may_touch``). With ``red_rule_includes_fishing`` the red fishing
   tokens join the same rule (no red fishing ground next to a red land hex or
   another red fishing ground). The other tokens are then shuffled onto the
   remaining producing land hexes and fishing grounds.
5. **Harbors**: evenly spaced edges of the outer coastline (random rotation
   offset), pairwise vertex-disjoint. Each harbor may slide up to half the
   spacing from its ideal position; among all rotations the one with the
   fewest harbors facing a fishing ground wins (ties: first in scan order,
   which starts at the random offset). Types are shuffled.
6. **Robber**: ``desert`` = a random desert hex; if the board has no desert,
   or with ``random_land``, a random land hex. ``None`` if the robber is
   disabled (``settings.robber.enabled``).

Randomness: everything comes from ``rng``, in the order terrain, fishing
grounds, tokens, harbors, robber. With ``board.layout == "seeded"`` and
``board.seed`` set, a fresh ``Rng(board.seed)`` is used instead and the passed
``rng`` is left untouched, so a seeded layout is the same in every game.

Impossible configurations raise ``BoardGenerationError`` (a ``ValueError``
carrying an i18n ``code`` and ``params``); the lobby calls
``check_board_settings`` as a dry run.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from engine.board import coords
from engine.board.model import GeneratedBoard, Harbor
from engine.board.topology import Board
from engine.rng import Rng
from engine.settings.enums import TERRAIN_RESOURCE, BoardLayout, BoardShape, Resource, RobberStart, Terrain
from engine.settings.models import GameSettings
from engine.settings.resolve import ResolvedBoardCounts, resolve_board_counts

__all__ = ["BoardGenerationError", "generate_board", "check_board_settings", "MAX_RED_RESTARTS"]

MAX_RED_RESTARTS = 300
"""Restarts of the random greedy red-token placement before giving up (algorithm bound, not a game rule)."""


class BoardGenerationError(ValueError):
    """The settings describe a board that cannot be generated."""

    def __init__(self, code: str, **params: Any) -> None:
        super().__init__(code, params)
        self.code = code
        self.params = params


# --------------------------------------------------------------------- public
def generate_board(settings: GameSettings, rng: Rng) -> GeneratedBoard:
    """Generate the board for ``settings``; deterministic in ``settings`` and ``rng`` state."""
    bs = settings.board
    if bs.layout == BoardLayout.SEEDED and bs.seed is not None:
        rng = Rng(bs.seed)
    if bs.shape != BoardShape.SPIRAL:
        raise BoardGenerationError("board.shape_unsupported", shape=bs.shape.value)
    counts = resolve_board_counts(settings)
    if counts.land_hexes != bs.land_hexes:
        raise BoardGenerationError("board.terrain_count_mismatch", terrain=counts.land_hexes,
                                   land_hexes=bs.land_hexes)

    board = Board.spiral_island(bs.land_hexes, bs.sea_margin)
    coast_edges = _outer_coast(board)
    terrain = _place_terrain(board, counts, rng)
    fishing = _place_fishing(board, coast_edges, counts.fishing_count, bs.fishing_grounds.min_gap, rng)
    token = _place_tokens(board, terrain, fishing, counts, settings, rng)
    harbors = _place_harbors(board, coast_edges, set(fishing), counts, settings, rng)
    robber = _robber_start(board, terrain, settings, rng)
    return GeneratedBoard(board=board, terrain=terrain, token=token, fishing=frozenset(fishing),
                          harbors=harbors, robber_start=robber)


def check_board_settings(settings: GameSettings, seed: int = 0) -> None:
    """Lobby dry run: raise ``BoardGenerationError`` if this configuration cannot be generated."""
    generate_board(settings, Rng(seed))


# ---------------------------------------------------------------------- steps
def _outer_coast(board: Board) -> list[int]:
    """Edge ids of the longest outer coastline cycle, in walking order."""
    outer = [c for c, is_outer in zip(board.coastline_cycles(), board.coastline_is_outer()) if is_outer]
    if not outer:
        raise BoardGenerationError("board.no_coastline")
    return max(outer, key=len)


def _place_terrain(board: Board, counts: ResolvedBoardCounts, rng: Rng) -> tuple[Terrain | None, ...]:
    bag = [t for t, n in counts.terrain_counts.items() for _ in range(n)]
    rng.shuffle(bag)
    sea: list[Terrain | None] = [None] * (len(board.hexes) - board.land_hex_count)
    return tuple(bag) + tuple(sea)


def _sea_hex(board: Board, edge: int) -> int | None:
    return next((h for h in board.edge_hexes[edge] if not board.is_land(h)), None)


def _coastal_sea_hexes(board: Board, coast_edges: Sequence[int]) -> list[int]:
    """Sea hexes next to land, in outer-coastline order (each once)."""
    out: list[int] = []
    seen: set[int] = set()
    for e in coast_edges:
        h = _sea_hex(board, e)
        if h is not None and h not in seen:
            seen.add(h)
            out.append(h)
    return out


def _deltas(window: int) -> list[int]:
    """0, +1, -1, +2, -2, ... up to ``window``."""
    out = [0]
    for d in range(1, window + 1):
        out += [d, -d]
    return out


def _place_fishing(board: Board, coast_edges: Sequence[int], count: int, min_gap: int, rng: Rng) -> list[int]:
    if count == 0:
        return []
    cand = _coastal_sea_hexes(board, coast_edges)
    m = len(cand)
    min_dist = min_gap + 1
    if count <= m:
        start = rng.randbelow(m)
        window = (m // count) // 2
        for k in range(m):
            picked = _fishing_for_offset(board, cand, count, (start + k) % m, window, min_dist)
            if picked is not None:
                return picked
    raise BoardGenerationError("board.fishing_grounds_unplaceable", count=count, candidates=m, min_gap=min_gap)


def _fishing_for_offset(board: Board, cand: Sequence[int], count: int, offset: int, window: int,
                        min_dist: int) -> list[int] | None:
    m = len(cand)
    picked: list[int] = []
    for i in range(count):
        target = offset + i * m // count
        for d in _deltas(window):
            h = cand[(target + d) % m]
            if h not in picked and all(
                    coords.hex_distance(board.hexes[h], board.hexes[p]) >= min_dist for p in picked):
                picked.append(h)
                break
        else:
            return None
    return picked


def _place_tokens(board: Board, terrain: Sequence[Terrain | None], fishing: Sequence[int],
                  counts: ResolvedBoardCounts, settings: GameSettings, rng: Rng) -> tuple[int | None, ...]:
    bs = settings.board
    producing = [h for h in board.land_hex_ids if TERRAIN_RESOURCE.get(terrain[h]) is not None]  # type: ignore[arg-type]
    if len(producing) != len(counts.number_tokens):
        raise BoardGenerationError("board.token_count_mismatch", tokens=len(counts.number_tokens),
                                   producing=len(producing))
    red = set(bs.red_numbers)
    land_red = [t for t in counts.number_tokens if t in red]
    land_rest = [t for t in counts.number_tokens if t not in red]
    fish_red = [t for t in counts.fishing_tokens if t in red]
    fish_rest = [t for t in counts.fishing_tokens if t not in red]

    spread = not bs.red_may_touch
    land_spots, fish_spots = _place_reds(board, producing, list(fishing), len(land_red), len(fish_red),
                                         spread, spread and bs.red_rule_includes_fishing, rng)
    token: list[int | None] = [None] * len(board.hexes)
    _deal(token, land_spots, land_red, rng)
    _deal(token, [h for h in producing if h not in set(land_spots)], land_rest, rng)
    _deal(token, fish_spots, fish_red, rng)
    _deal(token, [h for h in fishing if h not in set(fish_spots)], fish_rest, rng)
    return tuple(token)


def _deal(token: list[int | None], hexes: Sequence[int], values: Sequence[int], rng: Rng) -> None:
    """Shuffle ``values`` onto ``hexes`` (same length)."""
    bag = list(values)
    rng.shuffle(bag)
    for h, v in zip(hexes, bag, strict=True):
        token[h] = v


def _place_reds(board: Board, producing: list[int], fishing: list[int], n_land: int, n_fish: int,
                spread_land: bool, spread_fish: bool, rng: Rng) -> tuple[list[int], list[int]]:
    """Hexes for the red land and red fishing tokens, by random greedy choice with restarts."""
    for _ in range(MAX_RED_RESTARTS):
        taken: set[int] = set()
        land = _greedy(board, producing, n_land, taken if spread_land else None, rng)
        if land is None:
            continue
        taken.update(land)
        fish = _greedy(board, fishing, n_fish, taken if spread_fish else None, rng)
        if fish is not None:
            return land, fish
        if not spread_land and not spread_fish:
            break
    raise BoardGenerationError("board.red_rule_unsatisfiable", land_red=n_land, fishing_red=n_fish,
                               producing=len(producing), fishing=len(fishing))


def _greedy(board: Board, pool: list[int], k: int, taken: set[int] | None, rng: Rng) -> list[int] | None:
    """``k`` hexes from ``pool`` in random order; with ``taken`` (a set it extends), none of them
    adjacent to each other or to a hex already in ``taken``. None if the greedy pass fails."""
    order = list(pool)
    rng.shuffle(order)
    if taken is None:
        return order[:k] if k <= len(order) else None
    chosen: list[int] = []
    blocked = set(taken)
    for h in order:
        if len(chosen) == k:
            break
        if h in blocked or any(n in blocked for n in board.hex_neighbors[h]):
            continue
        chosen.append(h)
        blocked.add(h)
    return chosen if len(chosen) == k else None


def _place_harbors(board: Board, coast_edges: Sequence[int], fishing: set[int], counts: ResolvedBoardCounts,
                   settings: GameSettings, rng: Rng) -> tuple[Harbor, ...]:
    total = counts.harbors_total
    if total == 0:
        return ()
    hs = settings.board.harbors
    n = len(coast_edges)
    best: list[int] | None = None
    if 2 * total <= n:
        start = rng.randbelow(n)
        window = (n // total) // 2
        best_score = total + 1
        for k in range(n):
            picked = _harbors_for_offset(board, coast_edges, total, (start + k) % n, window, fishing)
            if picked is None:
                continue
            score = sum(1 for i in picked if _sea_hex(board, coast_edges[i]) in fishing)
            if score < best_score:
                best, best_score = picked, score
                if score == 0:
                    break
    if best is None:
        raise BoardGenerationError("board.harbors_unplaceable", count=total, coastal_edges=n)

    kinds: list[Resource | None] = [None] * counts.harbors_generic
    kinds += [r for r, c in counts.harbors_specific.items() for _ in range(c)]
    rng.shuffle(kinds)
    out: list[Harbor] = []
    for i, kind in zip(sorted(best), kinds, strict=True):
        e = coast_edges[i]
        out.append(Harbor(edge=e, vertices=board.edge_vertices[e], resource=kind,
                          ratio=hs.generic_ratio if kind is None else hs.specific_ratio))
    return tuple(out)


def _harbors_for_offset(board: Board, coast_edges: Sequence[int], total: int, offset: int, window: int,
                        fishing: set[int]) -> list[int] | None:
    """Coast-cycle indices of ``total`` vertex-disjoint edges near even spacing from ``offset``;
    near each target an edge facing open sea beats one facing a fishing ground."""
    n = len(coast_edges)
    picked: list[int] = []
    used: set[int] = set()
    for i in range(total):
        target = offset + i * n // total
        fallback: int | None = None
        choice: int | None = None
        for d in _deltas(window):
            idx = (target + d) % n
            vs = board.edge_vertices[coast_edges[idx]]
            if idx in picked or used.intersection(vs):
                continue
            if _sea_hex(board, coast_edges[idx]) not in fishing:
                choice = idx
                break
            if fallback is None:
                fallback = idx
        choice = fallback if choice is None else choice
        if choice is None:
            return None
        picked.append(choice)
        used.update(board.edge_vertices[coast_edges[choice]])
    return picked


def _robber_start(board: Board, terrain: Sequence[Terrain | None], settings: GameSettings,
                  rng: Rng) -> int | None:
    if not settings.robber.enabled:
        return None
    if settings.board.robber_start == RobberStart.DESERT:
        deserts = [h for h in board.land_hex_ids if terrain[h] == Terrain.DESERT]
        if deserts:
            return rng.choice(deserts)
    return rng.choice(board.land_hex_ids)
