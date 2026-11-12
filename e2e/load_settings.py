"""Settings for the game host load smoke (e2e/load_smoke.py): dev settings and a
separate database. Games keep the settings the script passes (no forced overrides)."""
from config.settings.dev import *  # noqa: F401,F403
from config.settings.dev import BASE_DIR, DATABASES

DATABASES["default"]["NAME"] = BASE_DIR / "e2e_load.sqlite3"
DATABASES["default"].setdefault("OPTIONS", {})["timeout"] = 30  # SQLite: wait for the writer, don't fail
LOBBY_FORCED_OVERRIDES = None
