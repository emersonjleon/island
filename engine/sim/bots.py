"""Headless bots for simulations (WP8).

A bot looks at the full state (bots are trusted test players, not clients) and
returns raw intent dicts to try, in order. The runner applies them and ignores
rejects, so bots may be optimistic. Bots never touch ``state.rng``: each has its
own :class:`Rng`, so the game's randomness is the same with or without bots and
a game can be replayed from its command log alone.

* :class:`RandomBot` -- picks uniformly among legal moves.
* :class:`GreedyBot` -- prefers high-yield spots, cities over settlements over
  roads, saves for settlements and trades with the bank for what it lacks.
"""
from __future__ import annotations

from typing import Any

from engine.rng import Rng
from engine.rules import movement, placement, trade
from engine.settings.enums import BuildKind, Resource
from engine.state import GameState, Settler

__all__ = ["Bot", "RandomBot", "GreedyBot", "BOT_TYPES", "make_bot", "pips", "vertex_score"]

Intent = dict[str, Any]
SETTLEMENT, ROAD, CITY = BuildKind.SETTLEMENT, BuildKind.ROAD, BuildKind.CITY


def pips(token: int | None, state: GameState) -> int:
    """Number of dice combinations that roll ``token`` (integer, from the dice settings)."""
    if token is None:
        return 0
    n, sides = state.settings.clock.dice_count, state.settings.clock.dice_sides
    ways = {0: 1}
    for _ in range(n):
        nxt: dict[int, int] = {}
        for s, w in ways.items():
            for f in range(1, sides + 1):
                nxt[s + f] = nxt.get(s + f, 0) + w
        ways = nxt
    return ways.get(token, 0)


def vertex_score(state: GameState, v: int) -> int:
    gb = state.board
    return sum(pips(gb.token[h], state) for h in gb.board.vertex_hexes[v] if gb.hex_resource(h) is not None)


def _destination(s: Settler) -> int:
    if s.path:
        return s.path[-1]
    return s.step.to_v if s.step is not None else s.vertex


def _build(kind: BuildKind, target: int, settler: int | None = None) -> Intent:
    d: Intent = {"a": "build", "kind": kind.value}
    d["edge" if kind is ROAD else "vertex"] = target
    if settler is not None:
        d["settler"] = settler
    return d


class Bot:
    """Base bot: setup walking/building is shared; subclasses choose targets."""

    def __init__(self, seat: int, seed: int) -> None:
        self.seat = seat
        self.rng = Rng(seed)
        self.goal: int | None = None

    # --------------------------------------------------------------- choices
    def pick_vertex(self, state: GameState, options: list[int]) -> int:
        return self.rng.choice(options)

    def pick_road(self, state: GameState, options: list[int]) -> int:
        return self.rng.choice(options)

    def network(self, state: GameState) -> list[Intent]:
        raise NotImplementedError

    def _trade_for(self, state: GameState, kind: BuildKind, max_missing: int = 99) -> Intent | None:
        """A bank trade that brings ``kind`` one card closer, paid from surplus."""
        p = state.player(self.seat)
        cost = placement.cost_of(state, kind)
        missing = [r for r in Resource if cost[r] > p.hand[r]]
        if not missing or sum(cost[r] - p.hand[r] for r in missing) > max_missing:
            return None
        for g in sorted(Resource, key=lambda r: (-(p.hand[r] - cost[r]), r.value)):
            ratio = trade.best_ratio(state, self.seat, g)[0]
            if g not in missing and p.hand[g] - cost[g] >= ratio:
                want = max(missing, key=lambda r: (cost[r] - p.hand[r], -list(Resource).index(r)))
                if state.bank[want] > 0:
                    return {"a": "bank_trade", "give": {g.value: ratio}, "get": {want.value: 1}}
        return None

    # ----------------------------------------------------------------- setup
    def decide(self, state: GameState) -> list[Intent]:
        if state.phase == "finished":
            return []
        p = state.player(self.seat)
        if p.setup_done:
            return self.network(state)
        if any(c.seat == self.seat for c in state.constructions.values()):
            return []                        # keep the builder standing still
        if not p.settler_ids:
            return []
        s = state.settlers[p.settler_ids[0]]
        here = movement.settler_at_rest(state, s.id)
        roads_done = state.settings.setup.roads - p.setup_remaining.get(ROAD, 0)
        roads = placement.legal_targets(state, self.seat, ROAD) if (
            roads_done < p.setup_settlements_built or p.setup_remaining.get(SETTLEMENT, 0) == 0) else []
        if roads:
            at = [e for e in roads if here in state.board.board.edge_vertices[e]]
            if at:
                return [_build(ROAD, self.pick_road(state, at), s.id)]
            e = self.pick_road(state, roads)
            return [{"a": "move_settler", "settler": s.id, "to_vertex": state.board.board.edge_vertices[e][0]}]
        if roads_done < p.setup_settlements_built and not roads:
            t = self._trade_for(state, ROAD)
            return [] if t is None else [t]
        spots = placement.legal_targets(state, self.seat, SETTLEMENT)
        if not spots:
            t = self._trade_for(state, SETTLEMENT)
            return [] if t is None else [t]
        if self.goal not in spots:
            self.goal = self.pick_vertex(state, spots)
        if here == self.goal:
            return [_build(SETTLEMENT, self.goal, s.id)]
        if _destination(s) != self.goal:
            return [{"a": "move_settler", "settler": s.id, "to_vertex": self.goal, "mode": "replace"}]
        return []


class RandomBot(Bot):
    """Uniformly random legal setup spots and network builds; occasional random trades."""

    def network(self, state: GameState) -> list[Intent]:
        options = [(k, t) for k in (ROAD, SETTLEMENT, CITY) for t in placement.legal_targets(state, self.seat, k)]
        out: list[Intent] = []
        if options:
            k, t = self.rng.choice(options)
            out.append(_build(k, t))
        p = state.player(self.seat)
        give = [r for r in Resource if p.hand[r] >= trade.best_ratio(state, self.seat, r)[0]]
        if give and self.rng.randbelow(4) == 0:
            g = self.rng.choice(give)
            want = self.rng.choice([r for r in Resource if r is not g])
            ratio = trade.best_ratio(state, self.seat, g)[0]
            out.append({"a": "bank_trade", "give": {g.value: ratio}, "get": {want.value: 1}})
        return out


class GreedyBot(Bot):
    """Best-yield spots; city > settlement > road; trades for the missing resource."""

    def pick_vertex(self, state: GameState, options: list[int]) -> int:
        board = state.board.board
        contested = set()
        for c in state.constructions.values():
            if c.seat != self.seat and c.kind is SETTLEMENT:
                contested |= {c.target, *board.vertex_neighbors[c.target]}
        free = [v for v in options if v not in contested] or options
        best = max(vertex_score(state, v) for v in free)
        return self.rng.choice([v for v in free if vertex_score(state, v) == best])

    def _spot_score(self, state: GameState, v: int) -> int:
        if placement.settlement_error(state, self.seat, v, placement.NETWORK) is None:
            return vertex_score(state, v) * 2
        if v in state.buildings:
            return 0
        board = state.board.board
        if any(n in state.buildings for n in board.vertex_neighbors[v]) or not board.land_vertex(v):
            return 0
        return vertex_score(state, v)

    def pick_road(self, state: GameState, options: list[int]) -> int:
        board = state.board.board

        def score(e: int) -> int:
            return max(self._spot_score(state, v) for v in board.edge_vertices[e])
        best = max(score(e) for e in options)
        return self.rng.choice([e for e in options if score(e) == best])

    def network(self, state: GameState) -> list[Intent]:
        cities = placement.legal_targets(state, self.seat, CITY)
        if cities:
            return [_build(CITY, self.pick_vertex(state, cities))]
        spots = placement.legal_targets(state, self.seat, SETTLEMENT)
        if spots:
            return [_build(SETTLEMENT, self.pick_vertex(state, spots))]
        p = state.player(self.seat)
        board = state.board.board
        possible = p.pieces_left.get(SETTLEMENT, 0) > 0 and any(
            placement.settlement_error(state, self.seat, v, placement.NETWORK) is None for v in board.land_vertices)
        has_settlement = any(b.seat == self.seat and b.kind is SETTLEMENT for b in state.buildings.values())
        primary = SETTLEMENT if possible else ROAD
        roads = placement.legal_targets(state, self.seat, ROAD)
        building_road = any(c.seat == self.seat and c.kind is ROAD for c in state.constructions.values())
        if roads and not building_road and (primary is ROAD or p.hand_count > state.settings.robber.card_limit):
            return [_build(ROAD, self.pick_road(state, roads))]
        if has_settlement and p.pieces_left.get(CITY, 0) > 0:
            t = self._trade_for(state, CITY, max_missing=2)
            if t is not None:
                return [t]
        if primary is ROAD and p.pieces_left.get(ROAD, 0) <= 0:
            return []
        t = self._trade_for(state, primary)
        return [] if t is None else [t]


BOT_TYPES: dict[str, type[Bot]] = {"random": RandomBot, "greedy": GreedyBot}


def make_bot(kind: str, seat: int, seed: int) -> Bot:
    return BOT_TYPES[kind](seat, seed)
