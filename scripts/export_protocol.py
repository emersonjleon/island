"""Export the protocol contract shared by Python and TypeScript (WP8).

Writes, under ``protocol/``:

* ``codes.json`` -- every code the client must translate: rule error codes
  (``errors``), event kinds (``events``), construction cancel reasons and
  production skip reasons (``reasons``). Collected by scanning the engine source
  (``RuleError("...")`` / ``_err("...")`` calls) plus the event registry.
* ``schema/{commands,events,settings}.schema.json`` -- JSON Schemas (TS types
  are generated from these).
* ``fixtures/*.json`` -- golden server messages from a short deterministic bot
  game on the fixed test board (``board``, ``state`` per viewer, ``events`` per
  viewer with one example of every event kind that viewer can receive, ``reject``).

Usage: ``python3 scripts/export_protocol.py`` (write) or ``--check`` (exit 1 if
the files on disk differ; CI runs this through the engine tests).
"""
from __future__ import annotations

import ast
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import views  # noqa: E402
from engine.commands import command_json_schema  # noqa: E402
from engine.errors import RuleError  # noqa: E402
from engine.events import EVENT_TYPES, event_json_schema  # noqa: E402
from engine.rules import production  # noqa: E402
from engine.settings import export_json_schema  # noqa: E402
from engine.sim.bots import make_bot  # noqa: E402
from engine.sim.runner import Simulation  # noqa: E402
from engine.tests.fixtures import make_seats, make_settings, standard_board  # noqa: E402

PROTOCOL = ROOT / "protocol"
ERROR_CALLS = {"RuleError", "_err"}
CANCEL_CALLS = {"cancel_construction": 2, "cancel_builder_constructions": 2}
FIXTURE_SEED = 3
FIXTURE_SEATS = 3


# ------------------------------------------------------------------- codes
def _call_name(node: ast.Call) -> str | None:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _str_arg(node: ast.Call, i: int) -> str | None:
    if len(node.args) > i and isinstance(node.args[i], ast.Constant) and isinstance(node.args[i].value, str):
        return node.args[i].value
    return None


def scan_codes() -> tuple[set[str], set[str]]:
    """(error codes, cancel reasons) found in the engine source (tests excluded)."""
    errors: set[str] = set()
    reasons: set[str] = set()
    engine = ROOT / "engine"
    for path in sorted(engine.rglob("*.py")):
        if "tests" in path.relative_to(engine).parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name in ERROR_CALLS and (code := _str_arg(node, 0)) is not None:
                errors.add(code)
            if name in CANCEL_CALLS and (r := _str_arg(node, CANCEL_CALLS[name])) is not None:
                reasons.add(r)
    return errors, reasons


def codes() -> dict[str, Any]:
    errors, cancel = scan_codes()
    skips = {getattr(production, n) for n in dir(production) if n.startswith("SKIP_")}
    return {
        "errors": sorted(errors),
        "events": sorted(EVENT_TYPES),
        "reasons": {"construction_cancelled": sorted(cancel), "produced_skipped": sorted(skips)},
    }


# ---------------------------------------------------------------- fixtures
def fixtures() -> dict[str, Any]:
    batches: list[list[Any]] = []
    sim = Simulation(make_settings(), make_seats(FIXTURE_SEATS), FIXTURE_SEED,
                     [make_bot("greedy", i, FIXTURE_SEED * 1000 + i) for i in range(FIXTURE_SEATS)],
                     board=standard_board(), on_events=batches.append)
    mid: dict[str, Any] | None = None
    while not sim.state.finished and sim.state.now_ms < 4 * 3600 * 1000:
        sim.step()
        if mid is None and sim.state.dice_history and len(sim.state.dice_history) >= 5:
            mid = {str(v): views.project_state(sim.state, v) for v in (0, None)}
    assert mid is not None
    out: dict[str, Any] = {
        "board.json": {"t": "board", **sim.state.board.to_dict()},
        "state_seat0.json": {"t": "state", "seq": 1, "now": mid["0"]["now"], "state": mid["0"]},
        "state_spectator.json": {"t": "state", "seq": 1, "now": mid["None"]["now"], "state": mid["None"]},
        "reject.json": {"t": "reject", "cid": "a19",
                        **RuleError("build.distance_rule", {"kind": "settlement", "target": 41}).to_dict()},
    }
    for viewer, name in ((0, "seat0"), (1, "seat1"), (None, "spectator")):
        first: dict[str, dict[str, Any]] = {}
        for batch in batches:
            for d in views.filter_events(batch, viewer, sim.state):
                key = d["k"] if d["k"] != "robber_stole" else f"robber_stole.{'own' if d['seat'] == viewer else 'other'}"
                first.setdefault(key, d)
        evs = [first[k] for k in sorted(first)]
        out[f"events_{name}.json"] = {"t": "events", "seq": 2, "now": sim.state.now_ms, "events": evs}
    return out


# ------------------------------------------------------------------ output
def build() -> dict[str, str]:
    """Relative path under ``protocol/`` -> file text."""
    def dumps(obj: Any) -> str:
        return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    files = {
        "codes.json": dumps(codes()),
        "schema/commands.schema.json": dumps(command_json_schema()),
        "schema/events.schema.json": dumps(event_json_schema()),
        "schema/settings.schema.json": dumps(export_json_schema()),
    }
    for name, obj in fixtures().items():
        files[f"fixtures/{name}"] = dumps(obj)
    return files


def stale(files: dict[str, str]) -> list[str]:
    return sorted(rel for rel, text in files.items()
                  if not (PROTOCOL / rel).exists() or (PROTOCOL / rel).read_text(encoding="utf-8") != text)


def main(argv: list[str]) -> int:
    files = build()
    if "--check" in argv:
        bad = stale(files)
        for rel in bad:
            print(f"stale: protocol/{rel}")
        return 1 if bad else 0
    for rel, text in files.items():
        path = PROTOCOL / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(f"wrote {len(files)} files to protocol/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
