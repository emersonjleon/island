"""The generated board: topology plus terrain, number tokens, fishing grounds and harbors.

Produced by `engine.board.generator.generate_board` and stored (immutable) in the game state.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from engine.board.topology import Board
from engine.settings.enums import TERRAIN_RESOURCE, Resource, Terrain


@dataclass(frozen=True)
class Harbor:
    edge: int                      # coastal edge id
    vertices: tuple[int, int]      # the edge's two vertex ids (a building on either uses the harbor)
    resource: Resource | None      # None = generic harbor
    ratio: int                     # e.g. 3 for generic, 2 for specific


@dataclass(frozen=True)
class GeneratedBoard:
    board: Board
    terrain: tuple[Terrain | None, ...]   # per hex id; None for sea hexes
    token: tuple[int | None, ...]         # per hex id; set for producing land hexes and fishing grounds
    fishing: frozenset[int]               # hex ids of fishing grounds (sea hexes that produce fish)
    harbors: tuple[Harbor, ...]
    robber_start: int | None              # hex id, None if the board has no robber start
    vertex_harbor: tuple[int | None, ...] = field(init=False)  # per vertex id: index into harbors

    def __post_init__(self) -> None:
        vh: list[int | None] = [None] * len(self.board.vertices)
        for i, h in enumerate(self.harbors):
            for v in h.vertices:
                vh[v] = i
        object.__setattr__(self, "vertex_harbor", tuple(vh))

    def hex_resource(self, hex_id: int) -> Resource | None:
        """Resource a hex produces (fish for fishing grounds), or None."""
        if hex_id in self.fishing:
            return Resource.FISH
        t = self.terrain[hex_id]
        return None if t is None else TERRAIN_RESOURCE.get(t)

    def producing_hexes(self, roll: int) -> tuple[int, ...]:
        """Hex ids (land and fishing grounds) whose token equals `roll`, ascending."""
        return tuple(h for h, tok in enumerate(self.token) if tok == roll and self.hex_resource(h) is not None)

    def to_dict(self) -> dict:
        """Protocol `board` payload (see docs/STAGE1_PLAN.md §4.3)."""
        d = self.board.to_dict()
        for hx in d["hexes"]:
            i = hx["id"]
            t = self.terrain[i]
            hx["terrain"] = None if t is None else t.value
            hx["token"] = self.token[i]
            hx["land"] = self.board.is_land(i)
        d["fishing"] = [{"hex": h, "token": self.token[h]} for h in sorted(self.fishing)]
        d["harbors"] = [
            {"edge": h.edge, "vertices": list(h.vertices),
             "resource": None if h.resource is None else h.resource.value, "ratio": h.ratio}
            for h in self.harbors
        ]
        d["robber_start"] = self.robber_start
        return d
