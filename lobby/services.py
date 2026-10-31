"""Lobby actions. Views and tests call these; each raises LobbyError on a refused action."""
import secrets
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings as django_settings
from django.db import transaction
from pydantic import ValidationError

from engine.board.generator import BoardGenerationError, check_board_settings
from engine.codec import CODEC_VERSION
from engine.rng import Rng
from engine.settings import CURRENT_SCHEMA_VERSION, GameSettings, SeatOrder, UnknownPresetError, load_preset

from .models import COLOUR_VALUES, Game, GamePlayer, GameStatus

SEED_BITS = 63


class LobbyError(Exception):
    """A refused lobby action. ``code`` is a key of ``lobby.messages.ERROR_MESSAGES``."""

    def __init__(self, code: str, **params: Any):
        super().__init__(code)
        self.code = code
        self.params = params


def gamehost_channel() -> str:
    return getattr(django_settings, "GAMEHOST_CHANNEL", "gamehost")


# ------------------------------------------------------------------ settings
def build_settings(preset: str, overrides: dict[str, Any], seed: int = 0) -> GameSettings:
    """Validate preset + overrides and dry-run the board generator."""
    try:
        settings = load_preset(preset, overrides)
    except UnknownPresetError as exc:
        raise LobbyError("lobby.unknown_preset", preset=preset) from exc
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        raise LobbyError("lobby.invalid_settings", detail=first.get("type", "")) from exc
    try:
        check_board_settings(settings, seed)
    except BoardGenerationError as exc:
        raise LobbyError("lobby.board_impossible", detail=exc.code) from exc
    return settings


# ------------------------------------------------------------------ notify
def _group_send(group: str, message: dict[str, Any]) -> None:
    layer = get_channel_layer()
    if layer is not None:
        async_to_sync(layer.group_send)(group, message)


def broadcast_changed(game: Game) -> None:
    """Tell everyone watching the lobby page that seats or status changed (after commit)."""
    group = game.group_name
    transaction.on_commit(lambda: _group_send(group, {"type": "lobby.changed"}))


def notify_started(game: Game) -> None:
    """Called by the game host once the game is RUNNING: redirect lobby pages to the game."""
    _group_send(game.group_name, {"type": "lobby.started", "url": f"/play/{game.code}/"})


# ------------------------------------------------------------------ helpers
def _locked(game: Game) -> Game:
    return Game.objects.select_for_update().get(pk=game.pk)


def _require_open(game: Game) -> None:
    if game.status != GameStatus.LOBBY:
        raise LobbyError("lobby.not_open")


def _seat_of(game: Game, user) -> GamePlayer:
    seat = game.players.filter(user=user).first()
    if seat is None:
        raise LobbyError("lobby.not_joined")
    return seat


def _free_colour(game: Game) -> str:
    taken = set(game.players.values_list("colour", flat=True))
    return next(c for c in COLOUR_VALUES if c not in taken)


def max_players(game: Game) -> int:
    return load_preset(game.preset, game.overrides).players.max


# ------------------------------------------------------------------ actions
@transaction.atomic
def create_game(host, preset: str, overrides: dict[str, Any]) -> Game:
    build_settings(preset, overrides)
    game = Game.objects.create(host=host, preset=preset, overrides=overrides)
    GamePlayer.objects.create(game=game, user=host, colour=COLOUR_VALUES[0])
    return game


@transaction.atomic
def join_game(game: Game, user) -> GamePlayer:
    game = _locked(game)
    _require_open(game)
    existing = game.players.filter(user=user).first()
    if existing:
        return existing
    if game.players.count() >= max_players(game):
        raise LobbyError("lobby.full")
    seat = GamePlayer.objects.create(game=game, user=user, colour=_free_colour(game))
    broadcast_changed(game)
    return seat


@transaction.atomic
def leave_game(game: Game, user) -> None:
    """Leave the lobby. A leaving host hands the game to the next player, or cancels it."""
    game = _locked(game)
    _require_open(game)
    _seat_of(game, user).delete()
    if game.host_id == user.pk:
        successor = game.players.select_related("user").first()
        if successor is None:
            game.status = GameStatus.ABORTED
            game.save(update_fields=["status"])
        else:
            game.host = successor.user
            game.save(update_fields=["host"])
    broadcast_changed(game)


@transaction.atomic
def set_colour(game: Game, user, colour: str) -> None:
    game = _locked(game)
    _require_open(game)
    if colour not in COLOUR_VALUES:
        raise LobbyError("lobby.bad_colour")
    seat = _seat_of(game, user)
    if seat.colour == colour:
        return
    if game.players.filter(colour=colour).exists():
        raise LobbyError("lobby.colour_taken")
    seat.colour = colour
    seat.save(update_fields=["colour"])
    broadcast_changed(game)


@transaction.atomic
def set_ready(game: Game, user, ready: bool) -> None:
    game = _locked(game)
    _require_open(game)
    seat = _seat_of(game, user)
    if seat.ready != ready:
        seat.ready = ready
        seat.save(update_fields=["ready"])
        broadcast_changed(game)


@transaction.atomic
def cancel_game(game: Game, user) -> None:
    game = _locked(game)
    _require_open(game)
    if game.host_id != user.pk:
        raise LobbyError("lobby.not_host")
    game.status = GameStatus.ABORTED
    game.save(update_fields=["status"])
    broadcast_changed(game)


def start_problems(game: Game, settings: GameSettings | None = None) -> list[str]:
    """Why the host cannot start yet (error codes); empty when the game can start."""
    settings = settings or load_preset(game.preset, game.overrides)
    seats = list(game.players.all())
    problems = []
    if len(seats) < settings.players.min:
        problems.append("lobby.too_few_players")
    if any(not s.ready for s in seats if s.user_id != game.host_id):
        problems.append("lobby.not_all_ready")
    return problems


@transaction.atomic
def start_game(game: Game, user) -> Game:
    """Fix seed, seats and full settings, set STARTING and hand the game to the game host."""
    game = _locked(game)
    _require_open(game)
    if game.host_id != user.pk:
        raise LobbyError("lobby.not_host")
    seed = secrets.randbits(SEED_BITS)
    settings = build_settings(game.preset, game.overrides, seed)
    problems = start_problems(game, settings)
    if problems:
        raise LobbyError(problems[0])

    seats = list(game.players.all())
    if settings.players.seat_order == SeatOrder.RANDOM:
        Rng(seed).shuffle(seats)
    for number, seat in enumerate(seats):
        seat.seat = number
        seat.save(update_fields=["seat"])

    game.seed = seed
    game.settings = settings.model_dump(mode="json")
    game.settings_schema_version = CURRENT_SCHEMA_VERSION
    game.engine_version = str(CODEC_VERSION)
    game.status = GameStatus.STARTING
    game.save()

    game_id = game.pk
    transaction.on_commit(
        lambda: async_to_sync(get_channel_layer().send)(gamehost_channel(), {"type": "game.start", "game_id": game_id})
    )
    broadcast_changed(game)
    return game
