"""Dice clock (WP7): the dice source and the roll timer.

* ``@timer_handler(TIMER_DICE_ROLL)`` (:func:`on_dice_roll`): roll
  ``settings.clock.dice_count`` dice of ``dice_sides`` with ``state.rng``; set
  ``last_roll``, append the sum to ``dice_history``; schedule the next roll at
  ``timer.due_ms + roll_interval_ms`` (plus ``pause_after_seven_ms`` when the sum
  is ``clock.robber_roll``), so the schedule never drifts; store
  ``roll_timer_id`` / ``next_roll_at``; emit ``DiceRolled``; then run the robber
  (sum == ``robber_roll`` and ``robber.enabled``) or production (any other sum).
  On a robber roll nothing is produced, even with the robber disabled.

Event order of one roll: ``DiceRolled`` then either the production events
(``Produced``, ``Hand``...) or the robber events (``RobberStole``/``Hand`` per
target, ``RobberMoved``).

The first roll is scheduled by setup (WP6) when the first settlement is completed.
"""
from __future__ import annotations

from engine.events import DiceRolled, Event
from engine.game import TIMER_DICE_ROLL, timer_handler
from engine.scheduler import Timer
from engine.state import GameState

__all__ = ["on_dice_roll", "roll_dice", "schedule_next_roll"]


def roll_dice(state: GameState) -> list[int]:
    """Faces of one roll from the game RNG (two dice by default)."""
    clock = state.settings.clock
    return state.rng.dice(clock.dice_count, clock.dice_sides)


def schedule_next_roll(state: GameState, due_ms: int) -> int:
    """Schedule the next ``dice_roll`` at ``due_ms`` and record it in the state."""
    state.roll_timer_id = state.timers.schedule(due_ms, TIMER_DICE_ROLL, {})
    state.next_roll_at = due_ms
    return state.roll_timer_id


@timer_handler(TIMER_DICE_ROLL)
def on_dice_roll(state: GameState, timer: Timer, now_ms: int) -> list[Event]:
    """Roll, schedule the next roll, then produce or run the robber."""
    if state.phase == "finished":
        return []
    if state.roll_timer_id is not None and state.roll_timer_id != timer.id:
        return []  # a stale roll timer (should have been cancelled): ignore it
    clock = state.settings.clock
    dice = roll_dice(state)
    total = sum(dice)
    state.last_roll = list(dice)
    state.dice_history.append(total)
    is_robber_roll = total == clock.robber_roll
    next_due = timer.due_ms + clock.roll_interval_ms + (clock.pause_after_seven_ms if is_robber_roll else 0)
    schedule_next_roll(state, next_due)
    events: list[Event] = [DiceRolled(at=now_ms, dice=list(dice), sum=total, next_roll_at=next_due)]
    if is_robber_roll:
        if state.settings.robber.enabled:
            from engine.rules import robber
            events += robber.on_seven(state, now_ms)
    else:
        from engine.rules import production
        events += production.produce(state, total, now_ms)
    return events
