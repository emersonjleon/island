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

from engine.settings.enums import BuildKind, DevCardKind, InfoVisibility, ProductionLog, Resource
from engine.settings.models import VisibilitySettings

__all__ = [
    "Event", "AnyEvent", "EVENT_TYPES", "parse_event", "event_json_schema",
    "ClockStarted", "DiceRolled", "Produced", "RobberStole", "RobberMoved", "Hand", "SettlerLanded",
    "SettlerPath", "SettlerStepEvent", "SettlerArrived", "SettlerLeft", "ConstructionStarted",
    "ConstructionCancelled", "Built", "SetupComplete", "StartingResources", "StartingMaterials", "Traded",
    "Points", "LongestRoad", "DevCardBought", "DevCardPlayed", "LargestArmy", "OfferPosted", "OfferClosed", "Buildable", "Resigned", "GameOver", "Revealed", "NumbersRevealed", "SettlersGathered",
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
    """Under fog a player gets ``None`` for a hex they have not seen (and nothing
    when neither hex is seen)."""
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


class LongestRoad(Event):
    """Road lengths or the Longest Road holder changed (``seat`` None: nobody holds it)."""
    k: Literal["longest_road"] = "longest_road"
    seat: int | None
    previous: int | None
    lengths: dict[int, int]


# -------------------------------------------------------------- dev cards
class DevCardBought(Event):
    """``seat`` bought ``card``. Others see it per ``visibility.dev_cards``: ``open``
    the card, ``counts`` the purchase without the card, ``hidden`` nothing."""
    k: Literal["dev_card_bought"] = "dev_card_bought"
    audience: ClassVar[Literal["public", "private"]] = "private"
    seat: int
    card: DevCardKind
    deck_left: int

    def redacted(self, vis: VisibilitySettings) -> dict[str, Any] | None:
        if vis.dev_cards is InfoVisibility.OPEN:
            return self.to_dict()
        if vis.dev_cards is InfoVisibility.COUNTS:
            d = self.to_dict()
            del d["card"]
            return d
        return None


class DevCardPlayed(Event):
    """``seat`` played ``card``. Knight: ``hex`` and ``victim`` (None: nobody to rob),
    ``stolen`` cards taken (the kinds go only to the two players, in ``Hand``).
    Year of plenty: ``took`` (from the bank, public). Monopoly: ``resource`` and ``taken`` (seat -> count). Road building:
    ``roads`` free roads."""
    k: Literal["dev_card_played"] = "dev_card_played"
    seat: int
    card: DevCardKind
    hex: int | None = None
    victim: int | None = None
    stolen: int = 0
    took: ResMap = Field(default_factory=dict)
    resource: Resource | None = None
    taken: dict[int, int] = Field(default_factory=dict)
    roads: int = 0


class LargestArmy(Event):
    """Knights played or the Largest Army holder changed (``seat`` None: nobody)."""
    k: Literal["largest_army"] = "largest_army"
    seat: int | None
    previous: int | None
    knights: dict[int, int]


# ---------------------------------------------------------------- trade board
class OfferPosted(Event):
    """``seat`` put offer ``offer`` on the trade board: they give ``give`` for ``get``.
    ``expires_at``: game ms when it is taken down, or None (stays until taken)."""
    k: Literal["offer_posted"] = "offer_posted"
    offer: int
    seat: int
    give: ResMap
    get: ResMap
    expires_at: int | None = None


class OfferClosed(Event):
    """Offer ``offer`` of ``seat`` left the board. ``reason``: ``"accepted"`` (``by``
    took it; the cards moved, see ``Hand``), ``"cancelled"``, ``"expired"`` or
    ``"resigned"`` (its poster left the game)."""
    k: Literal["offer_closed"] = "offer_closed"
    offer: int
    seat: int
    reason: Literal["accepted", "cancelled", "expired", "resigned"]
    by: int | None = None
    give: ResMap = Field(default_factory=dict)
    get: ResMap = Field(default_factory=dict)


class Buildable(Event):
    """Legal build spots of ``seat`` (sent only to that seat, when they change)."""
    k: Literal["buildable"] = "buildable"
    audience: ClassVar[Literal["public", "private"]] = "private"
    seat: int
    roads: list[int]
    settlements: list[int]
    cities: list[int]
    megacities: list[int] = Field(default_factory=list)


class Resigned(Event):
    """``seat`` gave up. Their pieces stay on the board but no longer produce; ``returned``
    is what went back to the bank (their hand and unfinished builds)."""
    k: Literal["resigned"] = "resigned"
    seat: int
    returned: ResMap


class GameOver(Event):
    """``reason``: ``"target"`` (someone reached the victory target) or ``"resign"``
    (too few players left after a resignation)."""
    k: Literal["game_over"] = "game_over"
    winner: int | None
    points: dict[int, int]
    reason: Literal["target", "resign"] = "target"


class SettlersGathered(Event):
    """Settlers at rest gathered from the hexes around them on ``roll`` (Settlers
    variation). ``gains``: seat -> resources; like :class:`Produced`, others' gains are
    left out with ``visibility.production_log = own``."""
    k: Literal["settlers_gathered"] = "settlers_gathered"
    roll: int
    gains: dict[int, ResMap]
    settlers: list[int] = Field(default_factory=list)          # ids of the settlers that gathered

    def public(self, viewer: int | None, vis: VisibilitySettings) -> dict[str, Any] | None:
        d = self.to_dict()
        if vis.production_log is ProductionLog.OWN:
            d["gains"] = {k: v for k, v in d["gains"].items() if viewer is not None and k == str(viewer)}
        return d


class Revealed(Event):
    """``seat`` saw new land (Growing sight). ``board`` holds the newly seen hexes
    and the vertices, edges, fishing grounds and harbors on them, shaped like the
    ``board`` message (vertices and edges already known come again with their seen
    hexes). ``pieces`` holds what stands there now (``buildings``, ``roads``,
    ``settlers``, ``constructions``, ``robber``), shaped like the ``state`` message;
    a client replaces what it had at those places."""
    k: Literal["revealed"] = "revealed"
    audience: ClassVar[Literal["public", "private"]] = "private"
    seat: int
    board: dict[str, Any]
    pieces: dict[str, Any]


class NumbersRevealed(Event):
    """Number tokens shown because a building now stands next to their hex
    (``visibility.hidden_numbers``). ``tokens``: hex id -> token. Players get only
    the hexes they have seen."""
    k: Literal["numbers_revealed"] = "numbers_revealed"
    tokens: dict[int, int]


_EVENT_CLASSES: tuple[type[Event], ...] = (
    ClockStarted, DiceRolled, Produced, RobberStole, RobberMoved, Hand, SettlerLanded, SettlerPath,
    SettlerStepEvent, SettlerArrived, SettlerLeft, ConstructionStarted, ConstructionCancelled, Built,
    SetupComplete, StartingResources, StartingMaterials, Traded, Points, LongestRoad, DevCardBought, DevCardPlayed, LargestArmy, OfferPosted, OfferClosed, Buildable, Resigned, GameOver,
    Revealed, NumbersRevealed, SettlersGathered,
)
EVENT_TYPES: dict[str, type[Event]] = {c.model_fields["k"].default: c for c in _EVENT_CLASSES}

AnyEvent = Annotated[
    ClockStarted | DiceRolled | Produced | RobberStole | RobberMoved | Hand | SettlerLanded | SettlerPath
    | SettlerStepEvent | SettlerArrived | SettlerLeft | ConstructionStarted | ConstructionCancelled | Built
    | SetupComplete | StartingResources | StartingMaterials | Traded | Points | LongestRoad | DevCardBought | DevCardPlayed | LargestArmy
    | OfferPosted | OfferClosed | Buildable | Resigned | GameOver | Revealed | NumbersRevealed
    | SettlersGathered,
    Field(discriminator="k"),
]
_ADAPTER: TypeAdapter[Any] = TypeAdapter(AnyEvent)


def parse_event(raw: dict[str, Any]) -> Event:
    """Validate a full (unredacted) event dict back into its model."""
    return _ADAPTER.validate_python(raw)


def event_json_schema() -> dict[str, Any]:
    """JSON Schema of the full event union (serialization mode)."""
    return _ADAPTER.json_schema(mode="serialization")
