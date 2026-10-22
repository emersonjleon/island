import json
import unittest
from typing import Any

from pydantic import BaseModel, ValidationError

from engine.settings import (
    IMPLEMENTED_STAGE, LATER_STAGE_VALUES, BoardLayout, GameSettings, MigrationError, Resource, SeatOrder,
    SetupMode, Terrain, UnknownPresetError, available_presets, export_json_schema, load_preset,
    merge_overrides, migrate, parse_settings, preset_overrides, resolve_board_counts, scale_counts,
    stage_violations, value_stage,
)
from engine.settings.resolve import STANDARD_NUMBER_TOKENS, STANDARD_TERRAIN_COUNTS


def error_types(exc: ValidationError) -> list[str]:
    return [e["type"] for e in exc.errors()]


def board(**kwargs: Any) -> GameSettings:
    return GameSettings.model_validate({"board": kwargs})


class DefaultsTest(unittest.TestCase):
    def test_defaults_load(self) -> None:
        s = GameSettings()
        self.assertEqual(s.schema_version, 1)
        self.assertEqual(s.preset, "classic")
        self.assertEqual((s.players.min, s.players.max), (2, 4))
        self.assertEqual(s.board.land_hexes, 19)
        self.assertEqual(s.clock.roll_interval_ms, 20000)
        self.assertEqual(s.clock.robber_roll, 7)
        self.assertEqual(s.economy.costs.city, {Resource.GRAIN: 2, Resource.ORE: 3})
        self.assertEqual(s.economy.costs.settler[Resource.FISH], 2)
        self.assertEqual(s.economy.bank.per_resource, {r: 19 for r in Resource})
        self.assertEqual(s.economy.starting_materials[Resource.BRICK], 4)
        self.assertEqual((s.pieces.roads, s.pieces.settlements, s.pieces.cities), (15, 5, 4))
        self.assertEqual(s.build.time_ms.settlement, 8000)
        self.assertEqual(s.robber.steal_pct, 50)
        self.assertEqual(s.settlers.road_speed_pct, 200)
        self.assertEqual(s.victory.target, 10)
        self.assertEqual(s.victory.largest_army.min, 3)
        self.assertEqual(s.victory.longest_road.min, 5)
        self.assertEqual(sum(s.dev_cards.deck.values()), 25)
        self.assertEqual(stage_violations(s), [])

    def test_frozen_and_extra_forbid(self) -> None:
        s = GameSettings()
        with self.assertRaises(ValidationError):
            s.victory.target = 8  # type: ignore[misc]
        with self.assertRaises(ValidationError):
            GameSettings.model_validate({"victory": {"targett": 8}})
        with self.assertRaises(ValidationError):
            GameSettings.model_validate({"bogus": 1})

    def test_bounds(self) -> None:
        for raw in ({"clock": {"roll_interval_ms": 4999}}, {"board": {"land_hexes": 6}},
                    {"board": {"land_hexes": 251}}, {"victory": {"target": 21}},
                    {"robber": {"steal_pct": 101}}, {"economy": {"costs": {"road": {"brick": -1}}}},
                    {"economy": {"costs": {"road": {"gold": 1}}}}):
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                GameSettings.model_validate(raw)

    def test_json_round_trip(self) -> None:
        s = load_preset("blitz", {"board": {"land_hexes": 37, "seed": 5}, "robber": {"steal_pct": 25}})
        dumped = json.loads(json.dumps(s.model_dump(mode="json")))
        self.assertEqual(GameSettings.model_validate(dumped), s)
        self.assertEqual(GameSettings.model_validate_json(s.model_dump_json()), s)
        self.assertEqual(GameSettings.model_validate(s.model_dump()), s)

    def test_bank_accepts_single_int(self) -> None:
        s = GameSettings.model_validate({"economy": {"bank": {"per_resource": 30}}})
        self.assertEqual(s.economy.bank.per_resource, {r: 30 for r in Resource})
        with self.assertRaises(ValidationError):
            GameSettings.model_validate({"economy": {"bank": {"per_resource": {"ore": 30}}}})

    def test_every_field_has_label_and_stage(self) -> None:
        def walk(cls: type[BaseModel], prefix: str) -> None:
            for name, field in cls.model_fields.items():
                path = f"{prefix}.{name}"
                extra = field.json_schema_extra
                self.assertIsInstance(extra, dict, path)
                assert isinstance(extra, dict)
                self.assertEqual(extra["label"], path)
                self.assertIn(extra["stage"], (1, 2, 3))
                self.assertFalse(field.is_required(), path)
                ann = field.annotation
                if isinstance(ann, type) and issubclass(ann, BaseModel):
                    walk(ann, path)

        walk(GameSettings, "settings")


class ResolveTest(unittest.TestCase):
    def test_standard_board_exact(self) -> None:
        r = resolve_board_counts(GameSettings())
        self.assertEqual(r.terrain_counts, STANDARD_TERRAIN_COUNTS)
        expected_tokens = tuple(sorted(n for n, c in STANDARD_NUMBER_TOKENS.items() for _ in range(c)))
        self.assertEqual(r.number_tokens, expected_tokens)
        self.assertEqual(len(r.number_tokens), 18)
        self.assertEqual(r.fishing_count, 6)
        self.assertEqual(r.fishing_tokens, (4, 5, 6, 8, 9, 10))
        self.assertEqual(r.harbors_generic, 4)
        self.assertEqual(r.harbors_specific, {Resource.LUMBER: 1, Resource.BRICK: 1, Resource.WOOL: 1,
                                              Resource.GRAIN: 1, Resource.ORE: 1, Resource.FISH: 0})
        self.assertEqual(r.harbors_total, 9)

    def test_scaling_sums_and_determinism(self) -> None:
        for land in (7, 9, 10, 37, 61, 250):
            with self.subTest(land=land):
                s = board(land_hexes=land)
                r = resolve_board_counts(s)
                self.assertEqual(sum(r.terrain_counts.values()), land)
                self.assertEqual(len(r.number_tokens), r.producing_land_hexes)
                self.assertEqual(len(r.fishing_tokens), r.fishing_count)
                self.assertTrue(all(c >= 1 for t, c in r.terrain_counts.items() if t is not Terrain.DESERT))
                self.assertNotIn(7, r.number_tokens)
                self.assertEqual(resolve_board_counts(board(land_hexes=land)), r)

    def test_scaling_known_values(self) -> None:
        r7 = resolve_board_counts(board(land_hexes=7))
        self.assertEqual(r7.terrain_counts[Terrain.DESERT], 0)
        self.assertEqual(r7.number_tokens, (3, 4, 5, 6, 8, 9, 10))
        self.assertEqual((r7.fishing_count, r7.harbors_generic), (2, 1))
        self.assertEqual(resolve_board_counts(board(land_hexes=10)).terrain_counts[Terrain.DESERT], 1)
        r37 = resolve_board_counts(board(land_hexes=37))
        self.assertEqual([r37.terrain_counts[t] for t in Terrain], [8, 8, 7, 6, 6, 2])
        self.assertEqual((r37.fishing_count, r37.harbors_generic), (12, 8))
        r250 = resolve_board_counts(board(land_hexes=250))
        self.assertEqual(r250.terrain_counts[Terrain.DESERT], 13)
        self.assertEqual((r250.fishing_count, r250.harbors_generic), (79, 53))

    def test_explicit_counts_win(self) -> None:
        s = board(land_hexes=7, terrain_counts={"forest": 2, "hills": 2, "fields": 2, "desert": 1},
                  number_tokens={"5": 2, "6": 2, "8": 1, "9": 1}, fishing_grounds={"count": 3, "tokens": [5]},
                  harbors={"generic": 0})
        r = resolve_board_counts(s)
        self.assertEqual(r.terrain_counts[Terrain.PASTURE], 0)
        self.assertEqual(r.number_tokens, (5, 5, 6, 6, 8, 9))
        self.assertEqual(r.fishing_tokens, (5, 5, 5))
        self.assertEqual(r.harbors_generic, 0)

    def test_fishing_tokens_cycle(self) -> None:
        r = resolve_board_counts(board(fishing_grounds={"count": 8}))
        self.assertEqual(r.fishing_tokens, (4, 5, 6, 8, 9, 10, 4, 5))

    def test_scale_counts(self) -> None:
        self.assertEqual(scale_counts([("a", 1), ("b", 1), ("c", 1)], 2), {"a": 1, "b": 1, "c": 0})
        self.assertEqual(scale_counts([("a", 3), ("b", 1)], 0), {"a": 0, "b": 0})
        with self.assertRaises(ValueError):
            scale_counts([("a", 0)], 3)


class CrossFieldTest(unittest.TestCase):
    def assert_error(self, raw: dict[str, Any], code: str) -> None:
        with self.assertRaises(ValidationError) as ctx:
            GameSettings.model_validate(raw)
        self.assertIn(code, error_types(ctx.exception))

    def test_players_min_le_max(self) -> None:
        self.assert_error({"players": {"min": 4, "max": 3}}, "settings.players.min_gt_max")

    def test_terrain_sum(self) -> None:
        self.assert_error({"board": {"terrain_counts": {"forest": 18}}}, "settings.board.terrain_sum")
        self.assert_error({"board": {"land_hexes": 7, "terrain_counts": {"desert": 7}}},
                          "settings.board.no_producing_hexes")

    def test_token_count(self) -> None:
        self.assert_error({"board": {"number_tokens": {"6": 2}}}, "settings.board.token_count")
        # Explicit terrain with 2 deserts -> 17 producing hexes.
        terrain = {"forest": 4, "pasture": 4, "fields": 4, "hills": 3, "mountains": 2, "desert": 2}
        tokens = dict(STANDARD_NUMBER_TOKENS)
        tokens[12] = 0
        s = GameSettings.model_validate({"board": {"terrain_counts": terrain, "number_tokens": tokens}})
        self.assertEqual(len(resolve_board_counts(s).number_tokens), 17)

    def test_red_numbers(self) -> None:
        self.assert_error({"board": {"red_numbers": [6, 6]}}, "settings.board.red_duplicates")
        self.assert_error({"board": {"red_numbers": [6, 7]}}, "settings.board.red_not_token")
        tokens = {5: 9, 9: 9}
        self.assert_error({"board": {"number_tokens": tokens}}, "settings.board.red_not_token")
        GameSettings.model_validate({"board": {"number_tokens": tokens, "red_numbers": [5, 9]}})

    def test_tokens_in_dice_range(self) -> None:
        self.assert_error({"board": {"fishing_grounds": {"tokens": [7]}}}, "settings.board.token_out_of_range")
        self.assert_error({"board": {"fishing_grounds": {"tokens": [13]}}}, "settings.board.token_out_of_range")
        self.assert_error({"board": {"fishing_grounds": {"tokens": []}}}, "settings.board.fishing_tokens_empty")
        GameSettings.model_validate({"board": {"fishing_grounds": {"tokens": [], "count": 0}}})

    def test_setup_vs_pieces(self) -> None:
        self.assert_error({"setup": {"settlements": 3}, "pieces": {"settlements": 2}}, "settings.setup.exceeds_pieces")

    def test_bank_covers_starting_materials(self) -> None:
        self.assert_error({"economy": {"bank": {"per_resource": 15}}}, "settings.economy.bank_too_small")
        GameSettings.model_validate({"economy": {"bank": {"per_resource": 15}, "starting_materials_from_bank": False}})

    def test_dev_card_cooldown_ms(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            parse_settings({"dev_cards": {"cooldown": "ms"}}, implemented_stage=2)
        self.assertIn("settings.dev_cards.cooldown_ms_missing", error_types(ctx.exception))


class StageTest(unittest.TestCase):
    def test_implemented_stage(self) -> None:
        self.assertEqual(IMPLEMENTED_STAGE, 1)

    def test_later_stage_field_rejected(self) -> None:
        for raw, field in (({"dev_cards": {"road_building_roads": 3}}, "dev_cards.road_building_roads"),
                           ({"victory": {"time_limit_ms": 600000}}, "victory.time_limit_ms"),
                           ({"settlers": {"leave_after_setup": False}}, "settlers.leave_after_setup"),
                           ({"victory": {"largest_army": {"min": 4}}}, "victory.largest_army.min"),
                           ({"visibility": {"sight": {"city": 3}}}, "visibility.sight.city")):
            with self.subTest(field=field), self.assertRaises(ValidationError) as ctx:
                GameSettings.model_validate(raw)
            err = ctx.exception.errors()[0]
            self.assertEqual(err["type"], "settings.later_stage")
            self.assertIn(field, err["msg"])
            self.assertEqual(err["ctx"]["violations"][0]["field"], field)

    def test_later_stage_enum_value_rejected(self) -> None:
        for raw in ({"board": {"layout": "beginner"}}, {"board": {"shape": "hexagon"}},
                    {"clock": {"dice_mode": "deck"}}, {"setup": {"mode": "snake_click"}},
                    {"visibility": {"map": "growing"}}, {"settlers": {"builder_required": "always"}},
                    {"robber": {"move_on_seven": "player"}}):
            with self.subTest(raw=raw), self.assertRaises(ValidationError) as ctx:
                GameSettings.model_validate(raw)
            self.assertEqual(error_types(ctx.exception), ["settings.later_stage"])

    def test_later_stage_numeric_limit(self) -> None:
        with self.assertRaises(ValidationError):
            GameSettings.model_validate({"players": {"max": 5}, "economy": {"bank": {"per_resource": 30}}})

    def test_stage_one_values_allowed(self) -> None:
        s = GameSettings.model_validate({
            "board": {"layout": "seeded", "seed": 3, "robber_start": "random_land"},
            "players": {"seat_order": "host"}, "visibility": {"hands": "open", "production_log": "own"},
            "robber": {"require_adjacent": True, "enabled": False}, "trading": {"harbor_trade": False}})
        self.assertEqual(s.board.layout, BoardLayout.SEEDED)
        self.assertEqual(s.players.seat_order, SeatOrder.HOST)

    def test_defaults_of_later_fields_allowed_explicitly(self) -> None:
        GameSettings.model_validate({"dev_cards": {"road_building_roads": 2}, "trading": {"player_trades": True}})

    def test_context_raises_implemented_stage(self) -> None:
        s = parse_settings({"board": {"layout": "beginner"}, "players": {"max": 6},
                            "economy": {"bank": {"per_resource": 30}}}, implemented_stage=3)
        self.assertEqual(s.players.max, 6)
        with self.assertRaises(ValidationError):
            parse_settings({"board": {"shape": "custom"}}, implemented_stage=3)

    def test_enum_stage_keyed_by_type(self) -> None:
        # SeatOrder.RANDOM == SetupMode.RANDOM as strings; their stages differ.
        self.assertEqual(value_stage(SeatOrder.RANDOM), 1)
        self.assertEqual(value_stage(SetupMode.RANDOM), 3)
        self.assertEqual(value_stage(BoardLayout.BEGINNER), 3)
        self.assertIn(SetupMode, LATER_STAGE_VALUES)


class PresetTest(unittest.TestCase):
    def test_available(self) -> None:
        self.assertEqual(available_presets(), ["blitz", "classic"])

    def test_classic_equals_defaults(self) -> None:
        self.assertEqual(preset_overrides("classic"), {})
        self.assertEqual(load_preset("classic"), GameSettings())

    def test_blitz(self) -> None:
        s = load_preset("blitz")
        self.assertEqual((s.clock.roll_interval_ms, s.victory.target, s.preset), (8000, 7, "blitz"))
        self.assertEqual(s.board.land_hexes, 19)

    def test_override_merge(self) -> None:
        s = load_preset("blitz", {"clock": {"pause_after_seven_ms": 0}, "victory": {"target": 12},
                                  "economy": {"costs": {"road": {"lumber": 2}}}})
        self.assertEqual(s.clock.roll_interval_ms, 8000)  # sibling kept
        self.assertEqual(s.victory.target, 12)
        self.assertEqual(s.economy.costs.road, {Resource.LUMBER: 2})  # mapping values replace
        self.assertEqual(s.economy.costs.city, {Resource.GRAIN: 2, Resource.ORE: 3})

    def test_merge_overrides_is_pure(self) -> None:
        base = {"clock": {"roll_interval_ms": 8000}}
        merged = merge_overrides(base, {"clock": {"dice_mode": "two_dice"}})
        self.assertEqual(merged, {"clock": {"roll_interval_ms": 8000, "dice_mode": "two_dice"}})
        self.assertEqual(base, {"clock": {"roll_interval_ms": 8000}})

    def test_unknown_preset(self) -> None:
        for name in ("nope", "../classic", "settlers"):
            with self.subTest(name=name), self.assertRaises(UnknownPresetError):
                load_preset(name)

    def test_presets_hold_only_differences(self) -> None:
        defaults = GameSettings().model_dump(mode="json")

        def check(diff: dict[str, Any], base: dict[str, Any], path: str) -> None:
            for key, value in diff.items():
                if isinstance(value, dict) and isinstance(base.get(key), dict):
                    check(value, base[key], f"{path}.{key}")
                else:
                    self.assertNotEqual(value, base.get(key), f"{path}.{key} repeats the default")

        for name in available_presets():
            check(preset_overrides(name), defaults, name)
            self.assertEqual(stage_violations(load_preset(name)), [])


class MigrationTest(unittest.TestCase):
    def test_current_version_passthrough(self) -> None:
        raw = {"schema_version": 1, "victory": {"target": 8}}
        self.assertEqual(migrate(raw), raw)
        self.assertEqual(migrate({}), {})

    def test_fake_v0_to_v1(self) -> None:
        def v0_to_v1(data: dict[str, Any]) -> dict[str, Any]:
            data = dict(data)
            data["clock"] = {"roll_interval_ms": data.pop("roll_seconds") * 1000}
            return data

        raw = {"schema_version": 0, "roll_seconds": 30}
        out = migrate(raw, migrations={0: v0_to_v1})
        self.assertEqual(out, {"schema_version": 1, "clock": {"roll_interval_ms": 30000}})
        self.assertEqual(raw["schema_version"], 0)  # input untouched
        self.assertEqual(GameSettings.model_validate(out).clock.roll_interval_ms, 30000)

    def test_errors(self) -> None:
        with self.assertRaises(MigrationError):
            migrate({"schema_version": 0})
        with self.assertRaises(MigrationError):
            migrate({"schema_version": 2})
        with self.assertRaises(MigrationError):
            migrate({"schema_version": "1"})


class SchemaTest(unittest.TestCase):
    def test_export(self) -> None:
        schema = export_json_schema()
        json.dumps(schema)
        self.assertEqual(schema["x-implemented-stage"], IMPLEMENTED_STAGE)
        self.assertEqual(schema["x-later-stage-values"]["BoardLayout"], {"beginner": 3})
        props = schema["properties"]
        self.assertEqual(props["dev_cards"]["stage"], 2)
        clock = schema["$defs"]["ClockSettings"]["properties"]["roll_interval_ms"]
        self.assertEqual((clock["minimum"], clock["maximum"], clock["default"]), (5000, 120000, 20000))
        self.assertEqual(clock["label"], "settings.clock.roll_interval_ms")


if __name__ == "__main__":
    unittest.main()
