from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from chat.consumers import ChatMixin

from .models import Game, GameStatus


class LobbyConsumer(ChatMixin, AsyncJsonWebsocketConsumer):
    """Read-only live channel for one lobby page.

    Sends {"t": "changed"} when seats or status change (the page refetches its
    seats block) and {"t": "started", "url": ...} when the game host has the game
    running (also right after connecting, when the game started before the page
    connected). Actions go through the normal POST views; only chat lines
    ({"t": "chat", "text": ...}, see chat.consumers) come in over the socket.
    """

    async def connect(self):
        user = self.scope.get("user")
        code = self.scope["url_route"]["kwargs"]["code"].upper()
        found = await self._game(code) if user is not None and user.is_authenticated else None
        if found is None:
            await self.close(code=4403)
            return
        self.group = f"lobby.{code}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        game_id, running = found
        if running:
            # The game host may have started the game before this page connected.
            await self.send_json({"t": "started", "url": f"/play/{code}/"})
        await self.chat_join(game_id)

    async def disconnect(self, close_code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)
        await self.chat_leave()

    async def receive_json(self, content, **kwargs):
        kind = content.get("t") if isinstance(content, dict) else None
        if kind == "ping":
            await self.send_json({"t": "pong"})
        elif kind == "chat":
            await self.chat_receive(content)

    async def lobby_changed(self, event):
        await self.send_json({"t": "changed"})

    async def lobby_started(self, event):
        await self.send_json({"t": "started", "url": event["url"]})

    @database_sync_to_async
    def _game(self, code: str) -> tuple[int, bool] | None:
        """(id, whether it is running) of the game, or None."""
        row = Game.objects.filter(code=code).values_list("pk", "status").first()
        return None if row is None else (row[0], row[1] == GameStatus.RUNNING)
