"""The engine must stay pure: no Django/Channels, no wall clock, no global randomness."""
import ast
import pathlib
import unittest

ENGINE = pathlib.Path(__file__).resolve().parents[1]
FORBIDDEN = {"django", "channels", "random", "time", "datetime", "threading", "asyncio", "socket", "requests"}


class PurityTest(unittest.TestCase):
    def test_no_forbidden_imports(self) -> None:
        offenders = []
        for path in ENGINE.rglob("*.py"):
            if "tests" in path.relative_to(ENGINE).parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    names = [node.module]
                for name in names:
                    if name.split(".")[0] in FORBIDDEN:
                        offenders.append(f"{path.relative_to(ENGINE)}: {name}")
        self.assertEqual(offenders, [], "forbidden imports in engine")


if __name__ == "__main__":
    unittest.main()
