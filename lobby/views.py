from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from engine.settings import load_preset

from . import services
from .forms import KNOB_PATHS, CreateGameForm
from .messages import error_message
from .models import BOT_LEVELS, COLOURS, Game, GameStatus
from .presets import (
    CUSTOM, GROUPS, KNOBS, KNOBS_BY_NAME, STATS, default_players, experimental_names, preset_description,
    preset_label, preset_values,
    base_presets, presets_data, settings_values, stats_rows,
)
from .setting_labels import CHOICES, LABELS
from .settings_editor import EXPERIMENTAL, changed_settings, editor_data, editor_view, is_experimental
from .prefill import settings_form_data


def _game(code: str) -> Game:
    return get_object_or_404(Game.objects.select_related("host"), code=code.upper())


SAVED_PARAM = "saved"
FOLLOW_PARAM = "follow"   # the game page goes to the game by itself once it runs


@login_required
def game_list(request: HttpRequest) -> HttpResponse:
    """The lobby: open games, the player's saved settings and the create form. ``?saved=<id>``
    fills the form with saved settings."""
    active = _saved_from(request)
    if request.method == "POST":
        form = CreateGameForm(request.POST)
    elif active is not None:
        form = CreateGameForm(settings_form_data(active.preset, active.overrides))
    else:
        # ``?custom=1`` opens Custom (where the saved settings live), e.g. after deleting one.
        form = CreateGameForm(initial={"preset": CUSTOM} if request.GET.get("custom") else None)
    if request.method == "POST" and request.POST.get("save_as"):
        saved = _save_from_form(request, form)
        if saved is not None:
            return redirect(f"{reverse('lobby:list')}?{SAVED_PARAM}={saved.pk}#create-game")
    elif request.method == "POST" and form.is_valid():
        try:
            game = services.create_game(request.user, form.chosen_preset(), form.overrides())
        except services.LobbyError as exc:
            form.add_error(None, error_message(exc.code))
        else:
            if request.POST.get("play_bots"):
                _play_against_bots(request, game, form.cleaned_data["bot_level"])
                # The game may be running before the page loads: tell the page to follow it.
                return redirect(f"{reverse('lobby:detail', args=[game.code])}?{FOLLOW_PARAM}=1")
            return redirect("lobby:detail", code=game.code)
    open_games = Game.objects.filter(status=GameStatus.LOBBY).select_related("host").prefetch_related("players")
    mine = (
        Game.objects.filter(players__user=request.user, status__in=[GameStatus.STARTING, GameStatus.RUNNING])
        .select_related("host")
        .distinct()
    )
    context = {"form": form, "open_games": open_games[:50], "my_games": mine,
               "saved_settings": saved_rows(request.user, active), "active_saved": active,
               "max_saved": services.MAX_SAVED_PER_USER,
               "save_name": request.POST.get("save_name", "") if request.method == "POST"
               else (active.name if active else "")}
    return render(request, "lobby/list.html", context | create_form_context(form))


def _saved_from(request: HttpRequest):
    raw = request.GET.get(SAVED_PARAM, "")
    if not raw.isdigit():
        return None
    return request.user.saved_settings.filter(pk=int(raw)).first()


def _save_from_form(request: HttpRequest, form: CreateGameForm):
    """Keep the form's settings under the posted name; None (with the error on the form) if not."""
    if not form.is_valid():
        return None
    try:
        saved = services.save_settings(request.user, request.POST.get("save_name", ""),
                                       form.chosen_preset(), form.overrides())
    except services.LobbyError as exc:
        form.add_error(None, error_message(exc.code))
        return None
    messages.success(request, _("Saved as \u201c%(name)s\u201d. It is ready under My settings.") % {"name": saved.name})
    return saved


def _play_against_bots(request: HttpRequest, game: Game, level: str) -> None:
    """Fill the new game's free seats with bots and start it at once."""
    try:
        services.fill_with_bots(game, request.user, level)
        services.start_game(game, request.user)
    except services.LobbyError as exc:
        messages.error(request, error_message(exc.code))


def _chosen(form: CreateGameForm) -> tuple[str, int]:
    """The game type and table size the form shows (what was posted, else the initial ones)."""
    preset = form.data.get("preset") or form.initial.get("preset") or form.fields["preset"].initial
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
    editor = editor_view(form.data if form.is_bound else {}, base, KNOB_PATHS, form.editor_errors)
    posted = [k[2:].split(":")[0] for k, v in (form.data.items() if form.is_bound else []) if k.startswith("s:") and v]
    groups = []
    for key, label in GROUPS:
        fields = [form[k.name] for k in KNOBS if k.group == key]
        typed = form.is_bound and any(form.data.get(k.name) for k in KNOBS if k.group == key and not k.boolean)
        groups.append({"key": key, "label": label, "fields": fields,
                       "open": typed or any(f.errors for f in fields)})
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
        "editor": [g for g in editor if g["key"] != EXPERIMENTAL],
        "experimental_editor": next((g for g in editor if g["key"] == EXPERIMENTAL), None),
        # "Start from" in Custom: every game type a custom game can start from (beta ones marked).
        "base_choices": [
            {"name": name, "label": preset_label(name), "description": preset_description(name),
             "selected": name == base, "experimental": name in experimental_names()}
            for name in base_presets()
        ],
        "editor_open": any(not is_experimental(p) for p in form.editor_errors) or any(
            not is_experimental(path) for path in posted),
        "experimental_open": any(is_experimental(p) for p in form.editor_errors) or any(
            is_experimental(path) for path in posted),
        "editor_data": editor_data(),
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
        "stats": stats_rows(settings_values(settings)) + visibility_rows(settings),
        "rule_changes": rule_changes(game.preset, settings),
    } | again_context(game, me)


def again_context(game: Game, me) -> dict:
    """Play again on a finished game: who may press it, and the new game another player started."""
    if game.status != GameStatus.FINISHED:
        return {"can_play_again": False, "rematch": None}
    rematch = game.rematch
    if rematch is not None and rematch.status != GameStatus.LOBBY:
        rematch = None
    in_rematch = rematch is not None and me is not None and rematch.players.filter(user_id=me.user_id).exists()
    return {
        "can_play_again": me is not None and not me.is_bot,
        "rematch": rematch,
        "rematch_host": rematch.host.public_name if rematch is not None else "",
        "in_rematch": in_rematch,
    }


def visibility_rows(settings) -> list[tuple]:
    """A summary line when players do not see the whole map (Growing sight)."""
    if settings.visibility.map.value == "open":
        return []
    return [(LABELS["visibility.map"][0], CHOICES.get(("MapVisibility", settings.visibility.map.value), ""))]


def rule_changes(preset: str, settings) -> list[tuple]:
    """The settings changed from the game type that the summary does not already show."""
    players = settings.players.max
    base = load_preset(preset, {"players": {"max": players}}, players=players)
    shown = {".".join(KNOBS_BY_NAME[k].path) for _label, knobs in STATS for k in knobs} | {"visibility.map"}
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
    return redirect(reverse("lobby:list") + "?custom=1#my-settings")


def saved_rows(user, active=None) -> list[dict]:
    """The player's saved settings, each with the link that fills the create form with them."""
    base = reverse("lobby:list")
    return [{"saved": saved, "use_url": f"{base}?{SAVED_PARAM}={saved.pk}#create-game",
             "active": active is not None and saved.pk == active.pk}
            for saved in user.saved_settings.all()]


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


@login_required
@require_POST
def play_again(request: HttpRequest, code: str) -> HttpResponse:
    """Start the same game again (same settings, table size and bots), or join the one already started."""
    game = _game(code)
    try:
        rematch = services.play_again(game, request.user)
    except services.LobbyError as exc:
        messages.error(request, error_message(exc.code))
        return redirect("lobby:detail", code=game.code)
    return redirect("lobby:detail", code=rematch.code)
