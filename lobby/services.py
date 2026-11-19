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
from engine.settings import (
    CURRENT_SCHEMA_VERSION, GameSettings, SeatOrder, UnknownPresetError, load_preset, merge_overrides,
)

from .models import BOT_LEVELS, BOT_NAMES, COLOUR_VALUES, SAVED_NAME_LENGTH, Game, GamePlayer, GameStatus, SavedSettings

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
def build_settings(preset: str, overrides: dict[str, Any], seed: int = 0, players: int | None = None) -> GameSettings:
    """Validate preset + overrides and dry-run the board generator.

    ``players``: the real table size at the start (the island and bank scale to it);
    None sizes them for ``players.max``.
    """
    try:
        settings = load_preset(preset, overrides, players=players)
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


def started_message(game: Game) -> dict[str, Any]:
    """Group message that redirects lobby pages to the running game (sent by the game host)."""
    return {"type": "lobby.started", "url": f"/play/{game.code}/"}


def notify_started(game: Game) -> None:
    """Synchronous variant of the game host's redirect, for scripts and tests."""
    _group_send(game.group_name, started_message(game))


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


def _free_bot_name(game: Game) -> str:
    taken = set(game.players.filter(user=None).values_list("bot_name", flat=True))
    return next((n for n in BOT_NAMES if n not in taken), BOT_NAMES[0])


def max_players(game: Game) -> int:
    return load_preset(game.preset, game.overrides).players.max


# ------------------------------------------------------------------ actions
@transaction.atomic
def create_game(host, preset: str, overrides: dict[str, Any]) -> Game:
    # Test deployments (e2e/settings.py) can force settings on every new game, e.g. a
    # short game with plenty of resources. Empty in normal settings.
    forced = getattr(django_settings, "LOBBY_FORCED_OVERRIDES", None)
    if forced:
        overrides = merge_overrides(overrides, forced)
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
        successor = game.players.select_related("user").filter(user__isnull=False).first()
        if successor is None:
            game.status = GameStatus.ABORTED
            game.save(update_fields=["status"])
        else:
            game.host = successor.user
            game.save(update_fields=["host"])
    broadcast_changed(game)


@transaction.atomic
def add_bot(game: Game, user, level: str) -> GamePlayer:
    """The host fills a free seat with a computer player (always ready)."""
    game = _locked(game)
    _require_open(game)
    if game.host_id != user.pk:
        raise LobbyError("lobby.not_host")
    if level not in {value for value, _label in BOT_LEVELS}:
        raise LobbyError("lobby.bad_bot_level")
    if game.players.count() >= max_players(game):
        raise LobbyError("lobby.full")
    seat = GamePlayer.objects.create(
        game=game, user=None, bot_level=level, bot_name=_free_bot_name(game), colour=_free_colour(game), ready=True
    )
    broadcast_changed(game)
    return seat


@transaction.atomic
def fill_with_bots(game: Game, user, level: str) -> list[GamePlayer]:
    """The host fills every free seat with computer players of ``level``."""
    game = _locked(game)
    free = max_players(game) - game.players.count()
    if free <= 0:
        _require_open(game)
        raise LobbyError("lobby.full")
    return [add_bot(game, user, level) for _ in range(free)]


@transaction.atomic
def remove_bot(game: Game, user, player_id: int) -> None:
    """The host removes one of the game's computer players."""
    game = _locked(game)
    _require_open(game)
    if game.host_id != user.pk:
        raise LobbyError("lobby.not_host")
    deleted, _rows = game.players.filter(pk=player_id, user=None).delete()
    if not deleted:
        raise LobbyError("lobby.no_such_bot")
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
    problems = start_problems(game)
    if problems:
        raise LobbyError(problems[0])
    seats = list(game.players.all())
    seed = secrets.randbits(SEED_BITS)
    settings = build_settings(game.preset, game.overrides, seed, players=len(seats))

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


# ------------------------------------------------------------------ settings
MAX_SAVED_PER_USER = 10


@transaction.atomic
def change_settings(game: Game, user, preset: str, overrides: dict[str, Any]) -> Game:
    """The host changes the game's settings before it starts; every person must get ready again."""
    game = _locked(game)
    _require_open(game)
    if game.host_id != user.pk:
        raise LobbyError("lobby.not_host")
    forced = getattr(django_settings, "LOBBY_FORCED_OVERRIDES", None)
    if forced:
        overrides = merge_overrides(overrides, forced)
    settings = build_settings(preset, overrides)
    if game.players.count() > settings.players.max:
        raise LobbyError("lobby.too_many_seated", seated=game.players.count(), max=settings.players.max)
    game.preset, game.overrides = preset, overrides
    game.save(update_fields=["preset", "overrides"])
    game.players.filter(user__isnull=False).exclude(user_id=game.host_id).update(ready=False)
    broadcast_changed(game)
    return game


def save_settings(user, name: str, preset: str, overrides: dict[str, Any]) -> SavedSettings:
    """Save (or replace, by name) one of ``user``'s own settings."""
    name = " ".join(name.split())[:SAVED_NAME_LENGTH]
    if not name:
        raise LobbyError("lobby.saved_needs_name")
    build_settings(preset, overrides)
    existing = SavedSettings.objects.filter(owner=user, name=name).first()
    if existing is None and SavedSettings.objects.filter(owner=user).count() >= MAX_SAVED_PER_USER:
        raise LobbyError("lobby.saved_too_many", max=MAX_SAVED_PER_USER)
    saved, _created = SavedSettings.objects.update_or_create(
        owner=user, name=name, defaults={"preset": preset, "overrides": overrides})
    return saved


def delete_saved(user, saved_id: int) -> None:
    deleted, _rows = SavedSettings.objects.filter(owner=user, pk=saved_id).delete()
    if not deleted:
        raise LobbyError("lobby.no_such_saved")
