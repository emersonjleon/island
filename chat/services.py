"""Channels and messages, the same for every kind of chat. The consumers call these; no WebSocket code here.

The game chat keeps its small API (``post``, ``history``, ``group_name`` by game id);
the site-wide chat builds on the channel functions (see ``chat.social``).
"""
import unicodedata
from typing import Any

from django.db import IntegrityError, transaction

from lobby.models import GamePlayer

from . import codes, conf
from .models import Channel, ChannelKind, Message


class ChatError(Exception):
    def __init__(self, code: str, params: dict[str, Any] | None = None):
        super().__init__(code)
        self.code = code
        self.params = params or {}


def clean_text(text: Any) -> str:
    """One line of plain text: control characters and runs of spaces become single spaces."""
    if not isinstance(text, str):
        raise ChatError(codes.EMPTY)
    visible = "".join(" " if unicodedata.category(ch) in ("Cc", "Zl", "Zp") else ch for ch in text)
    cleaned = " ".join(visible.split())
    if not cleaned:
        raise ChatError(codes.EMPTY)
    limit = conf.get("MAX_LENGTH")
    if len(cleaned) > limit:
        raise ChatError(codes.TOO_LONG, {"max": limit})
    return cleaned


# --- channels ----------------------------------------------------------------

def channel_group(key: str) -> str:
    """Channel-layer group of everyone listening to a channel ("game:4" -> "chat.game.4")."""
    return "chat." + key.replace(":", ".")


def get_channel(key: str, kind: str, **fields) -> Channel:
    channel = Channel.objects.filter(key=key).first()
    if channel is not None:
        return channel
    try:
        with transaction.atomic():
            return Channel.objects.create(key=key, kind=kind, **fields)
    except IntegrityError:  # someone else created it at the same moment
        return Channel.objects.get(key=key)


def write(channel: Channel, user, text: Any, colour: str = "", seat: int | None = None) -> Message:
    cleaned = clean_text(text)
    msg = Message.objects.create(channel=channel, sender=user, name=user.public_name[:64], colour=colour, seat=seat, text=cleaned)
    Channel.objects.filter(pk=channel.pk).update(last_message_id=msg.pk)
    channel.last_message_id = msg.pk
    return msg


def page(channel_id: int | None, before: Any = None, limit: int | None = None) -> tuple[list[Message], bool]:
    """Up to ``limit`` messages older than id ``before`` (the latest when None), oldest first, and whether more exist."""
    if channel_id is None:
        return [], False
    n = conf.get("PAGE") if limit is None else limit
    rows = Message.objects.filter(channel_id=channel_id)
    if isinstance(before, int):
        rows = rows.filter(id__lt=before)
    latest = list(rows.order_by("-id")[: n + 1])
    return list(reversed(latest[:n])), len(latest) > n


# --- the game chat -------------------------------------------------------------

def game_key(game_id: int) -> str:
    return f"game:{game_id}"


def group_name(game_id: int) -> str:
    return channel_group(game_key(game_id))


def to_wire(msg: Message) -> dict[str, Any]:
    return {
        "id": msg.pk,
        "name": msg.name,
        "colour": msg.colour,
        "seat": msg.seat,
        "player": bool(msg.colour),
        "text": msg.text,
        "at": int(msg.created_at.timestamp() * 1000),
    }


def post(game_id: int, user, text: Any) -> dict[str, Any]:
    """Store a message from ``user`` (a player or someone watching) and return it as sent to clients."""
    clean_text(text)  # refuse before creating the game's channel
    seat = GamePlayer.objects.filter(game_id=game_id, user=user).values("colour", "seat").first()
    channel = get_channel(game_key(game_id), ChannelKind.GAME, game_id=game_id)
    msg = write(channel, user, text, colour=seat["colour"] if seat else "", seat=seat["seat"] if seat else None)
    return to_wire(msg)


def history(game_id: int, limit: int | None = None) -> list[dict[str, Any]]:
    """The latest messages of a game, oldest first."""
    channel_id = Channel.objects.filter(key=game_key(game_id)).values_list("pk", flat=True).first()
    msgs, _more = page(channel_id, limit=conf.get("HISTORY") if limit is None else limit)
    return [to_wire(m) for m in msgs]
