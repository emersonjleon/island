"""Dense-id board topology built from land and sea hex sets.

Id assignment (stable across rebuilds of the same hex sets):

* hexes: land hexes sorted by ``(q, r)``, then sea hexes sorted; so land ids are
  ``0 .. land_hex_count-1``;
* vertices / edges: every vertex / edge of any board hex, sorted by canonical key.

Adjacency tables are tuples indexed by id. Each keeps the order of the matching
``coords`` function with off-board items dropped:

* ``hex_vertices[h]`` (6, clockwise from N), ``hex_edges[h]`` (6, clockwise from
  the NE side), ``hex_neighbors[h]`` (on-board neighbours, clockwise from NE);
* ``vertex_hexes[v]`` (1-3), ``vertex_edges[v]`` (2-3) and ``vertex_neighbors[v]``
  (paired with ``vertex_edges``: neighbour i is the far end of edge i);
* ``edge_vertices[e]`` (2), ``edge_hexes[e]`` (1-2).

"Off-board" hexes (not land, not sea) count as non-land everywhere.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from engine.board import coords
from engine.board.coords import Edge, Hex, Vertex

IdTable = tuple[tuple[int, ...], ...]


class Board:
    """Immutable board topology. Build with ``from_hexes`` or ``spiral_island``."""

    __slots__ = (
        "hexes", "vertices", "edges",
        "hex_id", "vertex_id", "edge_id",
        "land_hex_count", "land_hex_ids", "sea_hex_ids",
        "hex_vertices", "hex_edges", "hex_neighbors",
        "vertex_hexes", "vertex_edges", "vertex_neighbors",
        "edge_vertices", "edge_hexes",
        "land_vertices", "land_edges", "coastal_edges", "coastal_vertices",
        "_land_vertex_mask", "_land_edge_mask", "_coastal_edge_mask",
        "_coast_edge_cycles", "_coast_vertex_cycles", "_coast_outer",
    )

    hexes: tuple[Hex, ...]
    vertices: tuple[Vertex, ...]
    edges: tuple[Edge, ...]
    hex_id: dict[Hex, int]
    vertex_id: dict[Vertex, int]
    edge_id: dict[Edge, int]
    land_hex_count: int
    land_hex_ids: tuple[int, ...]
    sea_hex_ids: tuple[int, ...]
    hex_vertices: IdTable
    hex_edges: IdTable
    hex_neighbors: IdTable
    vertex_hexes: IdTable
    vertex_edges: IdTable
    vertex_neighbors: IdTable
    edge_vertices: tuple[tuple[int, int], ...]
    edge_hexes: IdTable
    land_vertices: tuple[int, ...]
    land_edges: tuple[int, ...]
    coastal_edges: tuple[int, ...]
    coastal_vertices: tuple[int, ...]
    _land_vertex_mask: tuple[bool, ...]
    _land_edge_mask: tuple[bool, ...]
    _coastal_edge_mask: tuple[bool, ...]
    _coast_edge_cycles: tuple[tuple[int, ...], ...]
    _coast_vertex_cycles: tuple[tuple[int, ...], ...]
    _coast_outer: tuple[bool, ...]

    def __init__(self, land: Iterable[Hex], sea: Iterable[Hex] = ()) -> None:
        land_set = {(int(h[0]), int(h[1])) for h in land}
        sea_set = {(int(h[0]), int(h[1])) for h in sea}
        if land_set & sea_set:
            raise ValueError("a hex cannot be both land and sea")
        self._build_ids(land_set, sea_set)
        self._build_adjacency()
        self._build_land(land_set)
        self._build_coastline()

    # ----------------------------------------------------------- constructors
    @classmethod
    def from_hexes(cls, land: Iterable[Hex], sea: Iterable[Hex] = ()) -> Board:
        return cls(land, sea)

    @classmethod
    def spiral_island(cls, land_count: int, sea_margin: int = 1) -> Board:
        """Land = first ``land_count`` spiral hexes from (0, 0); sea = every
        non-land hex within ``sea_margin`` steps of land."""
        land = coords.spiral((0, 0), land_count)
        return cls(land, sea_around(land, sea_margin))

    # ------------------------------------------------------------- build steps
    def _build_ids(self, land: set[Hex], sea: set[Hex]) -> None:
        self.hexes = tuple(sorted(land)) + tuple(sorted(sea))
        self.land_hex_count = len(land)
        self.land_hex_ids = tuple(range(len(land)))
        self.sea_hex_ids = tuple(range(len(land), len(self.hexes)))
        vs: set[Vertex] = set()
        es: set[Edge] = set()
        for h in self.hexes:
            vs.update(coords.hex_vertices(h))
            es.update(coords.hex_edges(h))
        self.vertices = tuple(sorted(vs))
        self.edges = tuple(sorted(es))
        self.hex_id = {h: i for i, h in enumerate(self.hexes)}
        self.vertex_id = {v: i for i, v in enumerate(self.vertices)}
        self.edge_id = {e: i for i, e in enumerate(self.edges)}

    def _build_adjacency(self) -> None:
        hid, vid, eid = self.hex_id, self.vertex_id, self.edge_id
        self.hex_vertices = tuple(tuple(vid[v] for v in coords.hex_vertices(h)) for h in self.hexes)
        self.hex_edges = tuple(tuple(eid[e] for e in coords.hex_edges(h)) for h in self.hexes)
        self.hex_neighbors = tuple(
            tuple(hid[n] for n in coords.hex_neighbors(h) if n in hid) for h in self.hexes
        )
        self.vertex_hexes = tuple(
            tuple(hid[h] for h in coords.vertex_hexes(v) if h in hid) for v in self.vertices
        )
        v_edges: list[tuple[int, ...]] = []
        v_neigh: list[tuple[int, ...]] = []
        for v in self.vertices:
            pairs = [
                (eid[e], vid[n])
                for e, n in zip(coords.vertex_edges(v), coords.vertex_neighbors(v))
                if e in eid
            ]
            v_edges.append(tuple(p[0] for p in pairs))
            v_neigh.append(tuple(p[1] for p in pairs))
        self.vertex_edges = tuple(v_edges)
        self.vertex_neighbors = tuple(v_neigh)
        ev: list[tuple[int, int]] = []
        for e in self.edges:
            a, b = coords.edge_vertices(e)
            ev.append((vid[a], vid[b]))
        self.edge_vertices = tuple(ev)
        self.edge_hexes = tuple(
            tuple(hid[h] for h in coords.edge_hexes(e) if h in hid) for e in self.edges
        )

    def _build_land(self, land: set[Hex]) -> None:
        self._land_vertex_mask = tuple(
            any(h in land for h in coords.vertex_hexes(v)) for v in self.vertices
        )
        land_count = [sum(h in land for h in coords.edge_hexes(e)) for e in self.edges]
        self._land_edge_mask = tuple(n >= 1 for n in land_count)
        self._coastal_edge_mask = tuple(n == 1 for n in land_count)
        self.land_vertices = tuple(i for i, m in enumerate(self._land_vertex_mask) if m)
        self.land_edges = tuple(i for i, m in enumerate(self._land_edge_mask) if m)
        self.coastal_edges = tuple(i for i, m in enumerate(self._coastal_edge_mask) if m)
        cv: set[int] = set()
        for e in self.coastal_edges:
            cv.update(self.edge_vertices[e])
        self.coastal_vertices = tuple(sorted(cv))

    def _build_coastline(self) -> None:
        """Split coastal edges into closed cycles.

        Every coastal vertex has exactly two coastal edges (the three hexes at a
        vertex are pairwise adjacent, so land/non-land changes come in pairs), so
        the coastal edges form disjoint simple cycles. Each cycle starts at its
        smallest edge id and is walked with land on the right-hand side as seen
        on screen: outer coasts run clockwise, lake shores anticlockwise. Outer
        cycles come first, each group ordered by start edge id.
        """
        coast_at: dict[int, list[int]] = {}
        for e in self.coastal_edges:
            for v in self.edge_vertices[e]:
                coast_at.setdefault(v, []).append(e)
        seen: set[int] = set()
        cycles: list[tuple[bool, tuple[int, ...], tuple[int, ...]]] = []
        for start in self.coastal_edges:
            if start in seen:
                continue
            a, b = self._oriented(start)
            e_cycle: list[int] = []
            v_cycle: list[int] = []
            e, v = start, a
            while True:
                seen.add(e)
                e_cycle.append(e)
                v_cycle.append(v)
                v = self._other_end(e, v)
                nxt = coast_at[v]
                e = nxt[1] if nxt[0] == e else nxt[0]
                if e == start:
                    break
            cycles.append((self._signed_area2(v_cycle) > 0, tuple(e_cycle), tuple(v_cycle)))
        cycles.sort(key=lambda c: (not c[0], c[1][0]))
        self._coast_outer = tuple(c[0] for c in cycles)
        self._coast_edge_cycles = tuple(c[1] for c in cycles)
        self._coast_vertex_cycles = tuple(c[2] for c in cycles)

    def _oriented(self, e: int) -> tuple[int, int]:
        """End vertices of coastal edge ``e`` ordered so land is on the right."""
        a, b = self.edge_vertices[e]
        land_hex = next(h for h in coords.edge_hexes(self.edges[e]) if self._is_land_key(h))
        ax, ay = coords.vertex_xy2(self.vertices[a])
        bx, by = coords.vertex_xy2(self.vertices[b])
        hx, hy = coords.hex_xy2(land_hex)
        # Screen y grows downwards, so cross > 0 means the land is to the right.
        cross = (bx - ax) * (hy - ay) - (by - ay) * (hx - ax)
        return (a, b) if cross > 0 else (b, a)

    def _signed_area2(self, vs: list[int]) -> int:
        pts = [coords.vertex_xy2(self.vertices[v]) for v in vs]
        total = 0
        for i, (x0, y0) in enumerate(pts):
            x1, y1 = pts[(i + 1) % len(pts)]
            total += x0 * y1 - x1 * y0
        return total

    def _other_end(self, e: int, v: int) -> int:
        a, b = self.edge_vertices[e]
        return b if a == v else a

    def _is_land_key(self, h: Hex) -> bool:
        i = self.hex_id.get(h)
        return i is not None and i < self.land_hex_count

    # ------------------------------------------------------------------ queries
    def is_land(self, hex_id: int) -> bool:
        return 0 <= hex_id < self.land_hex_count

    def land_vertex(self, v: int) -> bool:
        """Vertex touches at least one land hex."""
        return self._land_vertex_mask[v]

    def land_edge(self, e: int) -> bool:
        """Edge touches at least one land hex (walkable / buildable)."""
        return self._land_edge_mask[e]

    def coastal_edge(self, e: int) -> bool:
        """Edge has exactly one land hex (other side sea or off-board)."""
        return self._coastal_edge_mask[e]

    def coastline_cycles(self) -> list[list[int]]:
        """Coastal edge ids as closed cycles in walking order (see ``_build_coastline``)."""
        return [list(c) for c in self._coast_edge_cycles]

    def coastline_vertex_cycles(self) -> list[list[int]]:
        """Matching vertex cycles: edge ``i`` of a cycle runs from vertex ``i``
        to vertex ``(i+1) % len``."""
        return [list(c) for c in self._coast_vertex_cycles]

    def coastline_is_outer(self) -> list[bool]:
        """Per cycle: True for an outer coast, False for a lake shore."""
        return list(self._coast_outer)

    # ------------------------------------------------------------ serialisation
    def to_dict(self) -> dict[str, Any]:
        """Topology part of the protocol ``board`` message (plan §4.3). The
        generator adds terrain, tokens, fishing grounds and harbors."""
        return {
            "hexes": [{"id": i, "q": h[0], "r": h[1]} for i, h in enumerate(self.hexes)],
            "vertices": [
                {
                    "id": i, "q": v[0], "r": v[1], "c": v[2],
                    "hexes": list(self.vertex_hexes[i]),
                    "adj_v": list(self.vertex_neighbors[i]),
                    "adj_e": list(self.vertex_edges[i]),
                }
                for i, v in enumerate(self.vertices)
            ],
            "edges": [
                {"id": i, "v": list(self.edge_vertices[i]), "hexes": list(self.edge_hexes[i])}
                for i in range(len(self.edges))
            ],
        }


def sea_around(land: Iterable[Hex], margin: int) -> set[Hex]:
    """All non-land hexes within ``margin`` steps of some land hex."""
    land_set = set(land)
    sea: set[Hex] = set()
    for h in land_set:
        for radius in range(1, margin + 1):
            sea.update(n for n in coords.hex_ring(h, radius) if n not in land_set)
    return sea
