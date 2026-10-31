from .base import *  # noqa: F403
from .base import env, env_bool

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

# SQLite unless Postgres is configured, so `manage.py runserver` works without docker.
if not env_bool("USE_POSTGRES"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
        }
    }

if not env("REDIS_URL"):
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
