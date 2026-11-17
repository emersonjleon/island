"""Scale a preset to a bigger table: more players get a bigger island and bank.

Presets are written for ``players.sized_for`` players (4 in Classic). When a game
has more players and ``players.scale_for_more`` is on, :func:`scale_for_players`
multiplies, by ``players / sized_for`` and rounding up (integer maths):

* ``board.land_hexes`` (only when neither ``land_hexes``, ``terrain_counts`` nor
  ``number_tokens`` was given explicitly). Terrain, tokens, fishing grounds and
  generic harbors then follow through the usual auto counts (``resolve``).
* every ``economy.bank.per_resource`` count (unless the bank was given explicitly).

``explicit`` names the values that were given explicitly (a host's overrides);
by default that is all of ``raw``. A preset's own ``land_hexes`` or bank, written
for its ``sized_for`` players, is not explicit when ``load_preset`` scales it: it
is the starting point that gets multiplied.

The development deck is not scaled yet: its settings group is a stage 2 setting
and non-default values are refused while ``IMPLEMENTED_STAGE`` is 1.

It works on the raw (unvalidated) settings dict, before validation, because the
unscaled settings of a big game would not validate (the bank could not pay the
starting materials). Values given explicitly always win.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from .models import BankSettings, BoardSettings, PlayersSettings

__all__ = ["scale_for_players", "scaled_count"]

_MAX_LAND_HEXES = 250
_MAX_BANK = 1000
_BOARD_KEYS = ("land_hexes", "terrain_counts", "number_tokens")


def scaled_count(value: int, players: int, sized_for: int, cap: int) -> int:
    """``value * players / sized_for`` rounded up, at most ``cap`` (never below ``value``)."""
    return min(cap, max(value, -(-value * players // sized_for)))


def _default(model: type, name: str) -> Any:
    field = model.model_fields[name]
    if field.default_factory is not None:
        return field.default_factory()
    return field.default


def _group(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = raw.get(key)
    return value if isinstance(value, Mapping) else {}


def scale_for_players(raw: Mapping[str, Any], players: int | None = None,
                      explicit: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """``raw`` with board and bank scaled to ``players`` (default: ``players.max``).

    Values present in ``explicit`` (default: ``raw`` itself) are never scaled.
    """
    out = copy.deepcopy(dict(raw))
    if explicit is None:
        explicit = raw
    group = _group(raw, "players")
    sized_for = int(group.get("sized_for", _default(PlayersSettings, "sized_for")))
    enabled = bool(group.get("scale_for_more", _default(PlayersSettings, "scale_for_more")))
    count = players if players is not None else int(group.get("max", _default(PlayersSettings, "max")))
    if not enabled or sized_for < 1 or count <= sized_for:
        return out

    board = dict(_group(out, "board"))
    fixed_board = _group(explicit, "board")
    if not any(fixed_board.get(k) is not None for k in _BOARD_KEYS) and not any(
            board.get(k) is not None for k in ("terrain_counts", "number_tokens")):
        land = int(board.get("land_hexes") or _default(BoardSettings, "land_hexes"))
        board["land_hexes"] = scaled_count(land, count, sized_for, _MAX_LAND_HEXES)
        out["board"] = board

    economy = dict(_group(out, "economy"))
    bank = dict(_group(economy, "bank"))
    per = bank.get("per_resource")
    if per is None:
        per = {r.value: n for r, n in _default(BankSettings, "per_resource").items()}
    if "per_resource" not in _group(_group(explicit, "economy"), "bank") and isinstance(per, Mapping):
        bank["per_resource"] = {str(r): scaled_count(int(n), count, sized_for, _MAX_BANK) for r, n in per.items()}
        economy["bank"] = bank
        out["economy"] = economy

    return out
