import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST
from django.views.i18n import set_language as django_set_language

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
