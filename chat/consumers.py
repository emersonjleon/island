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
    """The site-wide chat on ``/ws/social/``: public rooms, friends and private messages.

    Client -> server:
      ``{"t": "say", "to": null | user_id, "text": ...}``  (null = your public room)
      ``{"t": "history", "with": user_id | null, "before": message_id?}``  (null = public room)
      ``{"t": "read", "with": user_id, "upto": message_id}``
      ``{"t": "friend", "op": "add" | "accept" | "remove", "id": user_id}`` or ``"name": ...`` for "add"
      ``{"t": "privacy", "value": "everyone" | "friends" | "games"}``, ``{"t": "room", "value": "es"}``
      ``{"t": "ping"}``
    Server -> client:
      ``{"t": "social", ...}`` (see ``social.state``) on connect and whenever friends or settings change;
      ``{"t": "public", "room": "es", "msgs": [...], "history": bool, "more": bool}``;
      ``{"t": "dm", "with": {"id", "name"}, "msgs": [...], "history": bool, "more": bool}``;
      ``{"t": "read", "with": user_id, "upto": message_id}`` (another tab of yours read it);
      refusals as ``{"t": "notice", "code": "chat....", "params": {...}}``.

    Private history is not sent up front: the state lists conversations with unread
    counts, and each conversation's lines come a page at a time when it is opened.
    """

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4403)
            return
        self.user = user
        self.room: str | None = None
        self.bucket = TokenBucket(conf.get("RATE_PER_SECOND"), conf.get("BURST"))
        self.own_group = social.user_group(user.pk)
        await self.channel_layer.group_add(self.own_group, self.channel_name)
        await self.accept()
        await self._push_state()

    async def disconnect(self, close_code):
        if hasattr(self, "own_group"):
            await self.channel_layer.group_discard(self.own_group, self.channel_name)
        if getattr(self, "room", None):
            await self.channel_layer.group_discard(social.public_group(self.room), self.channel_name)

    async def receive_json(self, content, **kwargs):
        kind = content.get("t") if isinstance(content, dict) else None
        if kind == "ping":
            await self.send_json({"t": "pong"})
            return
        handler = {
            "say": self._say, "history": self._history, "read": self._read,
            "friend": self._friend, "privacy": self._setting, "room": self._setting,
        }.get(kind)
        if handler is None:
            return
        if kind != "read" and not self.bucket.take():
            await self._notice(codes.RATE_LIMITED)
            return
        try:
            await handler(content)
        except services.ChatError as exc:
            await self._notice(exc.code, exc.params)

    async def _say(self, content: dict[str, Any]) -> None:
        to = content.get("to")
        if to is None:
            room, msg = await database_sync_to_async(social.post_public)(self.user, content.get("text"))
            await self.channel_layer.group_send(social.public_group(room), {"type": "social.public", "room": room, "msg": msg})
            return

        def post_dm():
            return social.post_dm(self.user, social.get_user(to), content.get("text"))

        msg = await database_sync_to_async(post_dm)()
        for uid in {self.user.pk, msg["to"]}:
            await self.channel_layer.group_send(social.user_group(uid), {"type": "social.dm", "msg": msg})

    async def _history(self, content: dict[str, Any]) -> None:
        other, before = content.get("with"), content.get("before")
        if other is None:
            if self.room is None:
                return
            msgs, more = await database_sync_to_async(social.public_page)(self.room, before)
            await self.send_json({"t": "public", "room": self.room, "msgs": msgs, "history": True, "more": more})
            return
        person, msgs, more = await database_sync_to_async(social.dm_page)(self.user, other, before)
        await self.send_json({"t": "dm", "with": person, "msgs": msgs, "history": True, "more": more})

    async def _read(self, content: dict[str, Any]) -> None:
        other, upto = content.get("with"), content.get("upto")
        if await database_sync_to_async(social.mark_read)(self.user, other, upto) is not None:
            await self.channel_layer.group_send(self.own_group, {"type": "social.read", "with": other, "upto": upto})

    async def _setting(self, content: dict[str, Any]) -> None:
        change = social.set_privacy if content["t"] == "privacy" else social.set_room
        await database_sync_to_async(change)(self.user, content.get("value"))
        await self.channel_layer.group_send(self.own_group, {"type": "social.refresh"})

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

    async def _push_state(self) -> None:
        """Send the panel's state and join the public room the settings call for (or none)."""

        def load():
            user = get_user_model().objects.get(pk=self.user.pk)  # the name may have changed since connecting
            return social.state(user)

        frame = await database_sync_to_async(load)()
        await self.send_json(frame)
        wanted = frame["room"] if frame["privacy"] == social.Privacy.EVERYONE else None
        if wanted == self.room:
            return
        if self.room is not None:
            await self.channel_layer.group_discard(social.public_group(self.room), self.channel_name)
        self.room = wanted
        if wanted is not None:
            await self.channel_layer.group_add(social.public_group(wanted), self.channel_name)
            msgs, more = await database_sync_to_async(social.public_page)(wanted)
            await self.send_json({"t": "public", "room": wanted, "msgs": msgs, "history": True, "more": more})

    async def social_refresh(self, event: dict[str, Any]) -> None:
        await self._push_state()

    async def social_public(self, event: dict[str, Any]) -> None:
        if self.room == event["room"]:
            await self.send_json({"t": "public", "room": event["room"], "msgs": [event["msg"]], "history": False, "more": False})

    async def social_dm(self, event: dict[str, Any]) -> None:
        msg = event["msg"]
        mine = msg["from"] == self.user.pk
        person = {"id": msg["to"], "name": msg["to_name"]} if mine else {"id": msg["from"], "name": msg["name"]}
        await self.send_json({"t": "dm", "with": person, "msgs": [msg], "history": False, "more": False})

    async def social_read(self, event: dict[str, Any]) -> None:
        await self.send_json({"t": "read", "with": event["with"], "upto": event["upto"]})

    async def _notice(self, code: str, params: dict | None = None) -> None:
        await self.send_json({"t": "notice", "code": code, "params": params or {}})
