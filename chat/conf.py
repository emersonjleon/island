"""Chat limits. Override any of them with a ``CHAT`` dict in the Django settings."""
from django.conf import settings

DEFAULTS = {
    "MAX_LENGTH": 200,         # characters in one message (after trimming spaces)
    "HISTORY": 60,             # messages sent to someone who opens the page
    "RATE_PER_SECOND": 0.5,    # steady sending rate per connection...
    "BURST": 5,                # ...with short bursts up to this many messages
    "PAGE": 50,                # site-wide chat: messages per page of history (public room or a conversation)
    "CONVERSATIONS": 50,       # latest private conversations listed when the site-wide chat opens
    "PUBLIC_RETENTION_DAYS": 30,  # prune_chat deletes public-room messages older than this
}


def get(name: str):
    return {**DEFAULTS, **getattr(settings, "CHAT", {})}[name]
