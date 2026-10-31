from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from engine.settings import load_preset

from . import services
from .forms import CreateGameForm
from .messages import error_message
from .models import COLOURS, Game, GameStatus


def _game(code: str) -> Game:
    return get_object_or_404(Game.objects.select_related("host"), code=code.upper())


@login_required
def game_list(request: HttpRequest) -> HttpResponse:
    form = CreateGameForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            game = services.create_game(request.user, form.cleaned_data["preset"], form.overrides())
        except services.LobbyError as exc:
            form.add_error(None, error_message(exc.code))
        else:
            return redirect("lobby:detail", code=game.code)
    open_games = Game.objects.filter(status=GameStatus.LOBBY).select_related("host").prefetch_related("players")
    mine = (
        Game.objects.filter(players__user=request.user, status__in=[GameStatus.STARTING, GameStatus.RUNNING])
        .select_related("host")
        .distinct()
    )
    return render(request, "lobby/list.html", {"form": form, "open_games": open_games[:50], "my_games": mine})


def seats_context(request: HttpRequest, game: Game) -> dict:
    settings = load_preset(game.preset, game.overrides)
    seats = list(game.players.select_related("user"))
    me = next((s for s in seats if s.user_id == request.user.pk), None)
    taken = {s.colour for s in seats}
    return {
        "game": game,
        "settings": settings,
        "seats": seats,
        "me": me,
        "is_host": game.host_id == request.user.pk,
        "free_colours": [(c, label) for c, label in COLOURS if c not in taken],
        "can_join": game.is_open and me is None and len(seats) < settings.players.max,
        "start_problems": [error_message(p) for p in services.start_problems(game, settings)] if game.is_open else [],
        "roll_seconds": settings.clock.roll_interval_ms // 1000,
    }


@login_required
def game_detail(request: HttpRequest, code: str) -> HttpResponse:
    game = _game(code)
    return render(request, "lobby/detail.html", seats_context(request, game))


@login_required
def game_seats(request: HttpRequest, code: str) -> HttpResponse:
    """The seats block alone; the lobby page refetches it when the WebSocket says something changed."""
    game = _game(code)
    return render(request, "lobby/_seats.html", seats_context(request, game))


def _action(request: HttpRequest, code: str, fn, *args) -> HttpResponse:
    game = _game(code)
    try:
        fn(game, request.user, *args)
    except services.LobbyError as exc:
        messages.error(request, error_message(exc.code))
    return redirect("lobby:detail", code=game.code)


@login_required
@require_POST
def join(request: HttpRequest, code: str) -> HttpResponse:
    return _action(request, code, services.join_game)


@login_required
@require_POST
def leave(request: HttpRequest, code: str) -> HttpResponse:
    game = _game(code)
    try:
        services.leave_game(game, request.user)
    except services.LobbyError as exc:
        messages.error(request, error_message(exc.code))
        return redirect("lobby:detail", code=game.code)
    return redirect("lobby:list")


@login_required
@require_POST
def colour(request: HttpRequest, code: str) -> HttpResponse:
    return _action(request, code, services.set_colour, request.POST.get("colour", ""))


@login_required
@require_POST
def ready(request: HttpRequest, code: str) -> HttpResponse:
    return _action(request, code, services.set_ready, request.POST.get("ready") == "1")


@login_required
@require_POST
def start(request: HttpRequest, code: str) -> HttpResponse:
    return _action(request, code, services.start_game)


@login_required
@require_POST
def cancel(request: HttpRequest, code: str) -> HttpResponse:
    game = _game(code)
    try:
        services.cancel_game(game, request.user)
    except services.LobbyError as exc:
        messages.error(request, error_message(exc.code))
        return redirect("lobby:detail", code=game.code)
    return redirect("lobby:list")
