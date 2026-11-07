"""Translation completeness checks for the Django side (WP17).

Usage:
    python scripts/i18n_check.py                     # translations complete, lobby codes covered
    python scripts/i18n_check.py --committed OLD.po  # also: OLD.po has the same msgids as the
                                                     # freshly extracted locale/es/.../django.po

CI copies the committed Spanish catalogue aside, runs ``makemessages -l es`` and then
calls this with ``--committed`` so a string added to a template or view without running
``makemessages`` fails the build. The game client's JSON catalogues are checked by
Vitest (frontend/src/i18n/catalogues.test.ts and ui/model.test.ts).

Only the standard library is used, so it runs before the project is installed.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRANSLATED_LANGUAGES = ("es",)          # English is the source language: msgstr stays empty
LOBBY_CODE_RE = re.compile(r"""["'](lobby\.[a-z_]+)["']""")
# Codes raised as LobbyError(...) or collected by start_problems(); channel message types
# such as {"type": "lobby.changed"} are not user-facing and are left out.
LOBBY_ERROR_RE = re.compile(r"""(?:LobbyError\(|\.append\()\s*["'](lobby\.[a-z_]+)["']""")


@dataclass(frozen=True)
class Entry:
    msgid: str
    msgid_plural: str
    msgstrs: tuple[str, ...]
    fuzzy: bool

    @property
    def key(self) -> tuple[str, str]:
        return self.msgid, self.msgid_plural


def _unquote(line: str) -> str:
    return ast.literal_eval(line.strip())


def parse_po(text: str) -> list[Entry]:
    """A small .po reader: msgctxt is not used in this project and obsolete entries are skipped."""
    entries: list[Entry] = []
    fields: dict[str, list[str]] = {}
    current: str | None = None
    fuzzy = False

    def flush() -> None:
        nonlocal fields, current, fuzzy
        if "msgid" in fields:
            strs = tuple("".join(v) for k, v in sorted(fields.items()) if k.startswith("msgstr"))
            entries.append(Entry("".join(fields["msgid"]), "".join(fields.get("msgid_plural", [])), strs, fuzzy))
        fields, current, fuzzy = {}, None, False

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            flush()
        elif line.startswith("#~"):
            continue
        elif line.startswith("#,"):
            fuzzy = fuzzy or "fuzzy" in line
        elif line.startswith("#"):
            continue
        elif line.startswith('"'):
            if current is not None:
                fields[current].append(_unquote(line))
        else:
            name, _, rest = line.partition(" ")
            if name == "msgid" and "msgid" in fields:
                flush()
            current = name
            fields[current] = [_unquote(rest)]
    flush()
    return [e for e in entries if e.msgid]          # drop the header entry


def problems_in_catalogue(entries: list[Entry], lang: str) -> list[str]:
    out = []
    for e in entries:
        if e.fuzzy:
            out.append(f"{lang}: fuzzy translation for {e.msgid!r}")
        elif not all(e.msgstrs) or not e.msgstrs:
            out.append(f"{lang}: missing translation for {e.msgid!r}")
    return out


def stale_catalogue(committed: list[Entry], extracted: list[Entry]) -> list[str]:
    old = {e.key for e in committed}
    new = {e.key for e in extracted}
    return ([f"not in the committed catalogue (run makemessages): {m[0]!r}" for m in sorted(new - old)]
            + [f"no longer used (run makemessages --no-obsolete): {m[0]!r}" for m in sorted(old - new)])


def lobby_codes_without_message(root: Path = ROOT) -> list[str]:
    messages = (root / "lobby" / "messages.py").read_text(encoding="utf8")
    known = set(LOBBY_CODE_RE.findall(messages))
    used: set[str] = set()
    for path in (root / "lobby").glob("*.py"):
        if path.name != "messages.py":
            used |= set(LOBBY_ERROR_RE.findall(path.read_text(encoding="utf8")))
    return [f"lobby code without a message in lobby/messages.py: {c}" for c in sorted(used - known)]


def catalogue(lang: str, root: Path = ROOT) -> Path:
    return root / "locale" / lang / "LC_MESSAGES" / "django.po"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--committed", type=Path, help="the Spanish catalogue as committed, before makemessages")
    args = parser.parse_args(argv)

    problems: list[str] = []
    for lang in TRANSLATED_LANGUAGES:
        source = args.committed if args.committed and lang == "es" else catalogue(lang)
        problems += problems_in_catalogue(parse_po(source.read_text(encoding="utf8")), lang)
    if args.committed:
        problems += stale_catalogue(parse_po(args.committed.read_text(encoding="utf8")),
                                    parse_po(catalogue("es").read_text(encoding="utf8")))
    problems += lobby_codes_without_message()

    for p in problems:
        print(p, file=sys.stderr)
    print(f"i18n check: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
