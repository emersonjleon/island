"""Per-viewer projections of the state and of event batches.

``viewer`` is a seat number, or ``None`` for a spectator. Stage 1 shows the whole
map (open map); only hands (``settings.visibility.hands``) and, with
``scores=hidden_until_end``, other players' points are redacted. Fog of war
(later stages) plugs in here.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from engine.events import Event
from engine.settings.enums import InfoVisibility, Resource, ScoreVisibility
from engine.settings.models import VisibilitySettings
from engine.state import Construction, GameState, PlayerState, Settler

__all__ = ["project_state", "filter_events", "register_buildable_provider", "BuildableProvider"]

BuildableProvider = Callable[[GameState, int], dict[str, list[int]]]
_buildable_provider: BuildableProvider | None = None


def register_buildable_provider(fn: BuildableProvider | None) -> None:
    """Placement registers ``fn(state, seat) -> {"roads", "settlements", "cities"}``.
    ``None`` unregisters. Without a provider, ``state.buildable_cache[seat]`` is used."""
    global _buildable_provider
    _buildable_provider = fn


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


def _settler_view(s: Settler) -> dict[str, Any]:
    st = s.step
    return {"id": s.id, "seat": s.seat, "vertex": s.vertex, "path": list(s.path),
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


def project_state(state: GameState, viewer: int | None) -> dict[str, Any]:
    """The ``state`` payload of the protocol for ``viewer`` (JSON-safe)."""
    out: dict[str, Any] = {
        "viewer": viewer,
        "phase": state.phase,
        "now": state.now_ms,
        "clock_started": state.clock_started,
        "next_roll_at": state.next_roll_at,
        "last_roll": None if state.last_roll is None else list(state.last_roll),
        "dice_history": list(state.dice_history),
        "bank": _res(state.bank),
        "robber": state.robber_hex,
        "buildings": [{"vertex": v, "seat": b.seat, "kind": b.kind.value}
                      for v, b in sorted(state.buildings.items())],
        "roads": [{"edge": e, "seat": s} for e, s in sorted(state.roads.items())],
        "settlers": [_settler_view(s) for _, s in sorted(state.settlers.items())],
        "constructions": [_construction_view(c) for _, c in sorted(state.constructions.items())],
        "players": [_player_view(state, p, viewer) for p in state.players],
        "winner": state.winner,
        "finished_at": state.finished_at,
    }
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
    out: list[dict[str, Any]] = []
    for ev in events:
        d = ev.view_for(viewer, vis)
        if d is not None:
            out.append(d)
    return out
