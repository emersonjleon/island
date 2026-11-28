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

With ages on (docs/AGES_DESIGN.md, "Bots"): **easy** advances to the Age of the Sea
when it can pay, never trades for it and stops there; **medium** treats each age as
one more build and trades for what it lacks; **hard** does the same, faster. Easy
buys only first-tier developments; medium and hard buy the advanced ones of their age
when they can spare the fish.
``fishing_bonus`` (valuing fishing grounds at setup) is off: in bot batches it made
the hard bot lose more often to the medium one.
"""
from __future__ import annotations

from dataclasses import dataclass

from engine.rules import age_state
from engine.settings.enums import Resource
from engine.sim.bots import CITY, MEGACITY, ROAD, SETTLEMENT, GreedyBot, Intent, pips
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
    max_age: int = 3          # with ages on: the last age the bot tries to reach
    age_trades: bool = True   # with ages on: trade with the bank toward an age's cost
    fishing_bonus: int = 0    # with ages on: extra spot score per fishing ground next to it
    max_dev_tier: int = 3     # advanced developments: the highest tier the bot buys
    megacity_trades: bool = False  # trade with the bank toward a megacity when one card or two are missing


LEVELS: dict[str, BotLevel] = {
    "easy": BotLevel("easy", think_ms=4000, mistake_pct=50, trade_pct=25,
                     variety_bonus=0, harbor_bonus=0, spend_before_seven=False, max_age=2, age_trades=False,
                     max_dev_tier=1),
    "medium": BotLevel("medium", think_ms=2000, mistake_pct=10, trade_pct=100,
                       variety_bonus=0, harbor_bonus=0, spend_before_seven=False),
    "hard": BotLevel("hard", think_ms=800, mistake_pct=0, trade_pct=100,
                     variety_bonus=3, harbor_bonus=2, spend_before_seven=True, megacity_trades=True),
}
LEVEL_NAMES: tuple[str, ...] = tuple(LEVELS)
DEFAULT_LEVEL = "medium"


class LevelBot(GreedyBot):
    """The greedy bot, tuned by a :class:`BotLevel`."""

    def __init__(self, seat: int, seed: int, level: BotLevel) -> None:
        super().__init__(seat, seed)
        self.level = level
        self.max_dev_tier = level.max_dev_tier

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
        if self.level.fishing_bonus and age_state.enabled(state):
            score += self.level.fishing_bonus * sum(1 for h in gb.board.vertex_hexes[v] if h in gb.fishing)
        harbor = gb.vertex_harbor[v]
        if self.level.harbor_bonus and harbor is not None and state.settings.trading.harbor_trade:
            res = gb.harbors[harbor].resource
            if res is None or res in produced | new:
                score += self.level.harbor_bonus
        return score

    def _age_step(self, state: GameState) -> Intent | None:
        if age_state.age_of(state, self.seat) >= self.level.max_age:
            return None
        step = super()._age_step(state)
        if step is not None and step["a"] == "bank_trade" and not (self.level.age_trades and self._allow_trade()):
            return None
        return step

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
        """Over the robber limit with nothing to build: swap surplus towards a megacity (with a
        city to upgrade), a city or a settlement."""
        p = state.player(self.seat)
        has_city = any(b.seat == self.seat and b.kind is CITY for b in state.buildings.values())
        kinds = (MEGACITY, CITY, SETTLEMENT, ROAD) if has_city else (CITY, SETTLEMENT, ROAD)
        for kind in kinds:
            if p.pieces_left.get(kind, 0) > 0:
                t = self._trade_for(state, kind)
                if t is not None:
                    return t
        return None

    def network_builds(self, state: GameState) -> list[Intent]:
        out = super().network_builds(state)
        if self.level.megacity_trades and (not out or out[0]["a"] == "bank_trade"):
            p = state.player(self.seat)
            has_city = any(b.seat == self.seat and b.kind is CITY for b in state.buildings.values())
            if has_city and p.pieces_left.get(MEGACITY, 0) > 0:
                t = self._trade_for(state, MEGACITY, max_missing=2)
                if t is not None and self._allow_trade():
                    return [t]
        return out

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
