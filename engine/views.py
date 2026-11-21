"""Per-viewer projections of the state and of event batches.

``viewer`` is a seat number, or ``None`` for a spectator. Hands
(``settings.visibility.hands``) and, with ``scores=hidden_until_end``, other
players' points are redacted. With fog (``visibility.map`` not ``open``, see
:mod:`engine.sight`) a player is not told about other players' buildings, roads,
settlers, constructions or the robber on hexes they have not seen; their own
pieces always show. Spectators see everything.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from engine import sight
from engine.events import Event
from engine.settings.enums import BuildKind, InfoVisibility, Resource, ScoreVisibility
from engine.settings.models import VisibilitySettings
from engine.state import Construction, GameState, PlayerState, Settler

__all__ = ["project_state", "filter_events", "register_buildable_provider", "BuildableProvider",
           "register_state_extension", "StateExtension", "board_for", "pieces_view", "viewer_seen", "viewer_live"]

board_for = sight.board_for

BuildableProvider = Callable[[GameState, int], dict[str, list[int]]]
_buildable_provider: BuildableProvider | None = None


def register_buildable_provider(fn: BuildableProvider | None) -> None:
    """Placement registers ``fn(state, seat) -> {"roads", "settlements", "cities"}``.
    ``None`` unregisters. Without a provider, ``state.buildable_cache[seat]`` is used."""
    global _buildable_provider
    _buildable_provider = fn


StateExtension = Callable[[GameState, int | None], dict[str, Any]]
_extensions: dict[str, StateExtension] = {}


def register_state_extension(name: str, fn: StateExtension | None) -> None:
    """A rule module adds ``fn(state, viewer) -> dict`` under ``name`` in the state
    projection (rules import views, so views cannot import them). ``None`` removes it."""
    if fn is None:
        _extensions.pop(name, None)
    else:
        _extensions[name] = fn


def _res(m: dict[Resource, int]) -> dict[str, int]:
    return {r.value: m[r] for r in Resource if r in m}


def _player_view(state: GameState, p: PlayerState, viewer: int | None) -> dict[str, Any]:
    vis = state.settings.visibility
    d: dict[str, Any] = {
        "seat": p.seat, "name": p.info.name, "colour": p.info.colour,
        "pieces": {k.value: v for k, v in p.pieces_left.items()},
        "setup": {"remaining": {k.value: v for k, v in p.setup_remaining.items()}, "done": p.setup_done,
                  "settlements_built": p.setup_settlements_built},
        "settlers": list(p.settler_ids),
        "resigned": p.resigned,
    }
    own = viewer is not None and viewer == p.seat
    if own or vis.hands is InfoVisibility.OPEN:
        d["hand"] = _res(p.hand)
        d["hand_count"] = p.hand_count
    elif vis.hands is InfoVisibility.COUNTS:
        d["hand_count"] = p.hand_count
    if own or vis.scores is ScoreVisibility.SHOWN or state.phase == "finished":
        d["points"] = p.points
    return d


def _settler_view(s: Settler, own: bool = True) -> dict[str, Any]:
    """``own=False`` (another player's settler under fog): the queued path is left out."""
    st = s.step
    return {"id": s.id, "seat": s.seat, "vertex": s.vertex, "path": list(s.path) if own else [],
            "step": None if st is None else
            {"edge": st.edge, "from_v": st.from_v, "to_v": st.to_v, "t0": st.t0, "t1": st.t1}}


def _construction_view(c: Construction) -> dict[str, Any]:
    return {"id": c.id, "seat": c.seat, "kind": c.kind.value, "target": c.target, "builder": c.builder,
            "t0": c.started_ms, "t1": c.done_ms, "paid": _res(c.paid), "setup": c.setup}


def _buildable(state: GameState, viewer: int) -> dict[str, list[int]] | None:
    if _buildable_provider is not None:
        return _buildable_provider(state, viewer)
    cached = state.buildable_cache.get(viewer)
    return None if cached is None else dict(cached)


def _longest_road_view(state: GameState) -> dict[str, Any]:
    """Holder and road lengths (kept by rules.longest_road in ``ext``; read here without
    importing the rules, which import this module)."""
    lr = state.ext.get("longest_road", {})
    return {"holder": lr.get("holder"), "lengths": dict(sorted(lr.get("lengths", {}).items(), key=lambda kv: int(kv[0])))}


def viewer_seen(state: GameState, viewer: int | None) -> frozenset[int] | None:
    """Hexes ``viewer`` has seen, or None when they see everything (spectator, no fog)."""
    if viewer is None or not sight.fog_on(state) or not state.has_seat(viewer):
        return None
    return sight.seen_hexes(state, viewer)


def viewer_live(state: GameState, viewer: int | None) -> frozenset[int] | None:
    """Hexes where ``viewer`` sees what happens now (Live fog: in sight; else seen),
    or None when they see everything."""
    if viewer is None or not sight.fog_on(state) or not state.has_seat(viewer):
        return None
    return sight.live_hexes(state, viewer)


def _remembered(state: GameState, viewer: int, live: frozenset[int]) -> dict[str, Any]:
    """Live fog: own buildings and roads, others' in sight now, and others' elsewhere
    as ``viewer`` last saw them."""
    gb = state.board
    mem_b, mem_r = sight.memory(state, viewer)
    buildings = {v: (b.seat, b.kind.value) for v, b in state.buildings.items()
                 if b.seat == viewer or sight.vertex_seen(gb, live, v)}
    for v, sk in mem_b.items():
        if not sight.vertex_seen(gb, live, v):
            buildings[v] = sk
    roads = {e: s for e, s in state.roads.items() if s == viewer or sight.edge_seen(gb, live, e)}
    for e, s in mem_r.items():
        if not sight.edge_seen(gb, live, e):
            roads[e] = s
    return {"buildings": [{"vertex": v, "seat": s, "kind": k} for v, (s, k) in sorted(buildings.items())],
            "roads": [{"edge": e, "seat": s} for e, s in sorted(roads.items())]}


def pieces_view(state: GameState, viewer: int | None, seen: frozenset[int] | None) -> dict[str, Any]:
    """Buildings, roads, settlers, constructions and the robber that ``viewer`` may
    see; ``seen=None``: all of them. Own pieces always show. ``seen`` is where the
    viewer sees what happens now (:func:`viewer_live`); under Live fog buildings and
    roads elsewhere come from what the viewer remembers."""
    gb = state.board

    def shows(seat: int, ok: bool) -> bool:
        return seen is None or seat == viewer or ok

    out = {
        "robber": state.robber_hex if seen is None or state.robber_hex in seen else None,
        "buildings": [{"vertex": v, "seat": b.seat, "kind": b.kind.value}
                      for v, b in sorted(state.buildings.items())
                      if shows(b.seat, seen is not None and sight.vertex_seen(gb, seen, v))],
        "roads": [{"edge": e, "seat": s} for e, s in sorted(state.roads.items())
                  if shows(s, seen is not None and sight.edge_seen(gb, seen, e))],
        "settlers": [_settler_view(st, own=seen is None or st.seat == viewer)
                     for _, st in sorted(state.settlers.items())
                     if shows(st.seat, seen is not None and sight.vertex_seen(gb, seen, st.vertex))],
        "constructions": [_construction_view(c) for _, c in sorted(state.constructions.items())
                          if shows(c.seat, seen is not None and sight.construction_place_seen(gb, seen, c))],
    }
    if seen is not None and viewer is not None and viewer >= 0 and sight.live_fog(state) and state.phase != "finished":
        out.update(_remembered(state, viewer, seen))
    return out


def _visibility_view(state: GameState, viewer: int | None) -> dict[str, Any]:
    vis = state.settings.visibility
    out: dict[str, Any] = {"map": vis.map.value, "hidden_numbers": vis.hidden_numbers}
    if viewer is not None and state.has_seat(viewer) and sight.fog_on(state):
        out["seen"] = sorted(sight.seen_hexes(state, viewer))
        out["in_sight"] = sorted(sight.seat_sight(state, viewer))
    return out


def project_state(state: GameState, viewer: int | None) -> dict[str, Any]:
    """The ``state`` payload of the protocol for ``viewer`` (JSON-safe)."""
    pieces = pieces_view(state, viewer, viewer_live(state, viewer))
    out: dict[str, Any] = {
        "viewer": viewer,
        "phase": state.phase,
        "now": state.now_ms,
        "clock_started": state.clock_started,
        "next_roll_at": state.next_roll_at,
        "last_roll": None if state.last_roll is None else list(state.last_roll),
        "dice_history": list(state.dice_history),
        "bank": _res(state.bank),
        **pieces,
        "players": [_player_view(state, p, viewer) for p in state.players],
        "winner": state.winner,
        "finished_at": state.finished_at,
        "end_reason": state.ext.get("victory", {}).get("reason", "target") if state.phase == "finished" else None,
        "longest_road": _longest_road_view(state),
        "visibility": _visibility_view(state, viewer),
    }
    for name, fn in sorted(_extensions.items()):
        out[name] = fn(state, viewer)
    if viewer is not None and state.has_seat(viewer):
        b = _buildable(state, viewer)
        if b is not None:
            out["buildable"] = b
    return out


def filter_events(events: Iterable[Event], viewer: int | None,
                  state: GameState | None = None) -> list[dict[str, Any]]:
    """JSON dicts of ``events`` as ``viewer`` may see them (redacted or dropped).
    Visibility settings come from ``state`` (defaults when ``state`` is None)."""
    vis = state.settings.visibility if state is not None else VisibilitySettings()
    seen = viewer_seen(state, viewer) if state is not None else None
    live = viewer_live(state, viewer) if state is not None else None
    numbers_seen = (state is not None and viewer is not None and state.has_seat(viewer)
                    and sight.numbers_hidden(state))
    out: list[dict[str, Any]] = []
    for ev in events:
        d = ev.view_for(viewer, vis)
        if d is not None and state is not None and (seen is not None or numbers_seen):
            d = _place_filter(state, ev, d, viewer, seen, live)
        if d is not None:
            out.append(d)
    return out


def _settler_seat(state: GameState, d: dict[str, Any]) -> int | None:
    if "seat" in d:
        return d["seat"]
    st = state.settlers.get(d.get("settler", -1))
    return None if st is None else st.seat


def _place_filter(state: GameState, ev: Event, d: dict[str, Any], viewer: int | None,
                  known: frozenset[int] | None, seen: frozenset[int] | None) -> dict[str, Any] | None:
    """Drop or trim an event about a place ``viewer`` does not see now (``seen``, from
    :func:`viewer_live`; None: everywhere). Numbers follow the land ever seen (``known``)."""
    gb = state.board
    k = d["k"]
    if k == "numbers_revealed":
        if known is None:
            return d
        tokens = {h: t for h, t in d["tokens"].items() if int(h) in known}
        return {**d, "tokens": tokens} if tokens else None
    if seen is None or d.get("seat") == viewer:
        return d
    if k in ("settler_landed", "settler_arrived", "settler_path", "settler_step"):
        if _settler_seat(state, d) == viewer:
            return d
        if k == "settler_path":
            return None
        if k == "settler_step":
            return d if sight.edge_seen(gb, seen, d["edge"]) else None
        return d if sight.vertex_seen(gb, seen, d["vertex"]) else None
    if k in ("construction_started", "built"):
        kind = BuildKind(d["kind"])
        ok = (sight.edge_seen(gb, seen, d["target"]) if kind is BuildKind.ROAD
              else sight.vertex_seen(gb, seen, d["target"]))
        return d if ok else None
    if k == "robber_moved":
        from_ok = d["from_hex"] in seen
        to_ok = d["to_hex"] in seen
        if not (from_ok or to_ok):
            return None
        return {**d, "from_hex": d["from_hex"] if from_ok else None, "to_hex": d["to_hex"] if to_ok else None}
    if k == "dev_card_played" and d.get("hex") is not None and d["hex"] not in seen:
        return {**d, "hex": None}
    return d
