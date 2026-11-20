import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST
from django.views.i18n import set_language as django_set_language

from . import devmode
from .forms import ProfileForm, SignUpForm
from .keybindings import KeybindingsError, validate_keybindings

MAX_BODY_BYTES = 16 * 1024


def signup(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return redirect(settings.LOGIN_REDIRECT_URL)
    return render(request, "accounts/signup.html", {"form": form})


@login_required
def profile(request: HttpRequest) -> HttpResponse:
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Profile saved."))
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"form": form})


@require_POST
def set_language(request: HttpRequest) -> HttpResponse:
    """Django's set_language, which also saves the choice on a signed-in user."""
    language = request.POST.get("language", "")
    if request.user.is_authenticated and language in dict(settings.LANGUAGES):
        request.user.preferred_language = language
        request.user.save(update_fields=["preferred_language"])
    return django_set_language(request)


@require_http_methods(["GET", "PUT"])
def keybindings(request: HttpRequest) -> JsonResponse:
    """GET returns the saved map ({} means client defaults); PUT replaces it."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "auth.required"}, status=401)
    if request.method == "GET":
        return JsonResponse({"keybindings": request.user.keybindings})
    if len(request.body) > MAX_BODY_BYTES:
        return JsonResponse({"error": "keybindings.too_large"}, status=413)
    try:
        payload = json.loads(request.body or b"null")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "keybindings.bad_json"}, status=400)
    data = payload.get("keybindings") if isinstance(payload, dict) else None
    try:
        clean = validate_keybindings(data)
    except KeybindingsError as exc:
        return JsonResponse({"error": exc.code}, status=400)
    request.user.keybindings = clean
    request.user.save(update_fields=["keybindings"])
    return JsonResponse({"keybindings": clean})


# ------------------------------------------------------------------ developer panel

@devmode.developer_required
def dev_overview(request: HttpRequest) -> HttpResponse:
    return render(request, "accounts/dev/overview.html", devmode.overview())


@devmode.developer_required
def dev_games(request: HttpRequest) -> HttpResponse:
    page = Paginator(devmode.game_table(), devmode.GAMES_PER_PAGE).get_page(request.GET.get("page"))
    return render(request, "accounts/dev/games.html", {"page": page})


@devmode.developer_required
def dev_users(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", devmode.DEFAULT_USER_SORT)
    if sort not in devmode.USER_SORTS:
        sort = devmode.DEFAULT_USER_SORT
    page = Paginator(devmode.user_table(query, sort), devmode.USERS_PER_PAGE).get_page(request.GET.get("page"))
    return render(request, "accounts/dev/users.html", {
        "page": page, "query": query, "sort": sort, "sorts": True,
        "sort_headers": [
            ("name", _("User")), ("joined", _("Joined")), ("login", _("Last login")),
            ("games", _("Games")), ("wins", _("Wins")), ("messages", _("Messages")),
        ],
        "numeric_sorts": {"games", "wins", "messages"},
    })
