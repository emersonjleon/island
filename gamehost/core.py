"""One live game, without I/O: engine calls, sequence numbers, command buffer.

``GameCore`` turns timers and incoming messages into ``Outgoing`` messages for the
channel layer. The async ``GameRunner`` owns the clock, sends them and persists.
"""
from dataclasses import dataclass, field
from typing import Any, Literal

from engine import game as engine
from engine.errors import RuleError
from engine.events import DiceRolled, Event
from engine.sim.runner import CommandRecord
from engine.views import filter_events, project_state

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
        if reply:
            out.append(self._reply(reply, {"t": "ack", "cid": cid}))
        return out + self.fan_out(events, now)

    def sync(self, msg: dict[str, Any]) -> list[Outgoing]:
        """Reply with the board and the current state for the asking audience."""
        seat = msg.get("seat")
        reply = msg.get("reply_channel")
        if not reply:
            return []
        board = {"t": "board", **self.state.board.to_dict()}
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
