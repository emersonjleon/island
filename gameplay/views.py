from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import get_language
from django.utils.translation import gettext as _

from gamehost.models import GameSnapshot

from lobby.models import Game, GameStatus


@login_required
def play(request: HttpRequest, code: str) -> HttpResponse:
    """The game page: an empty shell the client bundle fills in over the WebSocket."""
    game = Game.objects.filter(code=code.upper()).first()
    if game is None:
        messages.info(request, _("That game does not exist any more."))
        return redirect("lobby:list")
    if game.status in (GameStatus.LOBBY, GameStatus.ABORTED):
        return redirect("lobby:detail", code=game.code)
    if game.status == GameStatus.FINISHED and not GameSnapshot.objects.filter(game=game).exists():
        # Old games may have had their board cleaned up: show the game's page, not a blank board.
        messages.info(request, _("This game is over and its board is no longer kept."))
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
        "helpUrl": reverse("how_to_play"),
    }
    return render(request, "gameplay/game.html", {"game": game, "config": config, "seat": seat})
