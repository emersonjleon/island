from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from chat.consumers import ChatMixin

from .models import Game


class LobbyConsumer(ChatMixin, AsyncJsonWebsocketConsumer):
    """Read-only live channel for one lobby page.

    Sends {"t": "changed"} when seats or status change (the page refetches its
    seats block) and {"t": "started", "url": ...} when the game host has the game
    running. Actions go through the normal POST views; only chat lines
    ({"t": "chat", "text": ...}, see chat.consumers) come in over the socket.
    """

    async def connect(self):
        user = self.scope.get("user")
        code = self.scope["url_route"]["kwargs"]["code"].upper()
        game_id = await self._game_id(code) if user is not None and user.is_authenticated else None
        if game_id is None:
            await self.close(code=4403)
            return
        self.group = f"lobby.{code}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
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
    def _game_id(self, code: str) -> int | None:
        return Game.objects.filter(code=code).values_list("pk", flat=True).first()
