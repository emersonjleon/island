"""Codes the chat sends back in a ``notice``; like the engine's codes they are i18n keys."""
EMPTY = "chat.empty"
TOO_LONG = "chat.too_long"            # params: {"max": n}
RATE_LIMITED = "chat.rate_limited"

ALL = [EMPTY, TOO_LONG, RATE_LIMITED]
