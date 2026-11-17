"""Chat limits. Override any of them with a ``CHAT`` dict in the Django settings."""
from django.conf import settings

DEFAULTS = {
    "MAX_LENGTH": 200,         # characters in one message (after trimming spaces)
    "HISTORY": 60,             # messages sent to someone who opens the page
    "RATE_PER_SECOND": 0.5,    # steady sending rate per connection...
    "BURST": 5,                # ...with short bursts up to this many messages
    "PUBLIC_HISTORY": 60,      # public-room lines sent when the site-wide chat opens
    "DM_HISTORY": 200,         # latest private messages (all conversations) sent when it opens
}


def get(name: str):
    return {**DEFAULTS, **getattr(settings, "CHAT", {})}[name]
