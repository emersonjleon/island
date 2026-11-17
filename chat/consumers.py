"""Chat for the WebSocket consumers of the waiting room and the game.

Both pages already keep a socket open, so the chat rides on it: the consumer
mixes this in, calls ``chat_join`` once it has accepted and passes
``{"t": "chat", "text": ...}`` frames to ``chat_receive``. Everyone on either
page of a game is in the same group, so the conversation started in the
waiting room carries on in the game.

Server -> client: ``{"t": "chat", "msgs": [...], "history": bool}``; refusals
come as ``{"t": "notice", "code": "chat....", "params": {...}}``.
"""
from typing import Any

from channels.db import database_sync_to_async

from gameplay.ratelimit import TokenBucket

from . import codes, conf, services


class ChatMixin:
    async def chat_join(self, game_id: int) -> None:
        self.chat_game_id = game_id
        self.chat_group = services.group_name(game_id)
        self.chat_bucket = TokenBucket(conf.get("RATE_PER_SECOND"), conf.get("BURST"))
        await self.channel_layer.group_add(self.chat_group, self.channel_name)
        msgs = await database_sync_to_async(services.history)(game_id)
        await self.send_json({"t": "chat", "msgs": msgs, "history": True})

    async def chat_leave(self) -> None:
        if hasattr(self, "chat_group"):
            await self.channel_layer.group_discard(self.chat_group, self.channel_name)

    async def chat_receive(self, msg: dict[str, Any]) -> None:
        if not hasattr(self, "chat_group"):
            return
        if not self.chat_bucket.take():
            await self._chat_notice(codes.RATE_LIMITED)
            return
        try:
            out = await database_sync_to_async(services.post)(self.chat_game_id, self.scope["user"], msg.get("text"))
        except services.ChatError as exc:
            await self._chat_notice(exc.code, exc.params)
            return
        await self.channel_layer.group_send(self.chat_group, {"type": "chat.message", "msg": out})

    async def chat_message(self, event: dict[str, Any]) -> None:
        await self.send_json({"t": "chat", "msgs": [event["msg"]], "history": False})

    async def _chat_notice(self, code: str, params: dict | None = None) -> None:
        await self.send_json({"t": "notice", "code": code, "params": params or {}})
