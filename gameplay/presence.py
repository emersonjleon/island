"""Who is connected to a game, for the other players' score list (stage 2 reconnection).

Every socket of a game joins one presence group. A seated socket announces itself
when it connects (asking the others to answer with their own seats, so a newcomer
learns who is already there) and says goodbye when it closes. When one of two tabs
of the same seat closes, the other tab announces itself again, so the seat stays
online. Spectators listen but never announce.

Server -> client: ``{"t": "presence", "seat": n, "online": bool}``.
"""
from typing import Any


def presence_group(game_id: int) -> str:
    return f"game-{game_id}-presence"


class PresenceMixin:
    async def presence_join(self, game_id: int, seat: int | None) -> None:
        self.presence_group = presence_group(game_id)
        self.presence_seat = seat
        await self.channel_layer.group_add(self.presence_group, self.channel_name)
        if seat is not None:
            await self._presence_announce(True, ask=True)

    async def presence_leave(self) -> None:
        group = getattr(self, "presence_group", None)
        if group is None:
            return
        await self.channel_layer.group_discard(group, self.channel_name)
        if self.presence_seat is not None:
            await self._presence_announce(False)

    async def presence_update(self, event: dict[str, Any]) -> None:
        """A seat came or went (channel layer handler for ``presence.update``)."""
        seat, online, sender = event["seat"], event["online"], event.get("sender")
        mine = self.presence_seat
        if not online and seat == mine and sender != self.channel_name:
            await self._presence_announce(True)          # this seat is still here in another tab
            return
        await self.send_json({"t": "presence", "seat": seat, "online": online})
        if event.get("ask") and mine is not None and mine != seat:
            await self._presence_announce(True)

    async def _presence_announce(self, online: bool, ask: bool = False) -> None:
        await self.channel_layer.group_send(self.presence_group, {
            "type": "presence.update", "seat": self.presence_seat, "online": online, "ask": ask,
            "sender": self.channel_name})
