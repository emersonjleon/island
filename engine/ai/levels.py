"""Computer players at three difficulty levels.

They build on the simulation bots in :mod:`engine.sim.bots` and play through the
same raw intents a browser sends, so the game host applies, logs and replays
their commands exactly like a person's. A bot keeps its own :class:`Rng`; it
never touches ``state.rng``, so a game replays from its command log alone.

A level is a :class:`BotLevel` profile. These are tuning values of the computer
player (how fast and how well it plays), not rules of the game, so they live
here and not in ``GameSettings``.

* **easy** acts every few seconds, often picks a random spot instead of the
  best one and rarely trades with the bank.
* **medium** is the greedy bot: best-yield spots, cities before settlements,
  trades for what it is missing.
* **hard** acts quickly, values resources it does not produce yet and harbors
  it can use, and spends cards before a seven can rob them.
"""
from __future__ import annotations

from dataclasses import dataclass

from engine.settings.enums import Resource
from engine.sim.bots import CITY, ROAD, SETTLEMENT, GreedyBot, Intent, pips
from engine.state import GameState

__all__ = ["BotLevel", "LEVELS", "LEVEL_NAMES", "DEFAULT_LEVEL", "LevelBot", "make_level_bot"]

PERCENT = 100


@dataclass(frozen=True)
class BotLevel:
    name: str
    think_ms: int          # game time between two decisions
    mistake_pct: int       # chance that a spot is picked at random instead of scored
    trade_pct: int         # chance that a wanted bank trade is actually made
    variety_bonus: int     # extra score per resource a spot adds to the bot's production
    harbor_bonus: int      # extra score for a harbor the bot could use
    spend_before_seven: bool  # trade cards away while holding more than the robber limit


LEVELS: dict[str, BotLevel] = {
    "easy": BotLevel("easy", think_ms=4000, mistake_pct=50, trade_pct=25,
                     variety_bonus=0, harbor_bonus=0, spend_before_seven=False),
    "medium": BotLevel("medium", think_ms=2000, mistake_pct=10, trade_pct=100,
                       variety_bonus=0, harbor_bonus=0, spend_before_seven=False),
    "hard": BotLevel("hard", think_ms=800, mistake_pct=0, trade_pct=100,
                     variety_bonus=3, harbor_bonus=2, spend_before_seven=True),
}
LEVEL_NAMES: tuple[str, ...] = tuple(LEVELS)
DEFAULT_LEVEL = "medium"


class LevelBot(GreedyBot):
    """The greedy bot, tuned by a :class:`BotLevel`."""

    def __init__(self, seat: int, seed: int, level: BotLevel) -> None:
        super().__init__(seat, seed)
        self.level = level

    # ---------------------------------------------------------------- scoring
    def _produced(self, state: GameState) -> set[Resource]:
        gb = state.board
        out: set[Resource] = set()
        for v, b in state.buildings.items():
            if b.seat == self.seat:
                out |= {r for h in gb.board.vertex_hexes[v] if (r := gb.hex_resource(h)) is not None}
        return out

    def spot_value(self, state: GameState, v: int, produced: set[Resource]) -> int:
        """Dice combinations around ``v``, plus the level's bonuses for variety and harbors."""
        gb = state.board
        score, new = 0, set()
        for h in gb.board.vertex_hexes[v]:
            r = gb.hex_resource(h)
            if r is None:
                continue
            score += pips(gb.token[h], state)
            if r not in produced:
                new.add(r)
        score += self.level.variety_bonus * len(new)
        harbor = gb.vertex_harbor[v]
        if self.level.harbor_bonus and harbor is not None and state.settings.trading.harbor_trade:
            res = gb.harbors[harbor].resource
            if res is None or res in produced | new:
                score += self.level.harbor_bonus
        return score

    def _blunder(self) -> bool:
        return self.level.mistake_pct > 0 and self.rng.randbelow(PERCENT) < self.level.mistake_pct

    def pick_vertex(self, state: GameState, options: list[int]) -> int:
        if self._blunder():
            return self.rng.choice(options)
        if not (self.level.variety_bonus or self.level.harbor_bonus):
            return super().pick_vertex(state, options)
        board = state.board.board
        contested: set[int] = set()
        for c in state.constructions.values():
            if c.seat != self.seat and c.kind is SETTLEMENT:
                contested |= {c.target, *board.vertex_neighbors[c.target]}
        free = [v for v in options if v not in contested] or options
        produced = self._produced(state)
        scores = {v: self.spot_value(state, v, produced) for v in free}
        best = max(scores.values())
        return self.rng.choice([v for v in free if scores[v] == best])

    def pick_road(self, state: GameState, options: list[int]) -> int:
        if self._blunder():
            return self.rng.choice(options)
        return super().pick_road(state, options)

    # ---------------------------------------------------------------- trades
    def _allow_trade(self) -> bool:
        return self.level.trade_pct >= PERCENT or self.rng.randbelow(PERCENT) < self.level.trade_pct

    def _over_limit(self, state: GameState) -> bool:
        return state.player(self.seat).hand_count > state.settings.robber.card_limit

    def _spend_down(self, state: GameState) -> Intent | None:
        """Over the robber limit with nothing to build: swap surplus towards a city or settlement."""
        p = state.player(self.seat)
        for kind in (CITY, SETTLEMENT, ROAD):
            if p.pieces_left.get(kind, 0) > 0:
                t = self._trade_for(state, kind)
                if t is not None:
                    return t
        return None

    def network(self, state: GameState) -> list[Intent]:
        out = [i for i in super().network(state) if i["a"] != "bank_trade" or self._allow_trade()]
        if not out and self.level.spend_before_seven and self._over_limit(state):
            t = self._spend_down(state)
            if t is not None:
                out.append(t)
        return out


def make_level_bot(level: str, seat: int, seed: int) -> LevelBot:
    """A bot for ``seat`` at ``level`` (a key of :data:`LEVELS`)."""
    return LevelBot(seat, seed, LEVELS[level])
