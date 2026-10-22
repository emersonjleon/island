"""Server -> client events (protocol §4.3), as Pydantic v2 models.

Every event has ``k`` (discriminator) and ``at`` (game ms when it happened) and
carries resulting values, never text. Events are frozen; build them with keyword
arguments, e.g. ``DiceRolled(at=now, dice=[3, 4], sum=7, next_roll_at=now + iv)``.
Resource maps are ``dict[Resource, int]``; seat-keyed maps are ``dict[int, ...]``
(serialised with string keys, e.g. ``{"2": {...}}``).

Audience (used by ``views.filter_events``):

* ``audience = "public"``: everyone gets :meth:`Event.public` (the full event,
  except :class:`Produced` with ``visibility.production_log = own``);
* ``audience = "private"``: the event's ``seat`` gets the full event; everyone
  else (other seats and spectators, ``viewer=None``) gets :meth:`Event.redacted`,
  which may return ``None`` (event not sent).

Hand-related redaction follows ``settings.visibility.hands``: ``open`` -> full
event, ``counts`` -> the resource map replaced by its total (``<field>_count``),
``hidden`` -> not sent.
"""
from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from engine.settings.enums import BuildKind, InfoVisibility, ProductionLog, Resource
from engine.settings.models import VisibilitySettings

__all__ = [
    "Event", "AnyEvent", "EVENT_TYPES", "parse_event", "event_json_schema",
    "ClockStarted", "DiceRolled", "Produced", "RobberStole", "RobberMoved", "Hand", "SettlerLanded",
    "SettlerPath", "SettlerStepEvent", "SettlerArrived", "SettlerLeft", "ConstructionStarted",
    "ConstructionCancelled", "Built", "SetupComplete", "StartingResources", "StartingMaterials", "Traded",
    "Points", "Buildable", "GameOver",
]

ResMap = dict[Resource, int]
_DEFAULT_VIS = VisibilitySettings()


class Event(BaseModel):
    """Base class. Subclasses set ``k`` (Literal) and their fields."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    audience: ClassVar[Literal["public", "private"]] = "public"
    k: str
    at: int

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def public(self, viewer: int | None, vis: VisibilitySettings) -> dict[str, Any] | None:
        """Form sent to ``viewer`` for public events."""
        return self.to_dict()

    def redacted(self, vis: VisibilitySettings) -> dict[str, Any] | None:
        """Form of a private event for non-owners. Default: not sent."""
        return None

    def view_for(self, viewer: int | None, vis: VisibilitySettings | None = None) -> dict[str, Any] | None:
        """The JSON dict ``viewer`` (seat, or None = spectator) receives, or None."""
        vis = vis or _DEFAULT_VIS
        if self.audience == "public":
            return self.public(viewer, vis)
        if viewer is not None and viewer == getattr(self, "seat"):
            return self.to_dict()
        return self.redacted(vis)

    def _hand_redacted(self, field_name: str) -> dict[str, Any]:
        d = self.to_dict()
        d[f"{field_name}_count"] = sum(d.pop(field_name).values())
        return d

    def _by_hands(self, vis: VisibilitySettings, field_name: str) -> dict[str, Any] | None:
        if vis.hands is InfoVisibility.OPEN:
            return self.to_dict()
        if vis.hands is InfoVisibility.COUNTS:
            return self._hand_redacted(field_name)
        return None


# ------------------------------------------------------------------ clock
class ClockStarted(Event):
    k: Literal["clock_started"] = "clock_started"
    next_roll_at: int


class DiceRolled(Event):
    k: Literal["dice_rolled"] = "dice_rolled"
    dice: list[int]
    sum: int
    next_roll_at: int | None


class Produced(Event):
    """``gains``: seat -> resources received; ``skipped``: resource -> reason code
    (e.g. ``"bank_shortage"``, ``"robber"``)."""
    k: Literal["produced"] = "produced"
    roll: int
    gains: dict[int, ResMap]
    skipped: dict[Resource, str] = Field(default_factory=dict)

    def public(self, viewer: int | None, vis: VisibilitySettings) -> dict[str, Any] | None:
        d = self.to_dict()
        if vis.production_log is ProductionLog.OWN:
            d["gains"] = {k: v for k, v in d["gains"].items() if viewer is not None and k == str(viewer)}
        return d


# ----------------------------------------------------------------- robber
class RobberStole(Event):
    k: Literal["robber_stole"] = "robber_stole"
    audience: ClassVar[Literal["public", "private"]] = "private"
    seat: int
    lost: ResMap

    def redacted(self, vis: VisibilitySettings) -> dict[str, Any] | None:
        return self._by_hands(vis, "lost")


class RobberMoved(Event):
    k: Literal["robber_moved"] = "robber_moved"
    from_hex: int | None
    to_hex: int


# ------------------------------------------------------------------- hand
class Hand(Event):
    """A player's full hand after a change (resulting values)."""
    k: Literal["hand"] = "hand"
    audience: ClassVar[Literal["public", "private"]] = "private"
    seat: int
    hand: ResMap

    def redacted(self, vis: VisibilitySettings) -> dict[str, Any] | None:
        return self._by_hands(vis, "hand")


# --------------------------------------------------------------- settlers
class SettlerLanded(Event):
    k: Literal["settler_landed"] = "settler_landed"
    settler: int
    seat: int
    vertex: int


class SettlerPath(Event):
    """The vertices still queued after the current step (empty = path cleared)."""
    k: Literal["settler_path"] = "settler_path"
    settler: int
    path: list[int]


class SettlerStepEvent(Event):
    k: Literal["settler_step"] = "settler_step"
    settler: int
    edge: int
    from_v: int
    to_v: int
    t0: int
    t1: int


class SettlerArrived(Event):
    k: Literal["settler_arrived"] = "settler_arrived"
    settler: int
    vertex: int


class SettlerLeft(Event):
    """The settler is removed from the map."""
    k: Literal["settler_left"] = "settler_left"
    settler: int
    seat: int


# ----------------------------------------------------------- construction
class ConstructionStarted(Event):
    k: Literal["construction_started"] = "construction_started"
    id: int
    seat: int
    kind: BuildKind
    target: int
    builder: int | None
    t0: int
    t1: int
    paid: ResMap


class ConstructionCancelled(Event):
    """``reason``: code such as ``"conflict"``, ``"builder_left"``, ``"cancelled"``."""
    k: Literal["construction_cancelled"] = "construction_cancelled"
    id: int
    seat: int
    reason: str
    refund: ResMap


class Built(Event):
    k: Literal["built"] = "built"
    seat: int
    kind: BuildKind
    target: int
    points_after: int


# ------------------------------------------------------------------ setup
class SetupComplete(Event):
    k: Literal["setup_complete"] = "setup_complete"
    seat: int


class StartingResources(Event):
    k: Literal["starting_resources"] = "starting_resources"
    audience: ClassVar[Literal["public", "private"]] = "private"
    seat: int
    gained: ResMap

    def redacted(self, vis: VisibilitySettings) -> dict[str, Any] | None:
        return self._by_hands(vis, "gained")


class StartingMaterials(Event):
    k: Literal["starting_materials"] = "starting_materials"
    audience: ClassVar[Literal["public", "private"]] = "private"
    seat: int
    materials: ResMap

    def redacted(self, vis: VisibilitySettings) -> dict[str, Any] | None:
        return self._by_hands(vis, "materials")


# ------------------------------------------------------------------ trade
class Traded(Event):
    k: Literal["traded"] = "traded"
    seat: int
    give: ResMap
    get: ResMap
    ratio: int
    via: Literal["bank", "harbor"]


# ---------------------------------------------------------------- victory
class Points(Event):
    k: Literal["points"] = "points"
    seat: int
    points: int


class Buildable(Event):
    """Legal build spots of ``seat`` (sent only to that seat, when they change)."""
    k: Literal["buildable"] = "buildable"
    audience: ClassVar[Literal["public", "private"]] = "private"
    seat: int
    roads: list[int]
    settlements: list[int]
    cities: list[int]


class GameOver(Event):
    k: Literal["game_over"] = "game_over"
    winner: int | None
    points: dict[int, int]


_EVENT_CLASSES: tuple[type[Event], ...] = (
    ClockStarted, DiceRolled, Produced, RobberStole, RobberMoved, Hand, SettlerLanded, SettlerPath,
    SettlerStepEvent, SettlerArrived, SettlerLeft, ConstructionStarted, ConstructionCancelled, Built,
    SetupComplete, StartingResources, StartingMaterials, Traded, Points, Buildable, GameOver,
)
EVENT_TYPES: dict[str, type[Event]] = {c.model_fields["k"].default: c for c in _EVENT_CLASSES}

AnyEvent = Annotated[
    ClockStarted | DiceRolled | Produced | RobberStole | RobberMoved | Hand | SettlerLanded | SettlerPath
    | SettlerStepEvent | SettlerArrived | SettlerLeft | ConstructionStarted | ConstructionCancelled | Built
    | SetupComplete | StartingResources | StartingMaterials | Traded | Points | Buildable | GameOver,
    Field(discriminator="k"),
]
_ADAPTER: TypeAdapter[Any] = TypeAdapter(AnyEvent)


def parse_event(raw: dict[str, Any]) -> Event:
    """Validate a full (unredacted) event dict back into its model."""
    return _ADAPTER.validate_python(raw)


def event_json_schema() -> dict[str, Any]:
    """JSON Schema of the full event union (serialization mode)."""
    return _ADAPTER.json_schema(mode="serialization")
