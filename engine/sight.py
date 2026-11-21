"""What each player has seen of the island (Growing sight, hidden numbers).

Pure helpers shared by :mod:`engine.rules.visibility` (which keeps the record up
to date) and :mod:`engine.views` (which leaves out what a viewer has not seen).

Record, in ``state.ext["visibility"]`` (JSON-safe):

* ``seen``: ``{"<seat>": [hex ids, ascending]}``, hexes the seat has seen. It
  never shrinks. Kept only while fog is on (``visibility.map`` is not ``open``).
* ``sight`` (Live fog): ``{"<seat>": [hex ids]}``, the seat's land in sight after the
  last step, to tell when land comes into or goes out of sight.
* ``memory`` (Live fog): ``{"<seat>": {"b": {"<vertex>": [seat, kind]}, "r": {"<edge>": seat}}}``,
  other players' buildings and roads as the seat last saw them.
* ``numbers``: hex ids whose number token is shown, when ``visibility.hidden_numbers``
  is on: a token is shown once a building stands next to its hex.

Sight of ``r`` hexes around a piece: ``r = 1`` is the hexes the piece touches,
each step more adds their neighbours (``r = 0``: nothing). Sea hexes are seen too.
Settlers see while they stand still (Growing sight) or also while they walk
(Explored, Live fog). Spectators (``viewer=None``) see everything. A vertex or edge is seen when one of
its hexes is.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from engine.board.model import GeneratedBoard
from engine.settings.enums import BuildKind, MapVisibility
from engine.state import Construction, GameState, Settler

__all__ = [
    "EXT_KEY", "fog_on", "live_fog", "live_hexes", "memory", "numbers_hidden", "seen_hexes", "shown_numbers", "hexes_around",
    "vertex_sight", "edge_sight", "piece_sight", "settlers_reveal", "seat_sight",
    "seen_vertices", "seen_edges", "vertex_seen", "edge_seen", "construction_place_seen",
    "hex_view", "vertex_view", "edge_view", "board_for", "board_parts",
]

EXT_KEY = "visibility"


# ------------------------------------------------------------------ settings
def fog_on(state: GameState) -> bool:
    return state.settings.visibility.map is not MapVisibility.OPEN


def live_fog(state: GameState) -> bool:
    return state.settings.visibility.map is MapVisibility.LIVE_FOG


def numbers_hidden(state: GameState) -> bool:
    return bool(state.settings.visibility.hidden_numbers)


def _record(state: GameState) -> dict[str, Any]:
    return state.ext.get(EXT_KEY, {})


def seen_hexes(state: GameState, seat: int) -> frozenset[int]:
    """Hexes ``seat`` has seen (every hex when fog is off)."""
    if not fog_on(state):
        return frozenset(range(len(state.board.board.hexes)))
    return frozenset(_record(state).get("seen", {}).get(str(seat), ()))


def shown_numbers(state: GameState) -> frozenset[int]:
    """Hexes whose token is shown (every hex when numbers are not hidden)."""
    if not numbers_hidden(state):
        return frozenset(range(len(state.board.board.hexes)))
    return frozenset(_record(state).get("numbers", ()))


# ---------------------------------------------------------------------- sight
def hexes_around(gb: GeneratedBoard, start: Iterable[int], steps: int) -> set[int]:
    """``start`` plus every hex within ``steps`` neighbour steps of it."""
    seen = set(start)
    frontier = set(seen)
    nbrs = gb.board.hex_neighbors
    for _ in range(max(0, steps)):
        frontier = {n for h in frontier for n in nbrs[h]} - seen
        if not frontier:
            break
        seen |= frontier
    return seen


def vertex_sight(gb: GeneratedBoard, vertex: int, r: int) -> set[int]:
    return set() if r <= 0 else hexes_around(gb, gb.board.vertex_hexes[vertex], r - 1)


def edge_sight(gb: GeneratedBoard, edge: int, r: int) -> set[int]:
    return set() if r <= 0 else hexes_around(gb, gb.board.edge_hexes[edge], r - 1)


def piece_sight(state: GameState, kind: BuildKind, target: int) -> set[int]:
    """Hexes a finished piece of ``kind`` on ``target`` (edge for roads) sees."""
    sight = state.settings.visibility.sight
    if kind is BuildKind.ROAD:
        return edge_sight(state.board, target, sight.road)
    r = {BuildKind.SETTLEMENT: sight.settlement, BuildKind.CITY: sight.city,
         BuildKind.MEGACITY: sight.megacity}[kind]
    return vertex_sight(state.board, target, r)


def settlers_reveal(state: GameState, seat: int) -> bool:
    """Whether ``seat``'s settlers see land around them: always under fog (Emerson,
    Nov 19, 2026: you see the land around your settlers, buildings and roads)."""
    return state.settings.visibility.map is not MapVisibility.OPEN


def settler_sight(state: GameState, s: Settler) -> set[int]:
    """What a settler sees now: nothing while it walks under Growing sight (it reveals
    where it stops), else the hexes around its corner."""
    if state.settings.visibility.map is MapVisibility.GROWING and (s.step is not None or s.path):
        return set()
    return vertex_sight(state.board, s.vertex, state.settings.visibility.sight.settler)


def seat_sight(state: GameState, seat: int) -> set[int]:
    """Hexes in ``seat``'s sight now: around its buildings, roads and (when they
    reveal) settlers."""
    out: set[int] = set()
    for v, b in state.buildings.items():
        if b.seat == seat:
            out |= piece_sight(state, b.kind, v)
    for e, s in state.roads.items():
        if s == seat:
            out |= piece_sight(state, BuildKind.ROAD, e)
    if settlers_reveal(state, seat):
        for st in state.settlers.values():
            if st.seat == seat:
                out |= settler_sight(state, st)
    return out


def live_hexes(state: GameState, seat: int) -> frozenset[int]:
    """Hexes where ``seat`` sees what happens now: in sight under Live fog, else
    everything it has seen."""
    if live_fog(state) and state.phase != "finished":
        return frozenset(seat_sight(state, seat))
    return seen_hexes(state, seat)


def memory(state: GameState, seat: int) -> tuple[dict[int, tuple[int, str]], dict[int, int]]:
    """Other players' buildings (vertex -> (seat, kind)) and roads (edge -> seat) as
    ``seat`` last saw them (Live fog)."""
    m = _record(state).get("memory", {}).get(str(seat), {})
    return ({int(v): (int(s), str(k)) for v, (s, k) in m.get("b", {}).items()},
            {int(e): int(s) for e, s in m.get("r", {}).items()})


# ------------------------------------------------------------------- places
def seen_vertices(gb: GeneratedBoard, hexes: Iterable[int]) -> set[int]:
    hv = gb.board.hex_vertices
    return {v for h in hexes for v in hv[h]}


def seen_edges(gb: GeneratedBoard, hexes: Iterable[int]) -> set[int]:
    he = gb.board.hex_edges
    return {e for h in hexes for e in he[h]}


def vertex_seen(gb: GeneratedBoard, seen: frozenset[int], vertex: int) -> bool:
    return any(h in seen for h in gb.board.vertex_hexes[vertex])


def edge_seen(gb: GeneratedBoard, seen: frozenset[int], edge: int) -> bool:
    return any(h in seen for h in gb.board.edge_hexes[edge])


def construction_place_seen(gb: GeneratedBoard, seen: frozenset[int], c: Construction) -> bool:
    if c.kind is BuildKind.ROAD:
        return edge_seen(gb, seen, c.target)
    return vertex_seen(gb, seen, c.target)


# ------------------------------------------------------------- board views
def hex_view(gb: GeneratedBoard, h: int, numbers: frozenset[int]) -> dict[str, Any]:
    q, r = gb.board.hexes[h]
    t = gb.terrain[h]
    return {"id": h, "q": q, "r": r, "terrain": None if t is None else t.value,
            "token": gb.token[h] if h in numbers else None, "land": gb.board.is_land(h)}


def vertex_view(gb: GeneratedBoard, v: int, seen: frozenset[int]) -> dict[str, Any]:
    b = gb.board
    q, r, c = b.vertices[v]
    return {"id": v, "q": q, "r": r, "c": c, "hexes": [h for h in b.vertex_hexes[v] if h in seen],
            "adj_v": list(b.vertex_neighbors[v]), "adj_e": list(b.vertex_edges[v])}


def edge_view(gb: GeneratedBoard, e: int, seen: frozenset[int]) -> dict[str, Any]:
    b = gb.board
    return {"id": e, "v": list(b.edge_vertices[e]), "hexes": [h for h in b.edge_hexes[e] if h in seen]}


def board_parts(gb: GeneratedBoard, hexes: Iterable[int], seen: frozenset[int],
                numbers: frozenset[int]) -> dict[str, Any]:
    """Board pieces touching ``hexes``, as ``viewer`` (who has ``seen``) may know them.
    Hexes, vertices and edges list only seen hexes, so unseen land does not show."""
    hex_ids = sorted(set(hexes))
    verts = sorted(seen_vertices(gb, hex_ids))
    edges = sorted(seen_edges(gb, hex_ids))
    edge_set = set(edges)
    hex_set = set(hex_ids)
    return {
        "hexes": [hex_view(gb, h, numbers) for h in hex_ids],
        "vertices": [vertex_view(gb, v, seen) for v in verts],
        "edges": [edge_view(gb, e, seen) for e in edges],
        "fishing": [{"hex": h, "token": gb.token[h] if h in numbers else None}
                    for h in sorted(gb.fishing) if h in hex_set],
        "harbors": [{"edge": hb.edge, "vertices": list(hb.vertices),
                     "resource": None if hb.resource is None else hb.resource.value, "ratio": hb.ratio}
                    for hb in gb.harbors if hb.edge in edge_set],
    }


def board_for(state: GameState, viewer: int | None) -> dict[str, Any]:
    """The protocol ``board`` payload for ``viewer``: the whole board for spectators
    and open maps; otherwise only seen hexes (and the vertices, edges, fishing
    grounds and harbors on them), with hidden tokens as ``None``."""
    gb = state.board
    if viewer is None or not (fog_on(state) or numbers_hidden(state)):
        return gb.to_dict()
    seen = seen_hexes(state, viewer)
    out = board_parts(gb, seen, seen, shown_numbers(state))
    out["robber_start"] = gb.robber_start if gb.robber_start in seen else None
    out["partial"] = fog_on(state) and state.phase != "finished"
    return out
