"""State invariants checked after every simulation step (WP8).

:func:`violations` returns a list of short codes with details (empty when the
state is consistent); :func:`check` raises :class:`InvariantError` instead.
Conservation needs the per-resource total of the game, taken once with
:func:`resource_totals` right after ``new_game``.
"""
from __future__ import annotations

from engine.settings.enums import BuildKind, Resource
from engine.state import GameState

__all__ = ["InvariantError", "resource_totals", "violations", "check"]


class InvariantError(AssertionError):
    """The state broke an invariant (an engine bug)."""


def resource_totals(state: GameState) -> dict[Resource, int]:
    """bank + hands + escrow, per resource."""
    tot = {r: state.bank[r] for r in Resource}
    for p in state.players:
        for r in Resource:
            tot[r] += p.hand[r]
    for c in state.constructions.values():
        for r in Resource:
            tot[r] += c.paid.get(r, 0)
    return tot


def _conservation(state: GameState, totals: dict[Resource, int]) -> list[str]:
    out: list[str] = []
    now = resource_totals(state)
    for r in Resource:
        if now[r] != totals[r]:
            out.append(f"conservation.{r.value}: {now[r]} != {totals[r]}")
        if state.bank[r] < 0:
            out.append(f"bank.negative.{r.value}")
        for p in state.players:
            if p.hand[r] < 0:
                out.append(f"hand.negative.{p.seat}.{r.value}")
    return out


def _pieces(state: GameState) -> list[str]:
    out: list[str] = []
    cfg = state.settings.pieces
    limits = {BuildKind.ROAD: cfg.roads, BuildKind.SETTLEMENT: cfg.settlements, BuildKind.CITY: cfg.cities,
              BuildKind.MEGACITY: cfg.megacities}
    for p in state.players:
        used = {k: 0 for k in BuildKind}
        used[BuildKind.ROAD] = sum(1 for s in state.roads.values() if s == p.seat)
        for b in state.buildings.values():
            if b.seat == p.seat:
                used[b.kind] += 1
        for c in state.constructions.values():
            if c.seat == p.seat:
                used[c.kind] += 1
        for k in BuildKind:
            left = p.pieces_left.get(k, 0)
            if left < 0 or left + used[k] != limits[k]:
                out.append(f"pieces.{p.seat}.{k.value}: left {left} + used {used[k]} != {limits[k]}")
    return out


def _board(state: GameState) -> list[str]:
    out: list[str] = []
    board = state.board.board
    for v in state.buildings:
        for n in board.vertex_neighbors[v]:
            if n in state.buildings:
                out.append(f"distance_rule: {v}-{n}")
    # every road belongs to a component of own roads that touches an own building
    for seat in range(len(state.players)):
        own = {e for e, s in state.roads.items() if s == seat}
        anchored: set[int] = set()
        frontier = [v for v, b in state.buildings.items() if b.seat == seat]
        seen_v = set(frontier)
        while frontier:
            v = frontier.pop()
            for e in board.vertex_edges[v]:
                if e in own and e not in anchored:
                    anchored.add(e)
                    for w in board.edge_vertices[e]:
                        if w not in seen_v:
                            seen_v.add(w)
                            frontier.append(w)
        for e in sorted(own - anchored):
            out.append(f"road.unconnected.{seat}: {e}")
    return out


def _points(state: GameState) -> list[str]:
    out: list[str] = []
    bp = state.settings.victory.building_points
    for p in state.players:
        per = {BuildKind.SETTLEMENT: bp.settlement, BuildKind.CITY: bp.city, BuildKind.MEGACITY: bp.megacity}
        pts = sum(per[b.kind] for b in state.buildings.values() if b.seat == p.seat)
        if pts != p.points:
            out.append(f"points.{p.seat}: cached {p.points} != {pts}")
    if state.phase == "finished":
        if state.winner is None and any(p.points >= state.settings.victory.target for p in state.players):
            out.append("finished.no_winner")
    elif any(p.points >= state.settings.victory.target for p in state.players):
        out.append("target_reached.not_finished")
    return out


def _timers(state: GameState) -> list[str]:
    out: list[str] = []
    pending = state.timers.pending()
    if pending and state.timers.next_due() != pending[0].due_ms:
        out.append("scheduler.heap_order")
    if state.phase != "finished":
        due = state.timers.next_due()
        if due is not None and due < state.now_ms:
            out.append(f"scheduler.overdue: {due} < {state.now_ms}")
    for s in state.settlers.values():
        if s.step is not None and state.timers.get(s.timer_id) is None and state.phase != "finished":
            out.append(f"settler.no_timer: {s.id}")
        if s.id not in state.player(s.seat).settler_ids:
            out.append(f"settler.not_listed: {s.id}")
    for p in state.players:
        for sid in p.settler_ids:
            if sid not in state.settlers:
                out.append(f"settler.missing: {sid}")
    for c in state.constructions.values():
        if state.phase != "finished" and state.timers.get(c.timer_id) is None:
            out.append(f"construction.no_timer: {c.id}")
    return out


def violations(state: GameState, totals: dict[Resource, int]) -> list[str]:
    return [*_conservation(state, totals), *_pieces(state), *_board(state), *_points(state), *_timers(state)]


def check(state: GameState, totals: dict[Resource, int]) -> None:
    v = violations(state, totals)
    if v:
        raise InvariantError("; ".join(v))
