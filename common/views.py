from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from engine.settings import PlayersSettings, Resource, load_preset

# Resource names for the rules page (the game screen has its own catalogue).
RESOURCE_NAMES = {
    Resource.LUMBER: _("lumber"),
    Resource.BRICK: _("brick"),
    Resource.WOOL: _("wool"),
    Resource.GRAIN: _("grain"),
    Resource.ORE: _("ore"),
    Resource.FISH: _("fish"),
}
MS_PER_SECOND = 1000


def home(request: HttpRequest) -> HttpResponse:
    return render(request, "home.html")


def _cost(cost: dict) -> str:
    return ", ".join(f"{n} {RESOURCE_NAMES[r]}" for r, n in cost.items() if n)


def how_to_play(request: HttpRequest) -> HttpResponse:
    """The rules for new players. Every number comes from the Classic preset's settings."""
    s = load_preset("classic")
    costs, points, build = s.economy.costs, s.victory.building_points, s.build.time_ms
    buildings = [
        {"name": _("Road"), "cost": _cost(costs.road), "points": 0, "seconds": build.road // MS_PER_SECOND},
        {"name": _("Settlement"), "cost": _cost(costs.settlement), "points": points.settlement,
         "seconds": build.settlement // MS_PER_SECOND},
        {"name": _("City"), "cost": _cost(costs.city), "points": points.city, "seconds": build.city // MS_PER_SECOND},
        {"name": _("Megacity"), "cost": _cost(costs.megacity), "points": points.megacity,
         "seconds": build.megacity // MS_PER_SECOND},
    ]
    context = {
        "s": s,
        "buildings": buildings,
        "dev_card_cost": _cost(costs.dev_card),
        "roll_seconds": s.clock.roll_interval_ms // MS_PER_SECOND,
        "max_players": PlayersSettings.model_fields["max"].metadata[-1].le,
    }
    return render(request, "how_to_play.html", context)
