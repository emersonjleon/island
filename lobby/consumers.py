from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .models import Game


class LobbyConsumer(AsyncJsonWebsocketConsumer):
    """Read-only live channel for one lobby page.

    Sends {"t": "changed"} when seats or status change (the page refetches its
    seats block) and {"t": "started", "url": ...} when the game host has the game
    running. Actions go through the normal POST views.
    """

    async def connect(self):
        user = self.scope.get("user")
        code = self.scope["url_route"]["kwargs"]["code"].upper()
        if user is None or not user.is_authenticated or not await self._exists(code):
            await self.close(code=4403)
            return
        self.group = f"lobby.{code}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if isinstance(content, dict) and content.get("t") == "ping":
            await self.send_json({"t": "pong"})

    async def lobby_changed(self, event):
        await self.send_json({"t": "changed"})

    async def lobby_started(self, event):
        await self.send_json({"t": "started", "url": event["url"]})

    @database_sync_to_async
    def _exists(self, code: str) -> bool:
        return Game.objects.filter(code=code).exists()
