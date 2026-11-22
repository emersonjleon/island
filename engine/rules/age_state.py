"""Ages (WP26): read-only helpers shared by the rules that ages change.

Kept apart from :mod:`engine.rules.ages` (commands and timer) so placement,
construction, production and robber can import it without registering anything.

State: ``state.ext["ages"]`` = ``{"age": {seat: n}, "advancing": {seat: {"age", "t0",
"t1", "paid", "timer"}}, "reached": {seat: {age: ms}}}`` (seat and age keys are
strings, as in every ``ext`` dict). A player missing from ``age`` is in age I.
With ``ages.enabled`` off every helper returns the neutral value.
"""
from __future__ import annotations

from typing import Any

from engine.errors import RuleError
from engine.settings.enums import BuildKind
from engine.settings.models import AgeStep
from engine.state import GameState

__all__ = [
    "EXT_KEY", "FIRST_AGE", "LAST_AGE", "enabled", "ext", "age_of", "advancing", "step", "reached_steps",
    "locked_error", "card_limit_bonus", "fish_bonus", "build_time_pct", "city_count",
]

EXT_KEY = "ages"
FIRST_AGE = 1
LAST_AGE = 3


def enabled(state: GameState) -> bool:
    return state.settings.ages.enabled


def ext(state: GameState) -> dict[str, Any]:
    """The ages state, created on first use."""
    e = state.ext.setdefault(EXT_KEY, {})
    for key in ("age", "advancing", "reached"):
        e.setdefault(key, {})
    return e


def age_of(state: GameState, seat: int) -> int:
    if not enabled(state):
        return FIRST_AGE
    return int(state.ext.get(EXT_KEY, {}).get("age", {}).get(str(seat), FIRST_AGE))


def advancing(state: GameState, seat: int) -> dict[str, Any] | None:
    """The research in progress of ``seat`` (``age``, ``t0``, ``t1``, ``paid``), or None."""
    return state.ext.get(EXT_KEY, {}).get("advancing", {}).get(str(seat))


def step(state: GameState, age: int) -> AgeStep:
    """Settings of advancing *to* ``age`` (2 or 3)."""
    return state.settings.ages.age2 if age == 2 else state.settings.ages.age3


def reached_steps(state: GameState, seat: int) -> list[AgeStep]:
    """The steps of every age ``seat`` reached after the first, in order."""
    return [step(state, a) for a in range(FIRST_AGE + 1, age_of(state, seat) + 1)]


def locked_error(state: GameState, seat: int, kind: BuildKind) -> RuleError | None:
    """``age.locked`` {kind, age} when ``kind`` needs a later age than ``seat``'s."""
    if not enabled(state):
        return None
    need = state.settings.ages.unlock.get(kind, FIRST_AGE)
    if need > age_of(state, seat):
        return RuleError("age.locked", {"kind": kind.value, "age": need})
    return None


def card_limit_bonus(state: GameState, seat: int) -> int:
    """Added to ``robber.card_limit`` for ``seat`` (adds up over the ages)."""
    return sum(s.bonus.card_limit for s in reached_steps(state, seat))


def fish_bonus(state: GameState, seat: int) -> int:
    """Extra fish per own building on a producing fishing ground (adds up over the ages)."""
    return sum(s.bonus.fish_per_fishing_building for s in reached_steps(state, seat))


def build_time_pct(state: GameState, seat: int) -> int:
    """Build times of ``seat`` in percent: the highest reached age's value, else 100."""
    steps = reached_steps(state, seat)
    return steps[-1].bonus.build_time_pct if steps else 100


def city_count(state: GameState, seat: int) -> int:
    """Cities and megacities of ``seat`` (what the age requirements count)."""
    return sum(1 for b in state.buildings.values()
               if b.seat == seat and b.kind in (BuildKind.CITY, BuildKind.MEGACITY))
