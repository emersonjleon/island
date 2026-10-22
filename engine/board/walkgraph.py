"""Walking graph, path costs, pathfinding and landing points for settlers (WP5).

* **Nodes** are land vertices (touching at least one land hex); **edges** are land
  edges (touching at least one land hex). Coastal edges are walkable, sea is not.
  A ships expansion later only changes :func:`walk_edges`.
* **Edge cost** (game ms) is ``settlers.ms_per_edge``, or
  ``ms_per_edge * 100 // settlers.road_speed_pct`` on the walking player's own
  *finished* road (``state.roads[edge] == seat``). Integer maths only.
* **Search** is Dijkstra with integer costs and an early exit at the goal. Heap
  entries are ``(cost, vertex)`` and a vertex's predecessor only changes on a
  strictly cheaper cost, so ties resolve deterministically (smaller vertex id is
  expanded first, neighbours in ``board.vertex_neighbors`` order).
* **Landing points** (``settlers.landing == "even_coast"``): see :func:`landing_points`.

Everything here is a pure function of the board / state; nothing mutates the state
except :func:`landing_points`, which draws exactly one number from the given RNG.
"""
from __future__ import annotations

import heapq
from collections.abc import Callable, Sequence
from functools import lru_cache
from typing import TYPE_CHECKING

from engine.board.topology import Board
from engine.errors import EngineError
from engine.rng import Rng

if TYPE_CHECKING:
    from engine.state import GameState

__all__ = [
    "walk_edges", "is_walkable_vertex", "edge_between", "edge_cost_ms", "path_cost",
    "find_path", "shortest_path", "landing_cycle", "landing_points",
]

CostFn = Callable[[int], int]


# ----------------------------------------------------------------------- graph
@lru_cache(maxsize=32)
def walk_edges(board: Board) -> tuple[tuple[tuple[int, int], ...], ...]:
    """Per vertex id: ``((edge, neighbour), ...)`` over walkable edges, in
    ``board.vertex_edges`` order. Non-land vertices get an empty tuple."""
    out: list[tuple[tuple[int, int], ...]] = []
    for v in range(len(board.vertices)):
        if not board.land_vertex(v):
            out.append(())
            continue
        out.append(tuple((e, n) for e, n in zip(board.vertex_edges[v], board.vertex_neighbors[v])
                         if board.land_edge(e)))
    return tuple(out)


def is_walkable_vertex(board: Board, v: int) -> bool:
    """``v`` is a valid vertex id and touches a land hex."""
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v < len(board.vertices) \
        and board.land_vertex(v)


def edge_between(board: Board, a: int, b: int) -> int | None:
    """The walkable edge joining vertices ``a`` and ``b``, or None."""
    for e, n in walk_edges(board)[a]:
        if n == b:
            return e
    return None


# ----------------------------------------------------------------------- costs
def edge_cost_ms(state: GameState, seat: int, edge: int) -> int:
    """Time in game ms for ``seat``'s settler to walk ``edge`` right now."""
    ss = state.settings.settlers
    if state.roads.get(edge) == seat:
        return ss.ms_per_edge * 100 // ss.road_speed_pct
    return ss.ms_per_edge


def path_cost(state: GameState, seat: int, from_v: int, path: Sequence[int]) -> int:
    """Total current cost of walking ``from_v -> path[0] -> ... -> path[-1]``.
    Raises ``EngineError`` if two consecutive vertices are not joined by a walkable edge."""
    total = 0
    prev = from_v
    for v in path:
        e = edge_between(state.board.board, prev, v)
        if e is None:
            raise EngineError(f"walkgraph: no walkable edge {prev} -> {v}")
        total += edge_cost_ms(state, seat, e)
        prev = v
    return total


# --------------------------------------------------------------- pathfinding
def find_path(board: Board, from_v: int, to_v: int, cost: CostFn) -> tuple[int, list[int]] | None:
    """Cheapest path on the walk graph with integer edge costs ``cost(edge) > 0``.

    Returns ``(total_cost, [v1, ..., to_v])`` (the vertices after ``from_v``; empty
    when ``from_v == to_v``), or None if either end is not walkable or ``to_v`` is
    unreachable.
    """
    if not (is_walkable_vertex(board, from_v) and is_walkable_vertex(board, to_v)):
        return None
    if from_v == to_v:
        return 0, []
    adj = walk_edges(board)
    dist: dict[int, int] = {from_v: 0}
    prev: dict[int, int] = {}
    done: set[int] = set()
    heap: list[tuple[int, int]] = [(0, from_v)]
    while heap:
        d, v = heapq.heappop(heap)
        if v in done:
            continue
        if v == to_v:
            path = [v]
            while path[-1] in prev:
                path.append(prev[path[-1]])
            path.pop()               # from_v
            path.reverse()
            return d, path
        done.add(v)
        for e, n in adj[v]:
            if n in done:
                continue
            nd = d + cost(e)
            if nd < dist.get(n, nd + 1):
                dist[n] = nd
                prev[n] = v
                heapq.heappush(heap, (nd, n))
    return None


def shortest_path(state: GameState, seat: int, from_v: int, to_v: int) -> list[int] | None:
    """Fastest path for ``seat``'s settler given the current roads: the vertices after
    ``from_v`` up to ``to_v`` (``[]`` if equal), or None if not walkable / unreachable."""
    found = find_path(state.board.board, from_v, to_v, lambda e: edge_cost_ms(state, seat, e))
    return None if found is None else found[1]


# ------------------------------------------------------------- landing points
def landing_cycle(board: Board) -> list[int]:
    """Coastal vertices of the outer coastline in walking order (the longest outer
    cycle; ties go to the first, as ``Board.coastline_cycles`` orders them).
    Raises ``EngineError`` if the board has no outer coastline."""
    cycles = [c for c, outer in zip(board.coastline_vertex_cycles(), board.coastline_is_outer()) if outer]
    if not cycles:
        raise EngineError("walkgraph: board has no outer coastline")
    return max(cycles, key=len)


def landing_points(board: Board, count: int, rng: Rng) -> list[int]:
    """``count`` landing vertices spread evenly around the outer coastline.

    With ``L`` coast vertices and offset ``o = rng.randbelow(L)`` (one RNG draw),
    point ``i`` is ``cycle[(o + i * L // count) % L]``. If ``count > L`` points
    repeat (settlers may share a vertex). ``count == 0`` draws nothing.
    """
    if count < 0:
        raise EngineError("walkgraph: negative landing count")
    if count == 0:
        return []
    cycle = landing_cycle(board)
    n = len(cycle)
    offset = rng.randbelow(n)
    return [cycle[(offset + i * n // count) % n] for i in range(count)]
