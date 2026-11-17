"""Writing and reading a game's chat. The consumers call these; no WebSocket code here."""
import unicodedata
from typing import Any

from lobby.models import GamePlayer

from . import codes, conf
from .models import ChatMessage


class ChatError(Exception):
    def __init__(self, code: str, params: dict[str, Any] | None = None):
        super().__init__(code)
        self.code = code
        self.params = params or {}


def group_name(game_id: int) -> str:
    return f"chat.{game_id}"


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


def to_wire(msg: ChatMessage) -> dict[str, Any]:
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
    cleaned = clean_text(text)
    seat = GamePlayer.objects.filter(game_id=game_id, user=user).values("colour", "seat").first()
    msg = ChatMessage.objects.create(
        game_id=game_id, user=user, name=user.public_name[:64],
        colour=seat["colour"] if seat else "", seat=seat["seat"] if seat else None, text=cleaned,
    )
    return to_wire(msg)


def history(game_id: int, limit: int | None = None) -> list[dict[str, Any]]:
    """The latest messages of a game, oldest first."""
    n = conf.get("HISTORY") if limit is None else limit
    latest = list(ChatMessage.objects.filter(game_id=game_id).order_by("-id")[:n])
    return [to_wire(m) for m in reversed(latest)]
