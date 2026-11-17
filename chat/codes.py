"""Codes the chat sends back in a ``notice``; like the engine's codes they are i18n keys."""
EMPTY = "chat.empty"
TOO_LONG = "chat.too_long"            # params: {"max": n}
RATE_LIMITED = "chat.rate_limited"

# Site-wide chat (public room, friends, private messages).
PUBLIC_OFF = "chat.public_off"        # your privacy setting hides the public chat
DM_OFF = "chat.dm_off"                # your privacy setting is "only in games"
DM_FRIENDS_ONLY = "chat.dm_friends_only"  # your setting is "only friends" and they are not one
DM_REFUSED = "chat.dm_refused"        # params: {"name": ...}; their setting does not take your message
NO_USER = "chat.no_user"              # params: {"name": ...}
FRIEND_SELF = "chat.friend_self"
FRIEND_ALREADY = "chat.friend_already"  # params: {"name": ...}
BAD_PRIVACY = "chat.bad_privacy"

ALL = [
    EMPTY, TOO_LONG, RATE_LIMITED, PUBLIC_OFF, DM_OFF, DM_FRIENDS_ONLY, DM_REFUSED, NO_USER,
    FRIEND_SELF, FRIEND_ALREADY, BAD_PRIVACY,
]
