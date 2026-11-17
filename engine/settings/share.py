"""Share codes: a game's preset and setting changes as one short string.

Format: ``<preset>.<schema_version>.<payload>``, where ``payload`` is
``base64url(zlib(canonical_json(overrides)))`` without padding, and is empty when
nothing differs from the preset (``classic.1.``). ``overrides`` are the lobby's
differences from the preset, so the code stays short.

Decoding checks the size of the code and of the unpacked JSON, brings older
schema versions up to date (``migrations``) and returns the preset and overrides.
It does not validate the settings: pass them to ``load_preset`` for that.

Errors are :class:`ShareCodeError` with a code:
``settings.share.malformed``, ``settings.share.too_long``,
``settings.share.too_new`` (made by a newer server) and ``settings.preset.unknown``.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import zlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .migrations import MigrationError, migrate
from .models import CURRENT_SCHEMA_VERSION
from .presets import available_presets

__all__ = ["ShareCodeError", "SharedSettings", "encode_share_code", "decode_share_code",
           "MAX_CODE_LENGTH", "MAX_JSON_BYTES"]

MAX_CODE_LENGTH = 4096
"""Longest code accepted (characters)."""
MAX_JSON_BYTES = 65536
"""Largest unpacked overrides JSON accepted (bytes); guards against zip bombs."""

_SEP = "."
_CODE = re.compile(r"^([a-z0-9_]{1,32})\.([0-9]{1,4})\.([A-Za-z0-9_-]*)$")


class ShareCodeError(ValueError):
    def __init__(self, code: str, **params: Any) -> None:
        super().__init__(code, params)
        self.code = code
        self.params = params


@dataclass(frozen=True)
class SharedSettings:
    preset: str
    overrides: dict[str, Any] = field(default_factory=dict)


def _canonical(data: Mapping[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def encode_share_code(preset: str, overrides: Mapping[str, Any] | None = None) -> str:
    """The share code of ``preset`` with ``overrides`` (differences from the preset)."""
    data = dict(overrides or {})
    data.pop("schema_version", None)
    data.pop("preset", None)
    payload = ""
    if data:
        packed = zlib.compress(_canonical(data), 9)
        payload = base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")
    return _SEP.join((preset, str(CURRENT_SCHEMA_VERSION), payload))


def _unpack(payload: str) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        packed = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        inflater = zlib.decompressobj()
        raw = inflater.decompress(packed, MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES or inflater.unconsumed_tail:
            raise ShareCodeError("settings.share.too_long")
        if not inflater.eof or inflater.unused_data:
            raise ShareCodeError("settings.share.malformed")
        data = json.loads(raw.decode("utf-8"))
    except (binascii.Error, ValueError, zlib.error, UnicodeDecodeError) as exc:
        if isinstance(exc, ShareCodeError):
            raise
        raise ShareCodeError("settings.share.malformed") from exc
    if not isinstance(data, dict):
        raise ShareCodeError("settings.share.malformed")
    return data


def decode_share_code(code: str) -> SharedSettings:
    """The preset and overrides a share code holds, migrated to the current schema."""
    text = "".join(code.split())
    if len(text) > MAX_CODE_LENGTH:
        raise ShareCodeError("settings.share.too_long")
    match = _CODE.match(text)
    if match is None:
        raise ShareCodeError("settings.share.malformed")
    preset, version, payload = match.group(1), int(match.group(2)), match.group(3)
    if preset not in available_presets():
        raise ShareCodeError("settings.preset.unknown", preset=preset)
    if version > CURRENT_SCHEMA_VERSION:
        raise ShareCodeError("settings.share.too_new", version=version)
    overrides = _unpack(payload)
    overrides.pop("preset", None)
    if version < CURRENT_SCHEMA_VERSION:
        try:
            overrides = migrate({**overrides, "schema_version": version})
        except MigrationError as exc:
            raise ShareCodeError("settings.share.malformed") from exc
    overrides.pop("schema_version", None)
    return SharedSettings(preset=preset, overrides=overrides)
