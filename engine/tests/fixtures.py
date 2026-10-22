"""Reusable test fixtures: a fixed standard board and seat lists.

``standard_board()`` is a deterministic 19-hex spiral island with sea margin 1
(37 hexes, land ids 0..18), fixed terrain and tokens, two fishing grounds and two
harbors. It does not depend on ``engine.board.generator``.
"""
from __future__ import annotations

from typing import Any

from engine.board.model import GeneratedBoard, Harbor
from engine.board.topology import Board
from engine.settings import GameSettings, parse_settings
from engine.settings.enums import Resource, Terrain
from engine.state import SeatInfo

__all__ = ["standard_board", "make_seats", "make_settings", "DESERT_HEX", "FISHING", "COLOURS"]

F, P, A, H, M, D = (Terrain.FOREST, Terrain.PASTURE, Terrain.FIELDS, Terrain.HILLS, Terrain.MOUNTAINS,
                    Terrain.DESERT)
# Terrain per land hex id (ids are land hexes sorted by (q, r)); the desert is (0, 0).
_TERRAIN_BY_KEY_ORDER = (F, P, A, H, M, F, P, A, H, D, M, F, P, A, H, M, F, P, A)
_TOKENS = (5, 2, 6, 3, 8, 10, 9, 12, 11, 4, 8, 10, 9, 4, 5, 6, 3, 11)
_FISHING_TOKENS = (4, 10)
COLOURS = ("red", "blue", "white", "orange", "green", "brown")


def standard_board() -> GeneratedBoard:
    board = Board.spiral_island(19, sea_margin=1)
    land = board.land_hex_count
    assert land == 19 and board.hexes[9] == (0, 0)
    terrain: list[Terrain | None] = list(_TERRAIN_BY_KEY_ORDER) + [None] * (len(board.hexes) - land)
    tokens: list[int | None] = [None] * len(board.hexes)
    it = iter(_TOKENS)
    for h in range(land):
        if terrain[h] is not Terrain.DESERT:
            tokens[h] = next(it)
    fishing = (board.sea_hex_ids[0], board.sea_hex_ids[9])
    for h, tok in zip(fishing, _FISHING_TOKENS):
        tokens[h] = tok
    cycle = board.coastline_cycles()[0]
    harbors = []
    for e, res, ratio in ((cycle[0], None, 3), (cycle[6], Resource.LUMBER, 2)):
        a, b = board.edge_vertices[e]
        harbors.append(Harbor(edge=e, vertices=(a, b), resource=res, ratio=ratio))
    return GeneratedBoard(board=board, terrain=tuple(terrain), token=tuple(tokens),
                          fishing=frozenset(fishing), harbors=tuple(harbors), robber_start=9)


DESERT_HEX = 9
FISHING = standard_board().fishing


def make_seats(n: int = 3) -> list[SeatInfo]:
    return [SeatInfo(seat=i, user_id=100 + i, name=f"p{i}", colour=COLOURS[i]) for i in range(n)]


def make_settings(overrides: dict[str, Any] | None = None) -> GameSettings:
    """Classic defaults plus ``overrides`` (nested dict)."""
    return parse_settings(overrides or {})
