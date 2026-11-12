"""GameConsumer: the WebSocket edge between a browser and the game host.

It signs the player in (Django session), maps them to a seat or to the
spectators, checks message size and shape, rate-limits intents and forwards
them to the game host. All game rules live in the engine, behind the host.
"""
import json
from typing import Any

from channels.db import database_sync_to_async
from channels.exceptions import ChannelFull
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from engine.commands import parse_command
from engine.errors import RuleError
from gamehost import conf as host_conf
from gamehost.core import PROTO, group_name
from lobby.models import Game, GameStatus

from . import codes
from .ratelimit import TokenBucket

TRY_AGAIN_LATER = 1013  # WebSocket close code

MAX_MESSAGE_BYTES = getattr(settings, "GAMEPLAY_MAX_MESSAGE_BYTES", 4096)
INTENTS_PER_SECOND = getattr(settings, "GAMEPLAY_INTENTS_PER_SECOND", 20)
MAX_CID_LENGTH = 32
CLOSE_FORBIDDEN = 4403
CLOSE_PROTO = 4400
VISIBLE_STATUSES = (GameStatus.STARTING, GameStatus.RUNNING, GameStatus.FINISHED)


class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        code = self.scope["url_route"]["kwargs"]["code"].upper()
        found = await self._lookup(code, user) if user is not None and user.is_authenticated else None
        if found is None:
            await self.close(code=CLOSE_FORBIDDEN)
            return
        self.game_id, self.code, self.seat, self.settings = found
        self.host_channel = host_conf.get("CHANNEL")
        self.bucket = TokenBucket(INTENTS_PER_SECOND, INTENTS_PER_SECOND)
        self.group = group_name(self.game_id, self.seat)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        await self.send_json({"t": "welcome", "game": self.code, "seat": self.seat, "proto": PROTO,
                              "settings": self.settings})
        await self._to_host("game.sync", seat=self.seat)

    async def disconnect(self, close_code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    # ---------------------------------------------------------------- client -> server
    async def receive(self, text_data=None, bytes_data=None):
        if text_data is None or len(text_data.encode()) > MAX_MESSAGE_BYTES:
            await self.notice(codes.MESSAGE_TOO_LARGE if text_data else codes.MESSAGE_INVALID)
            return
        try:
            msg = json.loads(text_data)
        except ValueError:
            msg = None
        kind = msg.get("t") if isinstance(msg, dict) else None
        handler = {"hello": self.on_hello, "sync": self.on_sync, "ping": self.on_ping,
                   "intent": self.on_intent}.get(kind)
        if handler is None:
            await self.notice(codes.MESSAGE_INVALID)
            return
        await handler(msg)

    async def on_hello(self, msg: dict[str, Any]) -> None:
        if msg.get("proto") != PROTO:
            await self.notice(codes.PROTO_UNSUPPORTED, {"proto": PROTO})
            await self.close(code=CLOSE_PROTO)

    async def on_sync(self, msg: dict[str, Any]) -> None:
        # The host always answers with the full state; from_seq is accepted for the protocol's sake.
        await self._to_host("game.sync", seat=self.seat)

    async def on_ping(self, msg: dict[str, Any]) -> None:
        c = msg.get("c")
        await self._to_host("game.ping", c=c if isinstance(c, (int, float)) else None)

    async def on_intent(self, msg: dict[str, Any]) -> None:
        cid = msg.get("cid")
        if not isinstance(cid, str) or not 0 < len(cid) <= MAX_CID_LENGTH:
            await self.reject(None, codes.INTENT_BAD_CID)
            return
        if self.seat is None:
            await self.reject(cid, codes.INTENT_SPECTATOR)
            return
        if not self.bucket.take():
            await self.reject(cid, codes.INTENT_RATE_LIMITED)
            return
        try:
            command = parse_command(msg)
        except RuleError as exc:
            await self.reject(cid, exc.code, exc.params)
            return
        await self._to_host("game.intent", seat=self.seat, cid=cid, payload=command.model_dump(mode="json"))

    # ---------------------------------------------------------------- server -> client
    async def game_out(self, event):
        """Replies and event batches from the game host, already filtered for this audience."""
        await self.send_json(event["msg"])

    async def send_json(self, content: dict[str, Any]) -> None:
        await self.send(text_data=json.dumps(content, separators=(",", ":")))

    async def reject(self, cid: str | None, code: str, params: dict | None = None) -> None:
        await self.send_json({"t": "reject", "cid": cid, "code": code, "params": params or {}})

    async def notice(self, code: str, params: dict | None = None) -> None:
        await self.send_json({"t": "notice", "code": code, "params": params or {}})

    # ---------------------------------------------------------------- helpers
    async def _to_host(self, kind: str, **fields) -> None:
        try:
            await self.channel_layer.send(self.host_channel, {
                "type": kind, "game_id": self.game_id, "reply_channel": self.channel_name, **fields})
        except ChannelFull:
            # The game host is behind. Refuse an order; a lost ping is resent anyway; without a
            # sync the client has no state, so close with "try again later" and let it reconnect.
            if kind == "game.intent":
                await self.reject(fields.get("cid"), codes.GAME_BUSY)
            elif kind == "game.sync":
                await self.close(code=TRY_AGAIN_LATER)

    @database_sync_to_async
    def _lookup(self, code: str, user):
        game = Game.objects.filter(code=code, status__in=VISIBLE_STATUSES).first()
        if game is None:
            return None
        seat = game.players.filter(user=user).values_list("seat", flat=True).first()
        return game.pk, game.code, seat, game.settings
