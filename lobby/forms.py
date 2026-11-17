from django import forms
from django.utils.translation import gettext_lazy as _

from engine.settings import merge_overrides
from engine.settings.share import MAX_CODE_LENGTH

from .models import COLOURS
from .presets import CUSTOM, KNOBS, MIN_TABLE, preset_label, preset_names, preset_values
from .messages import error_message
from .services import LobbyError
from .sharing import read_code

MAX_PLAYERS = len(COLOURS)


class CreateGameForm(forms.Form):
    """A game type (preset) and table size; the custom type also takes every ``KNOBS`` setting.

    Blank custom fields keep the Classic value (scaled to the table size). A settings
    code (``config``) replaces all of them: the game gets the code's type and rules.
    """

    preset = forms.ChoiceField(label=_("Game type"), widget=forms.RadioSelect)
    max_players = forms.TypedChoiceField(
        label=_("Players"), coerce=int, choices=[(n, n) for n in range(MIN_TABLE, MAX_PLAYERS + 1)], initial=4,
        help_text=_("More players than the game type is made for get a bigger island and bank automatically."),
    )

    config = forms.CharField(
        label=_("Settings code"), required=False, max_length=MAX_CODE_LENGTH,
        help_text=_("Paste a code copied from another game to play with its rules. It replaces the choices below."),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["config"].widget.attrs.update({"autocomplete": "off", "spellcheck": "false"})
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

    def clean_config(self):
        code = "".join((self.cleaned_data.get("config") or "").split())
        if not code:
            return None
        try:
            return read_code(code)
        except LobbyError as exc:
            raise forms.ValidationError(error_message(exc.code)) from exc

    def chosen_preset(self) -> str:
        shared = self.cleaned_data.get("config")
        return shared.preset if shared else self.cleaned_data["preset"]

    def knob_fields(self):
        return [self[k.name] for k in KNOBS]

    def overrides(self) -> dict:
        data = self.cleaned_data
        if data.get("config"):
            return dict(data["config"].overrides)
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
