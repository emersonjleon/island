"""One live game, without I/O: engine calls, sequence numbers, command buffer.

``GameCore`` turns timers and incoming messages into ``Outgoing`` messages for the
channel layer. The async ``GameRunner`` owns the clock, sends them and persists.
"""
from dataclasses import dataclass, field
from typing import Any, Literal

from engine import game as engine
from engine.ai.driver import BotDriver
from engine.errors import RuleError
from engine.events import DiceRolled, Event
from engine.rules import victory
from engine.sim.runner import CommandRecord
from engine.views import board_for, filter_events, project_state

SPECT = "spect"
PROTO = 1


def audience_key(seat: int | None) -> str:
    return SPECT if seat is None else str(seat)


def group_name(game_id: int, seat: int | None) -> str:
    """Channel-layer group for one audience: a seat, or all spectators."""
    return f"g.{game_id}.spect" if seat is None else f"g.{game_id}.seat.{seat}"


@dataclass(frozen=True)
class Outgoing:
    kind: Literal["group", "channel"]
    target: str
    message: dict[str, Any]


@dataclass
class GameCore:
    game_id: int
    state: Any                                  # engine.state.GameState
    cmd_seq: int = 0                            # last accepted command number
    seqs: dict[str, int] = field(default_factory=dict)
    pending: list[tuple[int, CommandRecord]] = field(default_factory=list)
    rolls_since_snapshot: int = 0
    bots: BotDriver = field(default_factory=lambda: BotDriver([]))  # computer players' seats
    # Housekeeping (None = off): a person who sends no command for ``idle_resign_ms`` of game time
    # is resigned for them (when only computer players are left, that ends the game), and a game
    # still running after ``max_game_ms`` is ended with the leader as winner.
    idle_resign_ms: int | None = None
    max_game_ms: int | None = None
    last_active: dict[int, int] = field(default_factory=dict)   # person's seat -> last command time

    def __post_init__(self) -> None:
        # Counted from when this core was built (a restore forgets older activity: fair to the people).
        for p in self.state.players:
            if p.info.user_id is not None:
                self.last_active.setdefault(p.seat, self.state.now_ms)

    # ----------------------------------------------------------- audiences
    def audiences(self) -> list[int | None]:
        return [p.seat for p in self.state.players] + [None]

    def _next_seq(self, seat: int | None) -> int:
        key = audience_key(seat)
        self.seqs[key] = self.seqs.get(key, 0) + 1
        return self.seqs[key]

    def fan_out(self, events: list[Event], now: int) -> list[Outgoing]:
        """One ``events`` batch per audience, filtered for it; audiences with nothing to see get nothing."""
        if not events:
            return []
        self.rolls_since_snapshot += sum(isinstance(e, DiceRolled) for e in events)
        out = []
        for seat in self.audiences():
            visible = filter_events(events, seat, self.state)
            if visible:
                msg = {"t": "events", "seq": self._next_seq(seat), "now": now, "events": visible}
                out.append(Outgoing("group", group_name(self.game_id, seat), {"type": "game.out", "msg": msg}))
        return out

    def state_message(self, seat: int | None, *, resumed: bool = False) -> dict[str, Any]:
        """Full projection for one audience. Carries the audience's current seq (not a new one)."""
        msg = {"t": "state", "seq": self.seqs.get(audience_key(seat), 0), "now": self.state.now_ms,
               "state": project_state(self.state, seat)}
        if resumed:
            msg["resumed"] = True
        return msg

    # ----------------------------------------------------------- inputs
    @property
    def finished(self) -> bool:
        return self.state.phase == "finished"

    def next_wakeup(self) -> int | None:
        """Earliest game time something is due: an engine timer or a bot's next decision."""
        if self.finished:
            return None
        times = [t for t in (self.state.timers.next_due(), self.bots.next_wakeup(), self._housekeeping_due())
                 if t is not None]
        return min(times) if times else None

    def bots_act(self, now: int) -> list[Outgoing]:
        """Let every bot whose turn to think has come send its intents (like a player would)."""
        out: list[Outgoing] = []
        if self.finished or not self.bots:
            return out
        now = max(now, self.state.now_ms)
        for bot in self.bots.due(now):
            for payload in bot.decide(self.state):
                if self.finished:
                    return out
                out += self.intent(now, {"seat": bot.seat, "payload": payload})
        return out

    def _housekeeping_due(self) -> int | None:
        times = []
        if self.idle_resign_ms is not None:
            times += [t + self.idle_resign_ms for s, t in self.last_active.items()
                      if not self.state.player(s).resigned]
        if self.max_game_ms is not None:
            times.append(self.max_game_ms)
        return min(times) if times else None

    def housekeeping(self, now: int) -> list[Outgoing]:
        """Resign people who left, and end games that run far too long.

        Both act through ordinary ``resign`` commands, so they are logged and replay like any other.
        """
        out: list[Outgoing] = []
        if self.finished:
            return out
        now = max(now, self.state.now_ms)
        if self.idle_resign_ms is not None:
            for seat, last in sorted(self.last_active.items()):
                if not self.finished and not self.state.player(seat).resigned and now - last >= self.idle_resign_ms:
                    out += self.intent(now, {"seat": seat, "payload": {"a": "resign"}})
        if self.max_game_ms is not None and not self.finished and self.state.now_ms >= self.max_game_ms:
            winner = victory.leader(self.state)
            for p in self.state.players:
                if self.finished:
                    break
                if p.seat != winner and not p.resigned:
                    out += self.intent(now, {"seat": p.seat, "payload": {"a": "resign"}})
        return out

    def advance(self, now: int) -> list[Outgoing]:
        if now < self.state.now_ms:
            now = self.state.now_ms
        return self.fan_out(engine.advance(self.state, now), now)

    def intent(self, now: int, msg: dict[str, Any]) -> list[Outgoing]:
        """Apply a player's intent. Replies ack/reject to ``reply_channel``; logs accepted commands."""
        seat, cid, payload = msg.get("seat"), msg.get("cid"), msg.get("payload")
        reply = msg.get("reply_channel")
        out = self.advance(now)
        now = max(now, self.state.now_ms)
        try:
            if not isinstance(seat, int):
                raise RuleError("command.unknown_seat", {"seat": seat})
            events = engine.apply(self.state, seat, payload, now)
        except RuleError as exc:
            if reply:
                out.append(self._reply(reply, {"t": "reject", "cid": cid, "code": exc.code,
                                               "params": dict(exc.params or {})}))
            return out
        self.cmd_seq += 1
        self.pending.append((self.cmd_seq, CommandRecord(now, seat, payload)))
        if seat in self.last_active:
            self.last_active[seat] = now
        if reply:
            out.append(self._reply(reply, {"t": "ack", "cid": cid}))
        return out + self.fan_out(events, now)

    def sync(self, msg: dict[str, Any]) -> list[Outgoing]:
        """Reply with the board and the current state for the asking audience."""
        seat = msg.get("seat")
        reply = msg.get("reply_channel")
        if not reply:
            return []
        board = {"t": "board", **board_for(self.state, seat)}
        return [self._reply(reply, board), self._reply(reply, self.state_message(seat))]

    def resumed_messages(self) -> list[Outgoing]:
        """After a restore: a fresh state per audience so clients drop anything they missed."""
        return [Outgoing("group", group_name(self.game_id, seat),
                         {"type": "game.out", "msg": self.state_message(seat, resumed=True)})
                for seat in self.audiences()]

    @staticmethod
    def _reply(channel: str, msg: dict[str, Any]) -> Outgoing:
        return Outgoing("channel", channel, {"type": "game.out", "msg": msg})

    def take_pending(self) -> list[tuple[int, CommandRecord]]:
        pending, self.pending = self.pending, []
        return pending
