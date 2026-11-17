"""Chat limits. Override any of them with a ``CHAT`` dict in the Django settings."""
from django.conf import settings

DEFAULTS = {
    "MAX_LENGTH": 200,         # characters in one message (after trimming spaces)
    "HISTORY": 60,             # messages sent to someone who opens the page
    "RATE_PER_SECOND": 0.5,    # steady sending rate per connection...
    "BURST": 5,                # ...with short bursts up to this many messages
}


def get(name: str):
    return {**DEFAULTS, **getattr(settings, "CHAT", {})}[name]
