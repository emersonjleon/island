from django import forms
from django.utils.translation import gettext_lazy as _

from pydantic import ValidationError

from engine.settings import load_preset, merge_overrides

from .models import BOT_LEVELS, COLOURS
from .presets import CUSTOM, KNOBS, MIN_TABLE, base_presets, preset_label, preset_names, preset_values
from .messages import validation_message
from .settings_editor import editor_overrides, settings_by_path

# Settings the quick rules (KNOBS) already set; the "all settings" list leaves them out.
KNOB_PATHS = frozenset(".".join(k.path) for k in KNOBS)

MAX_PLAYERS = len(COLOURS)


class CreateGameForm(forms.Form):
    """A game type (preset) and table size; the custom type also takes every ``KNOBS`` setting.

    The custom type starts from ``base``, the game type chosen before it; blank custom
    fields keep that type's value (scaled to the table size).
    """

    preset = forms.ChoiceField(label=_("Game type"), widget=forms.RadioSelect)
    max_players = forms.TypedChoiceField(
        label=_("Players"), coerce=int, choices=[(n, n) for n in range(MIN_TABLE, MAX_PLAYERS + 1)], initial=4,
        help_text=_("More players than the game type is made for get a bigger island and bank automatically."),
    )

    base = forms.ChoiceField(required=False, widget=forms.HiddenInput)
    bot_level = forms.ChoiceField(label=_("Bot level"), choices=BOT_LEVELS, initial="medium", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["preset"].choices = [(p, preset_label(p)) for p in preset_names()]
        self.fields["preset"].initial = "classic"
        self.fields["base"].choices = [(p, p) for p in base_presets()]
        self.fields["base"].initial = "classic"
        base = preset_values(self.base_name(), 4) if CUSTOM in preset_names() else {}
        for knob in KNOBS:
            if knob.boolean:
                field = forms.BooleanField(label=knob.label, required=False, initial=base.get(knob.name, False))
            else:
                field = forms.IntegerField(label=knob.label, required=False, min_value=knob.min, max_value=knob.max)
                field.widget.attrs.update({"inputmode": "numeric", "placeholder": base.get(knob.name, "")})
            field.help_text = knob.help
            field.knob = knob
            self.fields[knob.name] = field

    def clean_bot_level(self):
        return self.cleaned_data.get("bot_level") or "medium"

    def base_name(self) -> str:
        """The game type a custom game starts from (what was posted, else Classic)."""
        valid = dict(self.fields["base"].choices)
        if hasattr(self, "cleaned_data") and self.cleaned_data.get("base") in valid:
            return self.cleaned_data["base"]
        posted = self.data.get("base") if self.is_bound else None
        return posted if posted in valid else self.fields["base"].initial

    def chosen_preset(self) -> str:
        """The game type the new game is stored with: a custom game keeps its base type."""
        preset = self.cleaned_data["preset"]
        return self.base_name() if preset == CUSTOM else preset

    def knob_fields(self):
        return [self[k.name] for k in KNOBS]

    def overrides(self) -> dict:
        data = self.cleaned_data
        out: dict = {"players": {"max": data["max_players"]}}
        if data["preset"] != CUSTOM:
            return out
        base = preset_values(self.base_name(), data["max_players"])
        for knob in KNOBS:
            value = data.get(knob.name)
            if knob.boolean and value == base[knob.name]:
                continue
            if value is None:
                continue
            out = merge_overrides(out, knob.override(value))
        return merge_overrides(out, self.editor_changes)

    # ------------------------------------------------------- all settings
    editor_changes: dict = {}
    editor_errors: dict = {}

    def clean(self):
        cleaned = super().clean()
        self.editor_changes, self.editor_errors = {}, {}
        if self.errors or cleaned.get("preset") != CUSTOM:
            return cleaned
        players = cleaned["max_players"]
        base = load_preset(self.base_name(), {"players": {"max": players}}, players=players)
        self.editor_changes, errors = editor_overrides(self.data, base, exclude=KNOB_PATHS)
        self.editor_errors = {e.setting.path: e.message for e in errors}
        if errors:
            raise forms.ValidationError(_("Some settings are not valid: they are marked below."))
        self._check_together()
        return cleaned

    def _check_together(self) -> None:
        """Validate the whole set; errors go to the setting they name when the editor shows it."""
        try:
            load_preset(self.chosen_preset(), self.overrides())
        except ValidationError as exc:
            known = settings_by_path()
            for err in exc.errors():
                path = ".".join(str(p) for p in err["loc"] if not isinstance(p, int))
                while path and path not in known:
                    path = path.rpartition(".")[0]
                message = validation_message(err.get("type", ""))
                knob = next((k for k in KNOBS if ".".join(k.path) == path), None)
                if knob is not None:
                    self.add_error(knob.name, message)
                elif path:
                    self.editor_errors[path] = message
                else:
                    self.add_error(None, message)
            if self.editor_errors:
                raise forms.ValidationError(_("Some settings are not valid: they are marked below.")) from exc

class ColourForm(forms.Form):
    colour = forms.ChoiceField(choices=COLOURS)
