"""Settings for the end-to-end smoke test: dev settings, a separate database, and
every new game forced to a short game with plenty of resources (e2e/fast_game.json)."""
import json
from pathlib import Path

from config.settings.dev import *  # noqa: F401,F403
from config.settings.dev import BASE_DIR, DATABASES

DATABASES["default"]["NAME"] = BASE_DIR / "e2e.sqlite3"
LOBBY_FORCED_OVERRIDES = json.loads((Path(__file__).with_name("fast_game.json")).read_text(encoding="utf-8"))
