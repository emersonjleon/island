"""Pointy-top hex grid in axial coordinates ``(q, r)``.

Conventions (see docs/STAGE1_PLAN.md §6):

* Neighbour directions: E(+1,0), W(-1,0), NE(+1,-1), NW(0,-1), SE(0,+1), SW(-1,+1).
  "North" is up on screen, i.e. smaller world ``y``; screen ``y`` grows downwards.
  "Clockwise" everywhere means clockwise as seen on screen.
* A hex has six corners N, NE, SE, S, SW, NW and six sides NE, E, SE, SW, W, NW
  (side X faces the neighbour in direction X).
* Canonical vertex key ``(q, r, "N"|"S")``; the other corners map onto these:
  NE(q,r)=S(q+1,r-1), NW(q,r)=S(q,r-1), SE(q,r)=N(q,r+1), SW(q,r)=N(q-1,r+1).
* Canonical edge key ``(q, r, "NE"|"E"|"SE")``; the other sides map onto these:
  SW(q,r)=NE(q-1,r+1), W(q,r)=E(q-1,r), NW(q,r)=SE(q,r-1).

Every function is deterministic and returns items in the documented order.
Functions that take a vertex or edge accept any (also non-canonical) key and
return canonical keys.

Geometry: ``world_xy``/``vertex_world_xy`` return floats (hex size 1,
``x = sqrt(3)*(q + r/2)``, ``y = 1.5*r``). They are for rendering only and must
never drive rule decisions. ``hex_xy2``/``vertex_xy2`` return exact integer
coordinates ``(X, Y)`` with ``x = X*sqrt(3)/2`` and ``y = Y/2``; use these when
an engine decision needs geometry (e.g. orientation tests).
"""
from __future__ import annotations

import math
from typing import Final

Hex = tuple[int, int]
Vertex = tuple[int, int, str]
Edge = tuple[int, int, str]

#: Direction name -> axial offset.
DIRECTIONS: Final[dict[str, Hex]] = {
    "NE": (1, -1),
    "E": (1, 0),
    "SE": (0, 1),
    "SW": (-1, 1),
    "W": (-1, 0),
    "NW": (0, -1),
}
#: Directions / sides in clockwise order starting at NE.
DIRECTION_ORDER: Final[tuple[str, ...]] = ("NE", "E", "SE", "SW", "W", "NW")
SIDE_ORDER: Final[tuple[str, ...]] = DIRECTION_ORDER
#: Corners in clockwise order starting at N.
CORNER_ORDER: Final[tuple[str, ...]] = ("N", "NE", "SE", "S", "SW", "NW")

_CORNER_TO_CANON: Final[dict[str, tuple[int, int, str]]] = {
    "N": (0, 0, "N"),
    "S": (0, 0, "S"),
    "NE": (1, -1, "S"),
    "NW": (0, -1, "S"),
    "SE": (0, 1, "N"),
    "SW": (-1, 1, "N"),
}
_SIDE_TO_CANON: Final[dict[str, tuple[int, int, str]]] = {
    "NE": (0, 0, "NE"),
    "E": (0, 0, "E"),
    "SE": (0, 0, "SE"),
    "SW": (-1, 1, "NE"),
    "W": (-1, 0, "E"),
    "NW": (0, -1, "SE"),
}
#: Integer corner offsets from the hex centre in (X, Y) units (see module doc).
_CORNER_XY2: Final[dict[str, tuple[int, int]]] = {
    "N": (0, -2),
    "NE": (1, -1),
    "SE": (1, 1),
    "S": (0, 2),
    "SW": (-1, 1),
    "NW": (-1, -1),
}
_SQRT3: Final[float] = math.sqrt(3.0)


def canon_vertex(q: int, r: int, corner: str) -> Vertex:
    """Canonical key of corner ``corner`` (N, NE, SE, S, SW, NW) of hex (q, r)."""
    try:
        dq, dr, c = _CORNER_TO_CANON[corner]
    except KeyError:
        raise ValueError(f"unknown corner {corner!r}") from None
    return (q + dq, r + dr, c)


def canon_edge(q: int, r: int, side: str) -> Edge:
    """Canonical key of side ``side`` (NE, E, SE, SW, W, NW) of hex (q, r)."""
    try:
        dq, dr, s = _SIDE_TO_CANON[side]
    except KeyError:
        raise ValueError(f"unknown side {side!r}") from None
    return (q + dq, r + dr, s)


def _cv(v: Vertex) -> Vertex:
    return canon_vertex(v[0], v[1], v[2])


def _ce(e: Edge) -> Edge:
    return canon_edge(e[0], e[1], e[2])


def hex_neighbors(h: Hex) -> list[Hex]:
    """The 6 neighbours, clockwise from NE (NE, E, SE, SW, W, NW).

    ``hex_neighbors(h)[i]`` shares side ``hex_edges(h)[i]`` with ``h``.
    """
    q, r = h
    return [(q + DIRECTIONS[d][0], r + DIRECTIONS[d][1]) for d in DIRECTION_ORDER]


def hex_distance(a: Hex, b: Hex) -> int:
    """Number of steps between two hexes."""
    dq = a[0] - b[0]
    dr = a[1] - b[1]
    return (abs(dq) + abs(dr) + abs(dq + dr)) // 2


# Step directions used to walk a ring clockwise starting at its NE corner hex.
_RING_STEPS: Final[tuple[str, ...]] = ("SE", "SW", "W", "NW", "NE", "E")


def hex_ring(center: Hex, radius: int) -> list[Hex]:
    """Hexes at exactly ``radius`` from ``center``.

    Radius 0 gives ``[center]``. Otherwise ``6*radius`` hexes, starting at
    ``center + radius*NE`` and walking clockwise.
    """
    if radius < 0:
        raise ValueError("radius must be >= 0")
    if radius == 0:
        return [center]
    q = center[0] + DIRECTIONS["NE"][0] * radius
    r = center[1] + DIRECTIONS["NE"][1] * radius
    out: list[Hex] = []
    for d in _RING_STEPS:
        dq, dr = DIRECTIONS[d]
        for _ in range(radius):
            out.append((q, r))
            q += dq
            r += dr
    return out


def spiral(center: Hex, count: int) -> list[Hex]:
    """The first ``count`` hexes of the spiral: ring 0, ring 1, ... each in
    ``hex_ring`` order (start at the NE corner hex, clockwise)."""
    if count < 0:
        raise ValueError("count must be >= 0")
    out: list[Hex] = []
    radius = 0
    while len(out) < count:
        out.extend(hex_ring(center, radius))
        radius += 1
    return out[:count]


def hex_vertices(h: Hex) -> list[Vertex]:
    """The 6 corners of ``h`` clockwise from N (N, NE, SE, S, SW, NW)."""
    return [canon_vertex(h[0], h[1], c) for c in CORNER_ORDER]


def hex_edges(h: Hex) -> list[Edge]:
    """The 6 sides of ``h`` clockwise from NE (NE, E, SE, SW, W, NW).

    Side i joins corners ``hex_vertices(h)[i]`` and ``hex_vertices(h)[(i+1) % 6]``.
    """
    return [canon_edge(h[0], h[1], s) for s in SIDE_ORDER]


def edge_vertices(e: Edge) -> tuple[Vertex, Vertex]:
    """The 2 end vertices of an edge, in clockwise order around hex ``(q, r)``
    of the canonical key (NE: N, NE corner; E: NE, SE corner; SE: SE, S corner)."""
    q, r, s = _ce(e)
    if s == "NE":
        return (canon_vertex(q, r, "N"), canon_vertex(q, r, "NE"))
    if s == "E":
        return (canon_vertex(q, r, "NE"), canon_vertex(q, r, "SE"))
    return (canon_vertex(q, r, "SE"), canon_vertex(q, r, "S"))


def edge_hexes(e: Edge) -> tuple[Hex, Hex]:
    """The 2 hexes sharing an edge: canonical ``(q, r)`` first, then its
    neighbour across that side."""
    q, r, s = _ce(e)
    dq, dr = DIRECTIONS[s]
    return ((q, r), (q + dq, r + dr))


def vertex_hexes(v: Vertex) -> tuple[Hex, Hex, Hex]:
    """The 3 hexes meeting at a vertex, clockwise starting with the canonical
    hex ``(q, r)``. N(q,r): (q,r), (q,r-1), (q+1,r-1). S(q,r): (q,r), (q,r+1), (q-1,r+1)."""
    q, r, c = _cv(v)
    if c == "N":
        return ((q, r), (q, r - 1), (q + 1, r - 1))
    return ((q, r), (q, r + 1), (q - 1, r + 1))


def vertex_edges(v: Vertex) -> tuple[Edge, Edge, Edge]:
    """The 3 edges meeting at a vertex; edge i separates ``vertex_hexes(v)[i]``
    and ``vertex_hexes(v)[(i+1) % 3]`` (so the order is clockwise too)."""
    q, r, c = _cv(v)
    if c == "N":
        return ((q, r - 1, "SE"), (q, r - 1, "E"), (q, r, "NE"))
    return ((q, r, "SE"), (q - 1, r + 1, "E"), (q - 1, r + 1, "NE"))


def vertex_neighbors(v: Vertex) -> tuple[Vertex, Vertex, Vertex]:
    """The 3 adjacent vertices; neighbour i is the far end of ``vertex_edges(v)[i]``."""
    cv = _cv(v)
    out: list[Vertex] = []
    for e in vertex_edges(cv):
        a, b = edge_vertices(e)
        out.append(b if a == cv else a)
    return (out[0], out[1], out[2])


def hex_xy2(h: Hex) -> tuple[int, int]:
    """Exact integer centre ``(X, Y)`` with ``x = X*sqrt(3)/2``, ``y = Y/2``."""
    return (2 * h[0] + h[1], 3 * h[1])


def vertex_xy2(v: Vertex) -> tuple[int, int]:
    """Exact integer position of a vertex in the same units as ``hex_xy2``."""
    q, r, c = _cv(v)
    x, y = hex_xy2((q, r))
    dx, dy = _CORNER_XY2[c]
    return (x + dx, y + dy)


def world_xy(h: Hex) -> tuple[float, float]:
    """Float world centre (hex size 1). Rendering only, never for rules."""
    return (_SQRT3 * (h[0] + h[1] / 2), 1.5 * h[1])


def vertex_world_xy(v: Vertex) -> tuple[float, float]:
    """Float world position of a vertex. Rendering only, never for rules."""
    x, y = vertex_xy2(v)
    return (x * _SQRT3 / 2, y / 2)
