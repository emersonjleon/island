from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from engine.settings import BuildKind, PlayersSettings, Resource, load_preset

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
        **_variant_rules(),
        "buildings": buildings,
        "dev_card_cost": _cost(costs.dev_card),
        "roll_seconds": s.clock.roll_interval_ms // MS_PER_SECOND,
        "max_players": PlayersSettings.model_fields["max"].metadata[-1].le,
    }
    return render(request, "how_to_play.html", context)


def _variant_rules() -> dict:
    """Numbers for the right-hand column of the rules page (ages, settlers, hidden
    island, friendly robber), each from the game type that introduces it."""
    ages = load_preset("ages")
    a = ages.ages
    steps = []
    for name, step in ((_("Age of the Sea (II)"), a.age2), (_("Golden Age (III)"), a.age3)):
        steps.append({"name": name, "cost": _cost(step.cost), "seconds": step.time_ms // MS_PER_SECOND,
                      "cities": step.requires.cities, "points": step.bonus.points,
                      "fish": step.bonus.fish_per_fishing_building, "card_limit": step.bonus.card_limit,
                      "build_pct": step.bonus.build_time_pct})
    settlers = load_preset("settlers")
    ss = settlers.settlers
    both = load_preset("ages_settlers")
    explorer = load_preset("explorer")
    return {
        "ages": ages,
        "age_steps": steps,
        "megacity_age": a.unlock.get(BuildKind.MEGACITY, 1),
        "settlers": settlers,
        "settler_cost": _cost(settlers.economy.costs.settler),
        "gather_rolls": ", ".join(" / ".join(str(n) for n in rolls) for rolls in ss.gather_rolls),
        "population": both.ages.largest_population,
        "both": both,
        "explorer": explorer,
        "friendly": load_preset("friendly"),
    }
