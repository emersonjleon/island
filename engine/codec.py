"""``GameState`` <-> JSON-safe dict, and a canonical state hash.

``load(dump(s))`` restores everything: settings, the full generated board, RNG
state, timers (with their id/seq counters), id counters and ``ext``. Dict keys
that are ints (vertex/edge/settler ids, seats) become lists of records or string
keys and are converted back on load. ``state_hash`` is the sha256 of the
canonical JSON (sorted keys, compact separators).
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from engine.board.model import GeneratedBoard, Harbor
from engine.board.topology import Board
from engine.rng import Rng
from engine.scheduler import Scheduler
from engine.settings.enums import STAGE_LATER, BuildKind, Resource, Terrain
from engine.settings.models import GameSettings
from engine.state import (
    Building, Construction, GameState, PlayerState, SeatInfo, Settler, SettlerStep,
)

__all__ = ["dump", "load", "state_hash", "canonical_json", "dump_board", "load_board", "CODEC_VERSION"]

CODEC_VERSION = 1


def _res(m: dict[Resource, int]) -> dict[str, int]:
    return {r.value: int(m[r]) for r in Resource if r in m}


def _unres(d: dict[str, int]) -> dict[Resource, int]:
    return {Resource(k): int(v) for k, v in d.items()}


def _kinds(m: dict[BuildKind, int]) -> dict[str, int]:
    return {k.value: int(v) for k, v in m.items()}


def _unkinds(d: dict[str, int]) -> dict[BuildKind, int]:
    return {BuildKind(k): int(v) for k, v in d.items()}


# ----------------------------------------------------------------------- board
def dump_board(gb: GeneratedBoard) -> dict[str, Any]:
    b = gb.board
    n = b.land_hex_count
    return {
        "land": [list(h) for h in b.hexes[:n]],
        "sea": [list(h) for h in b.hexes[n:]],
        "terrain": [None if t is None else t.value for t in gb.terrain],
        "token": list(gb.token),
        "fishing": sorted(gb.fishing),
        "harbors": [{"edge": h.edge, "vertices": list(h.vertices),
                     "resource": None if h.resource is None else h.resource.value, "ratio": h.ratio}
                    for h in gb.harbors],
        "robber_start": gb.robber_start,
    }


def load_board(d: dict[str, Any]) -> GeneratedBoard:
    board = Board([tuple(h) for h in d["land"]], [tuple(h) for h in d["sea"]])
    return GeneratedBoard(
        board=board,
        terrain=tuple(None if t is None else Terrain(t) for t in d["terrain"]),
        token=tuple(d["token"]),
        fishing=frozenset(d["fishing"]),
        harbors=tuple(Harbor(edge=h["edge"], vertices=(h["vertices"][0], h["vertices"][1]),
                             resource=None if h["resource"] is None else Resource(h["resource"]),
                             ratio=h["ratio"]) for h in d["harbors"]),
        robber_start=d["robber_start"],
    )


# ---------------------------------------------------------------------- pieces
def _dump_player(p: PlayerState) -> dict[str, Any]:
    i = p.info
    return {
        "seat": p.seat,
        "info": {"seat": i.seat, "user_id": i.user_id, "name": i.name, "colour": i.colour},
        "hand": _res(p.hand), "pieces_left": _kinds(p.pieces_left), "setup_remaining": _kinds(p.setup_remaining),
        "setup_done": p.setup_done, "last_setup_settlement": p.last_setup_settlement,
        "setup_settlements_built": p.setup_settlements_built, "points": p.points,
        "settler_ids": list(p.settler_ids),
    }


def _load_player(d: dict[str, Any]) -> PlayerState:
    return PlayerState(
        seat=d["seat"], info=SeatInfo(**d["info"]), hand=_unres(d["hand"]),
        pieces_left=_unkinds(d["pieces_left"]), setup_remaining=_unkinds(d["setup_remaining"]),
        setup_done=d["setup_done"], last_setup_settlement=d["last_setup_settlement"],
        setup_settlements_built=d["setup_settlements_built"], points=d["points"],
        settler_ids=list(d["settler_ids"]),
    )


def _dump_settler(s: Settler) -> dict[str, Any]:
    st = s.step
    return {"id": s.id, "seat": s.seat, "vertex": s.vertex, "path": list(s.path), "timer_id": s.timer_id,
            "step": None if st is None else
            {"edge": st.edge, "from_v": st.from_v, "to_v": st.to_v, "t0": st.t0, "t1": st.t1}}


def _load_settler(d: dict[str, Any]) -> Settler:
    st = d["step"]
    return Settler(id=d["id"], seat=d["seat"], vertex=d["vertex"], path=list(d["path"]),
                   step=None if st is None else SettlerStep(**st), timer_id=d["timer_id"])


def _dump_construction(c: Construction) -> dict[str, Any]:
    return {"id": c.id, "seat": c.seat, "kind": c.kind.value, "target": c.target, "builder": c.builder,
            "paid": _res(c.paid), "started_ms": c.started_ms, "done_ms": c.done_ms, "setup": c.setup,
            "timer_id": c.timer_id}


def _load_construction(d: dict[str, Any]) -> Construction:
    return Construction(id=d["id"], seat=d["seat"], kind=BuildKind(d["kind"]), target=d["target"],
                        builder=d["builder"], paid=_unres(d["paid"]), started_ms=d["started_ms"],
                        done_ms=d["done_ms"], setup=d["setup"], timer_id=d["timer_id"])


# ----------------------------------------------------------------------- state
def dump(state: GameState) -> dict[str, Any]:
    """JSON-safe dict of the whole state (no shared references to the live state)."""
    return {
        "codec": CODEC_VERSION,
        "settings": state.settings.model_dump(mode="json"),
        "board": dump_board(state.board),
        "rng": state.rng.state,
        "seed": state.seed,
        "now_ms": state.now_ms,
        "phase": state.phase,
        "players": [_dump_player(p) for p in state.players],
        "bank": _res(state.bank),
        "buildings": [{"vertex": v, "seat": b.seat, "kind": b.kind.value}
                      for v, b in sorted(state.buildings.items())],
        "roads": [{"edge": e, "seat": s} for e, s in sorted(state.roads.items())],
        "settlers": [_dump_settler(s) for _, s in sorted(state.settlers.items())],
        "constructions": [_dump_construction(c) for _, c in sorted(state.constructions.items())],
        "robber_hex": state.robber_hex,
        "clock_started": state.clock_started,
        "next_roll_at": state.next_roll_at,
        "roll_timer_id": state.roll_timer_id,
        "last_roll": None if state.last_roll is None else list(state.last_roll),
        "dice_history": list(state.dice_history),
        "timers": copy.deepcopy(state.timers.to_dict()),
        "id_counters": dict(state.id_counters),
        "winner": state.winner,
        "finished_at": state.finished_at,
        "buildable_cache": {str(seat): copy.deepcopy(v) for seat, v in sorted(state.buildable_cache.items())},
        "ext": copy.deepcopy(state.ext),
    }


def load(d: dict[str, Any]) -> GameState:
    """Rebuild a ``GameState`` from :func:`dump` output (also after a JSON round trip)."""
    if d.get("codec") != CODEC_VERSION:
        raise ValueError(f"unsupported codec version {d.get('codec')!r}")
    # The settings were validated when the game was created; do not re-apply the stage gate.
    settings = GameSettings.model_validate(d["settings"], context={"implemented_stage": STAGE_LATER})
    return GameState(
        settings=settings,
        board=load_board(d["board"]),
        rng=Rng.from_state(d["rng"]),
        seed=d["seed"],
        players=[_load_player(p) for p in d["players"]],
        bank=_unres(d["bank"]),
        now_ms=d["now_ms"],
        phase=d["phase"],
        buildings={b["vertex"]: Building(b["seat"], BuildKind(b["kind"])) for b in d["buildings"]},
        roads={r["edge"]: r["seat"] for r in d["roads"]},
        settlers={s["id"]: _load_settler(s) for s in d["settlers"]},
        constructions={c["id"]: _load_construction(c) for c in d["constructions"]},
        robber_hex=d["robber_hex"],
        clock_started=d["clock_started"],
        next_roll_at=d["next_roll_at"],
        roll_timer_id=d["roll_timer_id"],
        last_roll=None if d["last_roll"] is None else list(d["last_roll"]),
        dice_history=list(d["dice_history"]),
        timers=Scheduler.from_dict(copy.deepcopy(d["timers"])),
        id_counters=dict(d["id_counters"]),
        winner=d["winner"],
        finished_at=d["finished_at"],
        buildable_cache={int(k): copy.deepcopy(v) for k, v in d["buildable_cache"].items()},
        ext=copy.deepcopy(d["ext"]),
    )


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def state_hash(state: GameState) -> str:
    """sha256 hex digest of the canonical JSON of :func:`dump`."""
    return hashlib.sha256(canonical_json(dump(state)).encode("utf-8")).hexdigest()
