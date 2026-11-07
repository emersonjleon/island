import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i18n_check as ic  # noqa: E402

PO = r'''
msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\n"

#: a.py:1
msgid "Hello"
msgstr "Hola"

#: a.py:2
msgid ""
"Long text "
"continued"
msgstr ""
"Texto largo "
"continuado"

#, fuzzy
msgid "Guess"
msgstr "Adivina"

msgid "Missing"
msgstr ""

msgid "one apple"
msgid_plural "{n} apples"
msgstr[0] "una manzana"
msgstr[1] ""

#~ msgid "Old"
#~ msgstr "Viejo"
'''


class ParsePoTests(unittest.TestCase):
    def test_parse(self) -> None:
        entries = {e.msgid: e for e in ic.parse_po(PO)}
        self.assertEqual(set(entries), {"Hello", "Long text continued", "Guess", "Missing", "one apple"})
        self.assertEqual(entries["Long text continued"].msgstrs, ("Texto largo continuado",))
        self.assertTrue(entries["Guess"].fuzzy)
        self.assertEqual(entries["one apple"].msgid_plural, "{n} apples")

    def test_problems(self) -> None:
        problems = ic.problems_in_catalogue(ic.parse_po(PO), "es")
        self.assertEqual(len(problems), 3)
        self.assertTrue(any("fuzzy" in p and "Guess" in p for p in problems))
        self.assertTrue(any("Missing" in p for p in problems))
        self.assertTrue(any("one apple" in p for p in problems))

    def test_stale(self) -> None:
        old = ic.parse_po('msgid "A"\nmsgstr "a"\n\nmsgid "B"\nmsgstr "b"\n')
        new = ic.parse_po('msgid "A"\nmsgstr ""\n\nmsgid "C"\nmsgstr ""\n')
        out = ic.stale_catalogue(old, new)
        self.assertEqual(len(out), 2)
        self.assertIn("'C'", out[0])
        self.assertIn("'B'", out[1])


class RepoTests(unittest.TestCase):
    def test_repository_catalogues_are_complete(self) -> None:
        for lang in ic.TRANSLATED_LANGUAGES:
            entries = ic.parse_po(ic.catalogue(lang).read_text(encoding="utf8"))
            self.assertGreater(len(entries), 50)
            self.assertEqual(ic.problems_in_catalogue(entries, lang), [])

    def test_every_lobby_code_has_a_message(self) -> None:
        self.assertEqual(ic.lobby_codes_without_message(), [])

    def test_lobby_code_pattern(self) -> None:
        src = 'raise LobbyError("lobby.full")\nproblems.append("lobby.too_few")\nx = {"type": "lobby.changed"}'
        self.assertEqual(ic.LOBBY_ERROR_RE.findall(src), ["lobby.full", "lobby.too_few"])


if __name__ == "__main__":
    unittest.main()
