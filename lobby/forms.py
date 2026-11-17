from django import forms
from django.utils.translation import gettext_lazy as _

from engine.settings import merge_overrides

from .models import COLOURS
from .presets import CUSTOM, KNOBS, MIN_TABLE, preset_label, preset_names, preset_values

MAX_PLAYERS = len(COLOURS)


class CreateGameForm(forms.Form):
    """A game type (preset) and table size; the custom type also takes every ``KNOBS`` setting.

    Blank custom fields keep the Classic value (scaled to the table size).
    """

    preset = forms.ChoiceField(label=_("Game type"), widget=forms.RadioSelect)
    max_players = forms.TypedChoiceField(
        label=_("Players"), coerce=int, choices=[(n, n) for n in range(MIN_TABLE, MAX_PLAYERS + 1)], initial=4,
        help_text=_("More players than the game type is made for get a bigger island and bank automatically."),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["preset"].choices = [(p, preset_label(p)) for p in preset_names()]
        self.fields["preset"].initial = "classic"
        base = preset_values(CUSTOM, 4) if CUSTOM in preset_names() else {}
        for knob in KNOBS:
            if knob.boolean:
                field = forms.BooleanField(label=knob.label, required=False, initial=base.get(knob.name, False))
            else:
                field = forms.IntegerField(label=knob.label, required=False, min_value=knob.min, max_value=knob.max)
                field.widget.attrs.update({"inputmode": "numeric", "placeholder": base.get(knob.name, "")})
            field.help_text = knob.help
            field.knob = knob
            self.fields[knob.name] = field

    def knob_fields(self):
        return [self[k.name] for k in KNOBS]

    def overrides(self) -> dict:
        data = self.cleaned_data
        out: dict = {"players": {"max": data["max_players"]}}
        if data["preset"] != CUSTOM:
            return out
        base = preset_values(CUSTOM, data["max_players"])
        for knob in KNOBS:
            value = data.get(knob.name)
            if knob.boolean and value == base[knob.name]:
                continue
            if value is None:
                continue
            out = merge_overrides(out, knob.override(value))
        return out


class ColourForm(forms.Form):
    colour = forms.ChoiceField(choices=COLOURS)
