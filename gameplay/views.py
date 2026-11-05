from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import get_language

from lobby.models import Game, GameStatus


@login_required
def play(request: HttpRequest, code: str) -> HttpResponse:
    """The game page: an empty shell the client bundle fills in over the WebSocket."""
    game = get_object_or_404(Game, code=code.upper())
    if game.status in (GameStatus.LOBBY, GameStatus.ABORTED):
        return redirect("lobby:detail", code=game.code)
    seat = game.players.filter(user=request.user).values_list("seat", flat=True).first()
    config = {
        "game": game.code,
        "wsPath": f"/ws/play/{game.code}/",
        "seat": seat,
        "status": game.status,
        "lang": (get_language() or "en").split("-")[0],
        "keybindings": request.user.keybindings,
        "keybindingsUrl": "/accounts/keybindings/",
        "uiPrefs": request.user.ui_prefs,
        "lobbyUrl": f"/lobby/{game.code}/",
    }
    return render(request, "gameplay/game.html", {"game": game, "config": config, "seat": seat})
