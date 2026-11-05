"""Codes the WebSocket edge itself sends (``reject`` / ``notice``), besides the engine's.

Like engine codes they are i18n keys; the client translates them.
"""
INTENT_SPECTATOR = "intent.spectator"          # spectators may only sync
INTENT_RATE_LIMITED = "intent.rate_limited"
INTENT_BAD_CID = "intent.bad_cid"
MESSAGE_TOO_LARGE = "message.too_large"
MESSAGE_INVALID = "message.invalid"             # not a JSON object with a known "t"
PROTO_UNSUPPORTED = "proto.unsupported"
GAME_NOT_RUNNING = "game.not_running"           # sent by the game host when it does not own the game

ALL = [
    INTENT_SPECTATOR, INTENT_RATE_LIMITED, INTENT_BAD_CID, MESSAGE_TOO_LARGE, MESSAGE_INVALID,
    PROTO_UNSUPPORTED, GAME_NOT_RUNNING,
]
