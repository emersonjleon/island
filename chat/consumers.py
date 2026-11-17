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
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth import get_user_model

from gameplay.ratelimit import TokenBucket

from . import codes, conf, services, social


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


class SocialConsumer(AsyncJsonWebsocketConsumer):
    """The site-wide chat on ``/ws/social/``: public room, friends and private messages.

    Client -> server:
      ``{"t": "say", "to": null | user_id, "text": ...}``  (null = public room)
      ``{"t": "friend", "op": "add" | "accept" | "remove", "id": user_id}`` or ``"name": ...`` for "add"
      ``{"t": "privacy", "value": "everyone" | "friends" | "games"}``
      ``{"t": "ping"}``
    Server -> client:
      ``{"t": "social", ...}`` (see ``social.state``) on connect and whenever friends or the setting change;
      ``{"t": "public", "msgs": [...], "history": bool}``; ``{"t": "dm", "msgs": [...], "history": bool}``;
      refusals as ``{"t": "notice", "code": "chat....", "params": {...}}``.
    """

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4403)
            return
        self.user = user
        self.in_public = False
        self.bucket = TokenBucket(conf.get("RATE_PER_SECOND"), conf.get("BURST"))
        self.own_group = social.user_group(user.pk)
        await self.channel_layer.group_add(self.own_group, self.channel_name)
        await self.accept()
        await self._push_state(send_dm_history=True)

    async def disconnect(self, close_code):
        if hasattr(self, "own_group"):
            await self.channel_layer.group_discard(self.own_group, self.channel_name)
        if getattr(self, "in_public", False):
            await self.channel_layer.group_discard(social.PUBLIC_GROUP, self.channel_name)

    async def receive_json(self, content, **kwargs):
        kind = content.get("t") if isinstance(content, dict) else None
        if kind == "ping":
            await self.send_json({"t": "pong"})
            return
        if kind not in ("say", "friend", "privacy"):
            return
        if not self.bucket.take():
            await self._notice(codes.RATE_LIMITED)
            return
        try:
            if kind == "say":
                await self._say(content)
            elif kind == "friend":
                await self._friend(content)
            else:
                await database_sync_to_async(social.set_privacy)(self.user, content.get("value"))
                await self.channel_layer.group_send(self.own_group, {"type": "social.refresh"})
        except services.ChatError as exc:
            await self._notice(exc.code, exc.params)

    async def _say(self, content: dict[str, Any]) -> None:
        to = content.get("to")
        if to is None:
            msg = await database_sync_to_async(social.post_public)(self.user, content.get("text"))
            await self.channel_layer.group_send(social.PUBLIC_GROUP, {"type": "social.public", "msg": msg})
            return

        def post_dm():
            return social.post_dm(self.user, social.get_user(to), content.get("text"))

        msg = await database_sync_to_async(post_dm)()
        for uid in {self.user.pk, msg["to"]}:
            await self.channel_layer.group_send(social.user_group(uid), {"type": "social.dm", "msg": msg})

    async def _friend(self, content: dict[str, Any]) -> None:
        op = content.get("op")

        def apply() -> int | None:
            other = social.find_user(content.get("name")) if "name" in content else social.get_user(content.get("id"))
            if op == "add":
                social.request_friend(self.user, other)
            elif op == "accept":
                social.accept_friend(self.user, other)
            elif op == "remove":
                social.remove_friend(self.user, other)
            else:
                return None
            return other.pk

        other_id = await database_sync_to_async(apply)()
        if other_id is None:
            return
        for uid in {self.user.pk, other_id}:
            await self.channel_layer.group_send(social.user_group(uid), {"type": "social.refresh"})

    async def _push_state(self, send_dm_history: bool = False) -> None:
        """Send the panel's state and join or leave the public room to match the privacy setting."""

        def load():
            user = get_user_model().objects.get(pk=self.user.pk)  # the name may have changed since connecting
            return social.state(user), (social.dm_history(user) if send_dm_history else None)

        frame, dms = await database_sync_to_async(load)()
        await self.send_json(frame)
        if dms is not None:
            await self.send_json({"t": "dm", "msgs": dms, "history": True})
        wants_public = frame["privacy"] == social.Privacy.EVERYONE
        if wants_public and not self.in_public:
            await self.channel_layer.group_add(social.PUBLIC_GROUP, self.channel_name)
            self.in_public = True
            msgs = await database_sync_to_async(social.public_history)()
            await self.send_json({"t": "public", "msgs": msgs, "history": True})
        elif not wants_public and self.in_public:
            await self.channel_layer.group_discard(social.PUBLIC_GROUP, self.channel_name)
            self.in_public = False

    async def social_refresh(self, event: dict[str, Any]) -> None:
        await self._push_state()

    async def social_public(self, event: dict[str, Any]) -> None:
        if self.in_public:
            await self.send_json({"t": "public", "msgs": [event["msg"]], "history": False})

    async def social_dm(self, event: dict[str, Any]) -> None:
        await self.send_json({"t": "dm", "msgs": [event["msg"]], "history": False})

    async def _notice(self, code: str, params: dict | None = None) -> None:
        await self.send_json({"t": "notice", "code": code, "params": params or {}})
