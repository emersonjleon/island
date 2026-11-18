from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from engine.settings import encode_share_code, load_preset
from engine.settings.share import MAX_CODE_LENGTH

from . import services
from .forms import KNOB_PATHS, CreateGameForm
from .messages import error_message
from .models import BOT_LEVELS, COLOURS, Game, GameStatus
from .presets import (
    CUSTOM, GROUPS, KNOBS, KNOBS_BY_NAME, STATS, default_players, preset_description, preset_label, preset_values,
    presets_data, settings_values, stats_rows,
)
from .settings_editor import changed_settings, editor_data, editor_view
from .prefill import settings_form_data
from .sharing import CONFIG_PARAM, code_context, create_path, read_code


def _game(code: str) -> Game:
    return get_object_or_404(Game.objects.select_related("host"), code=code.upper())


@login_required
def game_list(request: HttpRequest) -> HttpResponse:
    initial = {"config": request.GET.get(CONFIG_PARAM, "")[:MAX_CODE_LENGTH]}
    form = CreateGameForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            game = services.create_game(request.user, form.chosen_preset(), form.overrides())
        except services.LobbyError as exc:
            form.add_error(None, error_message(exc.code))
        else:
            if request.POST.get("play_bots"):
                _play_against_bots(request, game, form.cleaned_data["bot_level"])
            return redirect("lobby:detail", code=game.code)
    open_games = Game.objects.filter(status=GameStatus.LOBBY).select_related("host").prefetch_related("players")
    mine = (
        Game.objects.filter(players__user=request.user, status__in=[GameStatus.STARTING, GameStatus.RUNNING])
        .select_related("host")
        .distinct()
    )
    context = {"form": form, "open_games": open_games[:50], "my_games": mine, "saved_settings": saved_rows(request.user)}
    return render(request, "lobby/list.html", context | create_form_context(form))


def _play_against_bots(request: HttpRequest, game: Game, level: str) -> None:
    """Fill the new game's free seats with bots and start it at once."""
    try:
        services.fill_with_bots(game, request.user, level)
        services.start_game(game, request.user)
    except services.LobbyError as exc:
        messages.error(request, error_message(exc.code))


def _chosen(form: CreateGameForm) -> tuple[str, int]:
    """The game type and table size the form shows (what was posted, else the initial ones)."""
    preset = form.data.get("preset") or form.fields["preset"].initial
    if preset not in dict(form.fields["preset"].choices):
        preset = form.fields["preset"].initial
    try:
        players = int(form.data.get("max_players") or form.fields["max_players"].initial)
    except ValueError:
        players = form.fields["max_players"].initial
    choices = [n for n, _label in form.fields["max_players"].choices]
    return preset, min(max(players, choices[0]), choices[-1])


def create_form_context(form: CreateGameForm) -> dict:
    preset, players = _chosen(form)
    base = form.base_name()

    def values_of(name: str, size: int | None = None) -> dict:
        real = base if name == CUSTOM else name
        return preset_values(real, size or players)

    def card_values(name: str) -> dict:
        """The chosen card follows the table size; the others show their own numbers."""
        own = default_players(base if name == CUSTOM else name)
        return values_of(name, players if name == preset else own)

    cards = [
        {"radio": radio, "name": radio.data["value"], "description": preset_description(radio.data["value"]),
         "values": card_values(radio.data["value"])}
        for radio in form["preset"]
    ]
    groups = [
        {"label": label, "fields": [form[k.name] for k in KNOBS if k.group == key]}
        for key, label in GROUPS
    ]
    return {
        "preset_cards": cards,
        "chosen_preset": preset,
        "chosen_stats": [
            (label, text, " ".join(knobs))
            for (label, text), (_label, knobs) in zip(stats_rows(values_of(preset)), STATS)
        ],
        "knob_groups": groups,
        "custom_preset": CUSTOM,
        "base_label": preset_label(base),
        "presets_data": presets_data(),
        "code_preview": code_preview(form),
        "editor": editor_view(form.data if form.is_bound else {}, base, KNOB_PATHS, form.editor_errors),
        "editor_open": bool(form.editor_errors) or any(
            k.startswith("s:") and v for k, v in (form.data.items() if form.is_bound else [])),
        "editor_data": editor_data(),
    }


def code_preview(form: CreateGameForm) -> dict | None:
    """The game type and summary of the settings code the form holds, if it can be read."""
    code = form.data.get("config") if form.is_bound else form.initial.get("config")
    code = "".join((code or "").split())
    if not code:
        return None
    try:
        shared = read_code(code)
        settings = services.build_settings(shared.preset, shared.overrides)
    except services.LobbyError:
        return None
    return {
        "label": preset_label(shared.preset),
        "players": settings.players.max,
        "stats": stats_rows(settings_values(settings)),
        "changes": rule_changes(shared.preset, settings),
    }


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
        "can_add_bot": game.is_open and game.host_id == request.user.pk and len(seats) < settings.players.max,
        "bot_levels": BOT_LEVELS,
        "bot_level": next((s.bot_level for s in reversed(seats) if s.is_bot), "medium"),
        "free_seats": max(settings.players.max - len(seats), 0),
        "start_problems": [error_message(p) for p in services.start_problems(game, settings)] if game.is_open else [],
        "roll_seconds": settings.clock.roll_interval_ms // 1000,
        "stats": stats_rows(settings_values(settings)),
        "rule_changes": rule_changes(game.preset, settings),
    } | code_context(request, game)


def rule_changes(preset: str, settings) -> list[tuple]:
    """The settings changed from the game type that the summary does not already show."""
    players = settings.players.max
    base = load_preset(preset, {"players": {"max": players}}, players=players)
    shown = {".".join(KNOBS_BY_NAME[k].path) for _label, knobs in STATS for k in knobs}
    return changed_settings(base, settings, exclude=shown)


@login_required
def edit_settings(request: HttpRequest, code: str) -> HttpResponse:
    """The host changes the settings of a game that has not started (the custom-game form, filled in)."""
    game = _game(code)
    if game.host_id != request.user.pk or not game.is_open:
        return redirect("lobby:detail", code=game.code)
    data = request.POST if request.method == "POST" else settings_form_data(game.preset, game.overrides)
    form = CreateGameForm(data)
    if request.method == "POST" and form.is_valid():
        try:
            services.change_settings(game, request.user, form.chosen_preset(), form.overrides())
        except services.LobbyError as exc:
            form.add_error(None, error_message(exc.code))
        else:
            messages.success(request, _("Settings changed. Every player must get ready again."))
            return redirect("lobby:detail", code=game.code)
    context = {"game": game, "form": form} | create_form_context(form)
    context["editor_open"] = True
    return render(request, "lobby/settings.html", context)


@login_required
@require_POST
def save_game_settings(request: HttpRequest, code: str) -> HttpResponse:
    """Anyone who sees a game can keep its settings under a name of their own."""
    game = _game(code)
    try:
        saved = services.save_settings(request.user, request.POST.get("name", ""), game.preset, game.overrides)
    except services.LobbyError as exc:
        messages.error(request, error_message(exc.code))
    else:
        messages.success(request, _("Saved as \u201c%(name)s\u201d. Find it under My settings when you create a game.")
                         % {"name": saved.name})
    return redirect("lobby:detail", code=game.code)


@login_required
@require_POST
def delete_saved(request: HttpRequest, saved_id: int) -> HttpResponse:
    try:
        services.delete_saved(request.user, saved_id)
    except services.LobbyError as exc:
        messages.error(request, error_message(exc.code))
    return redirect(reverse("lobby:list") + "#my-settings")


def saved_rows(user) -> list[dict]:
    rows = []
    for saved in user.saved_settings.all():
        code = encode_share_code(saved.preset, saved.overrides)
        rows.append({"saved": saved, "use_url": create_path(code)})
    return rows


@login_required
def game_detail(request: HttpRequest, code: str) -> HttpResponse:
    game = _game(code)
    return render(request, "lobby/detail.html", seats_context(request, game))


@login_required
def game_seats(request: HttpRequest, code: str) -> HttpResponse:
    """The seats block alone; the lobby page refetches it when the WebSocket says something changed."""
    game = _game(code)
    return render(request, "lobby/_seats.html", seats_context(request, game))


QUICK_HEADER = "X-Lobby-Quick"


def _action(request: HttpRequest, code: str, fn, *args) -> HttpResponse:
    """Run a lobby action. A background request from the page (``QUICK_HEADER``) gets
    204, or 400 with the refusal as text; a normal form post goes back to the game page."""
    game = _game(code)
    quick = request.headers.get(QUICK_HEADER) == "1"
    try:
        fn(game, request.user, *args)
    except services.LobbyError as exc:
        if quick:
            return HttpResponse(str(error_message(exc.code)), status=400, content_type="text/plain; charset=utf-8")
        messages.error(request, error_message(exc.code))
    if quick:
        return HttpResponse(status=204)
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
def add_bot(request: HttpRequest, code: str) -> HttpResponse:
    """One bot, or with ``fill`` one in every free seat."""
    action = services.fill_with_bots if request.POST.get("fill") else services.add_bot
    return _action(request, code, action, request.POST.get("level", ""))


@login_required
@require_POST
def remove_bot(request: HttpRequest, code: str) -> HttpResponse:
    try:
        player_id = int(request.POST.get("player", ""))
    except ValueError:
        player_id = 0
    return _action(request, code, services.remove_bot, player_id)


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
