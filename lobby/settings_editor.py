"""The "all settings" editor of a custom game: every setting the server implements.

The list is built from ``GameSettings`` itself (bounds, choices, stage), so a new
setting appears once it has a name in ``setting_labels.LABELS``. Each setting is
one form input (a map setting is one input per key) named ``s:<path>`` (``s:<path>:<key>``).
A blank input keeps the value of the game type the custom game starts from.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from functools import lru_cache
from types import UnionType
from typing import Any, Union, get_args, get_origin

from django.utils.translation import gettext, gettext_lazy as _
from pydantic import BaseModel

from engine.settings import IMPLEMENTED_STAGE, GameSettings, feature_stage, load_preset, merge_overrides, value_stage

from .presets import base_presets
from .setting_labels import CHOICES, GROUP_LABELS, KEY_LABELS, LABELS, SUBGROUP_LABELS

PREFIX = "s:"
MS_PER_SECOND = 1000
_MS_SUFFIX = "_ms"
# The table size has its own field on the create form.
SKIPPED = {"schema_version", "preset", "players.max"}


@dataclass(frozen=True)
class Setting:
    path: str
    kind: str  # "int" | "seconds" | "bool" | "choice" | "map"
    label: Any
    help: Any = ""
    group: str = ""
    subgroup: str = ""
    min: int | None = None
    max: int | None = None
    optional: bool = False
    choices: tuple[tuple[str, Any], ...] = ()
    keys: tuple[tuple[str, Any], ...] = ()
    enum: str = ""

    @property
    def name(self) -> str:
        return PREFIX + self.path

    def key_name(self, key: str) -> str:
        return f"{self.name}:{key}"

    @property
    def parts(self) -> tuple[str, ...]:
        return tuple(self.path.split("."))

    def read(self, settings: GameSettings) -> Any:
        value: Any = settings
        for part in self.parts:
            value = getattr(value, part)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, Mapping):
            return {(k.value if isinstance(k, Enum) else k): v for k, v in value.items()}
        return value

    def override(self, value: Any) -> dict[str, Any]:
        leaf: Any = value
        for part in reversed(self.parts):
            leaf = {part: leaf}
        return leaf

    # ---------------------------------------------------------------- display
    def show(self, value: Any) -> str:
        """``value`` (as stored in the settings) as the form shows it."""
        if value is None:
            return gettext("auto")
        if self.kind == "bool":
            return gettext("Yes") if value else gettext("No")
        if self.kind == "choice":
            return str(dict(self.choices).get(value, value))
        if self.kind == "seconds":
            return seconds_text(value)
        if self.kind == "map":
            labels = dict(self.keys)
            parts = [f"{labels.get(k, k)} {n}" for k, n in value.items() if n]
            return ", ".join(parts) if parts else "0"
        return str(value)

    def input_value(self, value: Any, key: str | None = None) -> str:
        """``value`` as the text of this setting's input (placeholder)."""
        if key is not None:
            return str((value or {}).get(key, 0))
        if value is None:
            return ""
        if self.kind == "bool":
            return "1" if value else "0"
        if self.kind == "seconds":
            return seconds_text(value)
        return str(value)


def seconds_text(ms: int) -> str:
    whole, rest = divmod(int(ms), MS_PER_SECOND)
    return str(whole) if not rest else f"{whole}.{rest:03d}".rstrip("0")


@dataclass
class Group:
    key: str
    label: Any
    sections: list[tuple[Any, list[Setting]]] = field(default_factory=list)


# ------------------------------------------------------------------ building
def _bounds(info) -> tuple[int | None, int | None]:
    low = high = None
    for m in info.metadata:
        low = getattr(m, "ge", low)
        high = getattr(m, "le", high)
    return low, high


def _inner_bounds(annotation) -> tuple[int | None, int | None]:
    """Bounds of an ``Annotated`` member of ``annotation`` (an optional int, or a map's values)."""
    for arg in get_args(annotation):
        meta = getattr(arg, "__metadata__", ())
        low = high = None
        for m in meta:
            for item in getattr(m, "metadata", [m]):
                low = getattr(item, "ge", low)
                high = getattr(item, "le", high)
        if low is not None or high is not None:
            return low, high
    return None, None


def _allowed(enum_cls: type[Enum], implemented: int, path: str) -> list[Enum]:
    return [v for v in enum_cls if feature_stage(path, value_stage(v), v.value) <= implemented]


def _setting(path: str, info, group: str, subgroup: str, implemented: int) -> Setting | None:
    if path in SKIPPED or path not in LABELS:
        return None
    label, help_text = LABELS[path]
    annotation = info.annotation
    optional = False
    if get_origin(annotation) in (Union, UnionType):
        args = [a for a in get_args(annotation) if a is not type(None)]
        optional = len(args) < len(get_args(annotation))
        annotation = args[0] if len(args) == 1 else annotation
    common = {"label": label, "help": help_text, "group": group, "subgroup": subgroup, "optional": optional}
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        allowed = _allowed(annotation, implemented, path)
        if len(allowed) < 2:
            return None
        choices = tuple((v.value, CHOICES.get((annotation.__name__, v.value), v.value)) for v in allowed)
        return Setting(path, "choice", choices=choices, enum=annotation.__name__, **common)
    if annotation is bool:
        return Setting(path, "bool", **common)
    if annotation is int:
        low, high = _bounds(info)
        if optional and low is None and high is None:
            low, high = _inner_bounds(info.annotation)
        name = path.rsplit(".", 1)[-1]
        in_ms = name.endswith(_MS_SUFFIX) or name.startswith("ms_") or ".time_ms." in path
        kind = "seconds" if in_ms else "int"
        return Setting(path, kind, min=low, max=high, **common)
    if get_origin(annotation) is dict:
        key_type, value_type = get_args(annotation)
        if not (isinstance(key_type, type) and issubclass(key_type, Enum)):
            return None
        low, high = _inner_bounds(annotation)
        keys = tuple((k.value, KEY_LABELS.get(k.value, k.value)) for k in key_type)
        return Setting(path, "map", keys=keys, min=low, max=high, **common)
    return None


def _walk(model: type[BaseModel], prefix: str, stage: int, implemented: int, out: list[Setting],
          group: str, subgroup: str) -> None:
    for name, info in model.model_fields.items():
        extra = info.json_schema_extra if isinstance(info.json_schema_extra, dict) else {}
        path = f"{prefix}.{name}" if prefix else name
        field_stage = feature_stage(path, max(stage, int(extra.get("stage", 1))))
        if field_stage > implemented:
            continue
        annotation = info.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            top = group or name
            sub = path if prefix else ""
            _walk(annotation, path, field_stage, implemented, out, top, sub)
            continue
        setting = _setting(path, info, group or name, subgroup, implemented)
        if setting is not None:
            out.append(setting)


@lru_cache(maxsize=4)
def all_settings(implemented: int = IMPLEMENTED_STAGE) -> tuple[Setting, ...]:
    out: list[Setting] = []
    _walk(GameSettings, "", 1, implemented, out, "", "")
    return tuple(out)


def settings_by_path() -> dict[str, Setting]:
    return {s.path: s for s in all_settings()}


def editor_groups(exclude: set[str] | frozenset[str] = frozenset()) -> list[Group]:
    """The editor's settings by group and sub-group, leaving out the paths in ``exclude``."""
    groups: dict[str, Group] = {}
    for setting in all_settings():
        if setting.path in exclude:
            continue
        group = groups.setdefault(setting.group, Group(setting.group, GROUP_LABELS.get(setting.group, setting.group)))
        heading = SUBGROUP_LABELS.get(setting.subgroup, "") if setting.subgroup else ""
        if not group.sections or group.sections[-1][0] != heading:
            group.sections.append((heading, []))
        group.sections[-1][1].append(setting)
    return list(groups.values())


# ------------------------------------------------------------------ reading
class EditorError(ValueError):
    def __init__(self, setting: Setting, message: Any):
        super().__init__(str(message))
        self.setting = setting
        self.message = message


def _parse_int(setting: Setting, raw: str) -> int:
    try:
        if setting.kind == "seconds":
            value = int(Decimal(raw.replace(",", ".")) * MS_PER_SECOND)
        else:
            value = int(raw)
    except (InvalidOperation, ValueError) as exc:
        raise EditorError(setting, _("Enter a whole number.") if setting.kind != "seconds"
                          else _("Enter a number of seconds.")) from exc
    low, high = setting.min, setting.max
    if (low is not None and value < low) or (high is not None and value > high):
        shown_low = setting.show(low) if low is not None else ""
        shown_high = setting.show(high) if high is not None else ""
        raise EditorError(setting, _("Enter a value from %(low)s to %(high)s.") % {"low": shown_low,
                                                                                   "high": shown_high})
    return value


def _parse(setting: Setting, data: Mapping[str, str], base: Any) -> tuple[bool, Any]:
    """(given, value) for ``setting`` from the posted ``data``; blank inputs are not given."""
    if setting.kind == "map":
        raws = {k: (data.get(setting.key_name(k)) or "").strip() for k, _label in setting.keys}
        if not any(raws.values()):
            return False, None
        value = dict(base or {})
        for key, raw in raws.items():
            if raw:
                value[key] = _parse_int(setting, raw)
        return True, value
    raw = (data.get(setting.name) or "").strip()
    if not raw:
        return False, None
    if setting.kind == "bool":
        if raw not in ("0", "1"):
            raise EditorError(setting, _("Choose yes or no."))
        return True, raw == "1"
    if setting.kind == "choice":
        if raw not in dict(setting.choices):
            raise EditorError(setting, _("Choose one of the options."))
        return True, raw
    return True, _parse_int(setting, raw)


def editor_overrides(data: Mapping[str, str], base: GameSettings,
                     exclude: set[str] | frozenset[str] = frozenset()) -> tuple[dict[str, Any], list[EditorError]]:
    """The overrides the posted editor inputs make on top of ``base``, and the inputs' errors."""
    overrides: dict[str, Any] = {}
    errors: list[EditorError] = []
    for setting in all_settings():
        if setting.path in exclude:
            continue
        current = setting.read(base)
        try:
            given, value = _parse(setting, data, current)
        except EditorError as exc:
            errors.append(exc)
            continue
        if given and value != current:
            overrides = merge_overrides(overrides, setting.override(value))
    return overrides, errors


def label_of(path: str) -> Any:
    """The editor label of the setting at ``path`` with its group, or None when not in the editor."""
    setting = settings_by_path().get(path)
    if setting is None:
        return None
    group = GROUP_LABELS.get(setting.group, setting.group)
    sub = SUBGROUP_LABELS.get(setting.subgroup) if setting.subgroup else None
    return " · ".join(str(x) for x in (group, sub, setting.label) if x)


def changed_settings(base: GameSettings, settings: GameSettings,
                     exclude: set[str] | frozenset[str] = frozenset()) -> list[tuple[str, str]]:
    """(label, value) of every editor setting that differs between ``base`` and ``settings``."""
    out = []
    for setting in all_settings():
        if setting.path in exclude:
            continue
        value = setting.read(settings)
        if value != setting.read(base):
            out.append((label_of(setting.path), setting.show(value)))
    return out


@lru_cache(maxsize=None)
def preset_inputs(preset: str) -> dict[str, str]:
    """Each input's text in ``preset`` (at its own table size): the editor's placeholders."""
    settings = load_preset(preset)
    out: dict[str, str] = {}
    for setting in all_settings():
        value = setting.read(settings)
        if setting.kind == "map":
            for key, _label in setting.keys:
                out[setting.key_name(key)] = setting.input_value(value, key)
        else:
            out[setting.name] = setting.input_value(value)
    return out


# ------------------------------------------------------------------ form view
def editor_view(data: Mapping[str, str], base_preset: str, exclude: set[str] | frozenset[str],
                errors: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Groups, sections and rows ready for the template: each row's inputs with the
    posted text, the base type's text as placeholder, and the row's error."""
    placeholders = preset_inputs(base_preset)
    groups = []
    for group in editor_groups(exclude):
        sections = []
        for heading, settings in group.sections:
            rows = []
            for setting in settings:
                names = ([(setting.key_name(k), label) for k, label in setting.keys] if setting.kind == "map"
                         else [(setting.name, "")])
                inputs = [{"name": n, "label": label, "value": data.get(n, ""), "placeholder": placeholders.get(n, "")}
                          for n, label in names]
                rows.append({"setting": setting, "inputs": inputs, "error": errors.get(setting.path)})
            sections.append({"heading": heading, "rows": rows})
        groups.append({"key": group.key, "label": group.label, "sections": sections})
    return groups


def editor_data() -> dict[str, Any]:
    """Placeholders of every base game type, for the page script (JSON-ready)."""
    return {"placeholders": {p: preset_inputs(p) for p in base_presets()}}
