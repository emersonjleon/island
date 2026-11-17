import base64
import json
import unittest
import zlib

from engine.rng import Rng
from engine.settings import (
    CURRENT_SCHEMA_VERSION, ShareCodeError, available_presets, decode_share_code, encode_share_code, load_preset,
)
from engine.settings.share import MAX_CODE_LENGTH, MAX_JSON_BYTES


def _payload(data: bytes) -> str:
    return base64.urlsafe_b64encode(zlib.compress(data, 9)).decode("ascii").rstrip("=")


class ShareCodeTest(unittest.TestCase):
    def assert_code_error(self, code: str, expected: str) -> None:
        with self.assertRaises(ShareCodeError) as ctx:
            decode_share_code(code)
        self.assertEqual(ctx.exception.code, expected)

    def test_no_changes(self) -> None:
        code = encode_share_code("classic", {})
        self.assertEqual(code, f"classic.{CURRENT_SCHEMA_VERSION}.")
        shared = decode_share_code(code)
        self.assertEqual((shared.preset, shared.overrides), ("classic", {}))

    def test_round_trip(self) -> None:
        overrides = {"players": {"max": 6}, "board": {"land_hexes": 40, "red_may_touch": True},
                     "economy": {"bank": {"per_resource": {"brick": 30, "lumber": 30, "wool": 30, "grain": 30,
                                                           "ore": 30, "fish": 30}}},
                     "victory": {"target": 12}}
        for preset in available_presets():
            with self.subTest(preset=preset):
                code = encode_share_code(preset, overrides)
                shared = decode_share_code(code)
                self.assertEqual(shared.preset, preset)
                self.assertEqual(shared.overrides, overrides)
                self.assertEqual(load_preset(shared.preset, shared.overrides),
                                 load_preset(preset, overrides))

    def test_canonical(self) -> None:
        a = encode_share_code("blitz", {"victory": {"target": 6}, "players": {"max": 3}})
        b = encode_share_code("blitz", {"players": {"max": 3}, "victory": {"target": 6}})
        self.assertEqual(a, b)
        self.assertRegex(a, r"^blitz\.\d+\.[A-Za-z0-9_-]+$")

    def test_preset_and_version_keys_dropped(self) -> None:
        code = encode_share_code("classic", {"preset": "huge", "schema_version": 1, "victory": {"target": 11}})
        self.assertEqual(decode_share_code(code).overrides, {"victory": {"target": 11}})

    def test_whitespace_ignored(self) -> None:
        code = encode_share_code("classic", {"victory": {"target": 11}})
        spaced = f"  {code[:8]}\n {code[8:]} "
        self.assertEqual(decode_share_code(spaced).overrides, {"victory": {"target": 11}})

    def test_seeded_random_codes_round_trip(self) -> None:
        rng = Rng(7)
        for _ in range(50):
            overrides = {"players": {"max": rng.randint(2, 12)},
                         "victory": {"target": rng.randint(5, 20)},
                         "clock": {"roll_interval_ms": rng.randint(5, 120) * 1000}}
            code = encode_share_code("custom", overrides)
            self.assertEqual(decode_share_code(code).overrides, overrides)

    def test_malformed(self) -> None:
        good = encode_share_code("classic", {"victory": {"target": 11}})
        for code in ("", "classic", "classic.1", "Classic.1.", "classic.x.", "classic.1.!!", good + "AA",
                     good[:-3], f"classic.1.{_payload(b'[1, 2]')}", f"classic.1.{_payload(b'not json')}",
                     f"classic.1.{_payload(b'\xff\xfe')}", "classic.1.AAAA"):
            with self.subTest(code=code):
                self.assert_code_error(code, "settings.share.malformed")

    def test_unknown_preset(self) -> None:
        self.assert_code_error("nope.1.", "settings.preset.unknown")

    def test_newer_version(self) -> None:
        self.assert_code_error(f"classic.{CURRENT_SCHEMA_VERSION + 1}.", "settings.share.too_new")

    def test_older_version_without_migration(self) -> None:
        self.assert_code_error("classic.0.", "settings.share.malformed")

    def test_too_long(self) -> None:
        self.assert_code_error("classic.1." + "A" * MAX_CODE_LENGTH, "settings.share.too_long")

    def test_zip_bomb_refused(self) -> None:
        bomb = json.dumps({"x": " " * (MAX_JSON_BYTES * 4)}).encode("ascii")
        code = f"classic.1.{_payload(bomb)}"
        self.assertLess(len(code), MAX_CODE_LENGTH)
        self.assert_code_error(code, "settings.share.too_long")


if __name__ == "__main__":
    unittest.main()
