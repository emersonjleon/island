"""Settings codes: copy a game's rules as a short code, and create a game from one."""
from typing import Any

from django.urls import reverse
from django.utils.http import urlencode

from engine.settings import ShareCodeError, SharedSettings, decode_share_code, encode_share_code

from .models import Game
from .services import LobbyError

CONFIG_PARAM = "config"

# ShareCodeError codes -> lobby error codes (keys of lobby.messages.ERROR_MESSAGES).
_ERRORS = {
    "settings.share.too_long": "lobby.code_too_long",
    "settings.share.too_new": "lobby.code_too_new",
    "settings.preset.unknown": "lobby.code_unknown_preset",
}


def game_code(game: Game) -> str:
    """The settings code of ``game``: its game type and the rules changed on top."""
    return encode_share_code(game.preset, game.overrides)


def create_path(code: str) -> str:
    """The lobby link that opens the create form with ``code`` filled in."""
    return f"{reverse('lobby:list')}?{urlencode({CONFIG_PARAM: code})}#create-game"


def read_code(code: str) -> SharedSettings:
    """The game type and overrides in ``code``; LobbyError when it cannot be read."""
    try:
        return decode_share_code(code)
    except ShareCodeError as exc:
        raise LobbyError(_ERRORS.get(exc.code, "lobby.code_malformed"), **exc.params) from exc


def code_context(request, game: Game) -> dict[str, Any]:
    code = game_code(game)
    return {"settings_code": code, "settings_code_url": request.build_absolute_uri(create_path(code))}
