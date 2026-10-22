import json
import unittest

from engine.commands import (
    COMMAND_TYPES, BankTrade, Build, CancelBuild, MoveSettler, command_json_schema, parse_command,
)
from engine.errors import RuleError
from engine.settings.enums import BuildKind, Resource


class ParseTest(unittest.TestCase):
    def test_protocol_examples(self) -> None:
        cmd = parse_command({"t": "intent", "cid": "a17", "a": "move_settler", "settler": 3, "to_vertex": 41,
                             "mode": "replace"})
        self.assertEqual(cmd, MoveSettler(settler=3, to_vertex=41))
        cmd = parse_command({"a": "move_settler", "settler": 3, "to_vertex": 42, "mode": "append"})
        self.assertEqual(cmd.mode, "append")  # type: ignore[union-attr]
        b = parse_command({"a": "build", "kind": "settlement", "vertex": 41, "settler": 3})
        self.assertIsInstance(b, Build)
        self.assertEqual((b.kind, b.target, b.settler), (BuildKind.SETTLEMENT, 41, 3))  # type: ignore[union-attr]
        r = parse_command({"a": "build", "kind": "road", "edge": 88})
        self.assertEqual(r.target, 88)  # type: ignore[union-attr]
        self.assertEqual(parse_command({"a": "build", "kind": "city", "vertex": 17}).target, 17)  # type: ignore[union-attr]
        self.assertEqual(parse_command({"a": "cancel_build", "construction": 12}), CancelBuild(construction=12))
        t = parse_command({"a": "bank_trade", "give": {"lumber": 4}, "get": {"ore": 1}})
        self.assertEqual(t, BankTrade(give={Resource.LUMBER: 4}, get={Resource.ORE: 1}))

    def test_model_passthrough(self) -> None:
        m = MoveSettler(settler=1, to_vertex=2)
        self.assertIs(parse_command(m), m)

    def assertInvalid(self, raw: object, action: str | None = None) -> RuleError:
        with self.assertRaises(RuleError) as cm:
            parse_command(raw)
        self.assertEqual(cm.exception.code, "command.invalid")
        self.assertEqual(cm.exception.params["action"], action)
        json.dumps(cm.exception.params)
        return cm.exception

    def test_rejects(self) -> None:
        self.assertInvalid("nope")
        self.assertInvalid({})
        self.assertInvalid({"a": "fly"}, "fly")
        self.assertInvalid({"a": "build", "kind": "road", "vertex": 3}, "build")
        self.assertInvalid({"a": "build", "kind": "road", "edge": 3, "vertex": 3}, "build")
        self.assertInvalid({"a": "build", "kind": "settlement", "edge": 3}, "build")
        self.assertInvalid({"a": "build", "kind": "castle", "vertex": 3}, "build")
        err = self.assertInvalid({"a": "move_settler", "settler": "3", "to_vertex": 1}, "move_settler")
        self.assertEqual(err.params["errors"][0]["loc"], "settler")
        self.assertInvalid({"a": "move_settler", "settler": True, "to_vertex": 1}, "move_settler")
        self.assertInvalid({"a": "move_settler", "settler": -1, "to_vertex": 1}, "move_settler")
        self.assertInvalid({"a": "move_settler", "settler": 1, "to_vertex": 1, "mode": "x"}, "move_settler")
        self.assertInvalid({"a": "move_settler", "settler": 1, "to_vertex": 1, "extra": 1}, "move_settler")
        self.assertInvalid({"a": "cancel_build", "construction": 1.0}, "cancel_build")
        self.assertInvalid({"a": "bank_trade", "give": {"lumber": 4}, "get": {"lumber": 1}}, "bank_trade")
        self.assertInvalid({"a": "bank_trade", "give": {"lumber": 4, "ore": 4}, "get": {"wool": 1}}, "bank_trade")
        self.assertInvalid({"a": "bank_trade", "give": {"lumber": 0}, "get": {"wool": 1}}, "bank_trade")
        self.assertInvalid({"a": "bank_trade", "give": {"gold": 4}, "get": {"wool": 1}}, "bank_trade")
        self.assertInvalid({"a": "bank_trade", "give": {}, "get": {"wool": 1}}, "bank_trade")

    def test_schema(self) -> None:
        schema = command_json_schema()
        text = json.dumps(schema)
        for name in COMMAND_TYPES:
            self.assertIn(name, text)
        self.assertEqual(set(COMMAND_TYPES), {"move_settler", "build", "cancel_build", "bank_trade"})


if __name__ == "__main__":
    unittest.main()
