"""Player intentions (client -> server), as Pydantic v2 models.

The wire envelope is ``{"t": "intent", "cid": "...", "a": "<action>", ...fields}``;
:func:`parse_command` drops ``t`` and ``cid`` and validates the rest. Models are
frozen and forbid unknown fields. Ids are strict non-negative ints (no strings,
no bools). Gameplay legality is checked only by the rule handlers.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

from engine.errors import RuleError
from engine.settings.enums import BuildKind, DevCardKind, Resource

__all__ = [
    "MoveSettler", "Build", "CancelBuild", "BankTrade", "BuyDevCard", "PlayDevCard", "Command", "COMMAND_TYPES",
    "parse_command", "command_json_schema", "ENVELOPE_KEYS",
]

Id = Annotated[int, Field(strict=True, ge=0)]
Amount = Annotated[int, Field(strict=True, ge=1, le=1000)]
ENVELOPE_KEYS = ("t", "cid")


class _Cmd(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MoveSettler(_Cmd):
    """Walk ``settler`` to ``to_vertex``. ``replace`` re-paths (after the current
    edge); ``append`` queues the path after the already-queued one."""
    a: Literal["move_settler"] = "move_settler"
    settler: Id
    to_vertex: Id
    mode: Literal["replace", "append"] = "replace"


class Build(_Cmd):
    """Start building. Settlement/city need ``vertex``; road needs ``edge``.
    ``settler`` names the builder when one is required (setup / Settlers variation)."""
    a: Literal["build"] = "build"
    kind: BuildKind
    vertex: Id | None = None
    edge: Id | None = None
    settler: Id | None = None

    @model_validator(mode="after")
    def _target(self) -> Self:
        if self.kind is BuildKind.ROAD:
            if self.edge is None or self.vertex is not None:
                raise ValueError("road needs edge and no vertex")
        elif self.vertex is None or self.edge is not None:
            raise ValueError(f"{self.kind.value} needs vertex and no edge")
        return self

    @property
    def target(self) -> int:
        """The vertex (settlement/city) or edge (road) id."""
        return self.edge if self.kind is BuildKind.ROAD else self.vertex  # type: ignore[return-value]


class CancelBuild(_Cmd):
    a: Literal["cancel_build"] = "cancel_build"
    construction: Id


class BankTrade(_Cmd):
    """Trade with the bank (or a harbor the player owns; the rule picks the best ratio).

    Stage 1: exactly one ``give`` resource and one different ``get`` resource,
    positive amounts. Whether ``give`` amount == ratio * ``get`` amount is a rule check
    (``trade.*`` codes), not a schema check.
    """
    a: Literal["bank_trade"] = "bank_trade"
    give: dict[Resource, Amount]
    get: dict[Resource, Amount]

    @model_validator(mode="after")
    def _one_each(self) -> Self:
        if len(self.give) != 1 or len(self.get) != 1:
            raise ValueError("give and get must each name exactly one resource")
        if set(self.give) == set(self.get):
            raise ValueError("give and get must differ")
        return self


class BuyDevCard(_Cmd):
    """Buy the top card of the development deck (stage 2)."""
    a: Literal["buy_dev_card"] = "buy_dev_card"


class PlayDevCard(_Cmd):
    """Play a development card (stage 2). Fields by card:

    * ``knight``: ``hex`` (where the robber goes) and, when several players could be
      robbed there, ``victim``;
    * ``year_of_plenty``: ``resources`` (one entry per card taken, repeats allowed);
    * ``monopoly``: ``resource``;
    * ``victory_point`` / ``road_building``: nothing else.

    Whether the right fields are given for the card is a rule check (``dev.*`` codes).
    """
    a: Literal["play_dev_card"] = "play_dev_card"
    card: DevCardKind
    hex: Id | None = None
    victim: Id | None = None
    resources: list[Resource] | None = Field(default=None, max_length=20)
    resource: Resource | None = None


Command = Annotated[MoveSettler | Build | CancelBuild | BankTrade | BuyDevCard | PlayDevCard,
                    Field(discriminator="a")]
COMMAND_TYPES: dict[str, type[_Cmd]] = {
    "move_settler": MoveSettler, "build": Build, "cancel_build": CancelBuild, "bank_trade": BankTrade,
    "buy_dev_card": BuyDevCard, "play_dev_card": PlayDevCard,
}
_ADAPTER: TypeAdapter[Any] = TypeAdapter(Command)


def parse_command(raw: Any) -> MoveSettler | Build | CancelBuild | BankTrade | BuyDevCard | PlayDevCard:
    """Validate a raw intent dict. Raises ``RuleError("command.invalid", {...})``.

    params: ``{"action": <a or None>, "errors": [{"loc": "dotted.path", "type": "..."}]}``.
    """
    if isinstance(raw, _Cmd):
        return raw  # type: ignore[return-value]
    if not isinstance(raw, dict):
        raise RuleError("command.invalid", {"action": None, "errors": [{"loc": "", "type": "dict_type"}]})
    body = {k: v for k, v in raw.items() if k not in ENVELOPE_KEYS}
    action = body.get("a") if isinstance(body.get("a"), str) else None
    try:
        return _ADAPTER.validate_python(body)
    except ValidationError as exc:
        errors = []
        for e in exc.errors():
            loc = list(e["loc"])
            if loc and loc[0] == action:      # drop the union tag prefix
                loc = loc[1:]
            errors.append({"loc": ".".join(str(p) for p in loc), "type": e["type"]})
        raise RuleError("command.invalid", {"action": action, "errors": errors}) from None


def command_json_schema() -> dict[str, Any]:
    """JSON Schema of the ``Command`` union (for ``protocol/schema`` / TS generation)."""
    return _ADAPTER.json_schema()
