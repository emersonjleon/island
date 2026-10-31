from django import forms
from django.utils.translation import gettext_lazy as _

from engine.settings import available_presets

from .models import COLOURS

MS_PER_SECOND = 1000


class CreateGameForm(forms.Form):
    """Preset plus the few stage 1 overrides. Blank fields keep the preset's value."""

    preset = forms.ChoiceField(label=_("Preset"))
    max_players = forms.TypedChoiceField(
        label=_("Players"), coerce=int, choices=[(n, n) for n in (2, 3, 4)], initial=4
    )
    land_hexes = forms.IntegerField(
        label=_("Island size (land hexes)"), required=False, min_value=7, max_value=250,
        help_text=_("Blank keeps the preset (19 in Classic)."),
    )
    roll_interval = forms.IntegerField(
        label=_("Seconds between dice rolls"), required=False, min_value=5, max_value=120,
        help_text=_("Blank keeps the preset (20 in Classic)."),
    )
    target = forms.IntegerField(
        label=_("Points to win"), required=False, min_value=5, max_value=20,
        help_text=_("Blank keeps the preset (10 in Classic)."),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["preset"].choices = [(p, p.title()) for p in available_presets()]
        self.fields["preset"].initial = "classic"

    def overrides(self) -> dict:
        data = self.cleaned_data
        out: dict = {"players": {"max": data["max_players"]}}
        if data.get("land_hexes"):
            out["board"] = {"land_hexes": data["land_hexes"]}
        if data.get("roll_interval"):
            out["clock"] = {"roll_interval_ms": data["roll_interval"] * MS_PER_SECOND}
        if data.get("target"):
            out["victory"] = {"target": data["target"]}
        return out


class ColourForm(forms.Form):
    colour = forms.ChoiceField(choices=COLOURS)
