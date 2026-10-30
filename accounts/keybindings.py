"""Validation for the key-binding map stored on the user.

The server does not know the action list (the client owns it); it only checks the
shape and size so a client cannot store arbitrary blobs.
"""
import re

MAX_ACTIONS = 100
MAX_COMBOS_PER_ACTION = 4
MAX_TOKEN_LENGTH = 64
NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
COMBO_RE = re.compile(r"^[A-Za-z0-9+_\-.]+$")


class KeybindingsError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def validate_keybindings(data: object) -> dict[str, list[str]]:
    if not isinstance(data, dict):
        raise KeybindingsError("keybindings.not_object")
    if len(data) > MAX_ACTIONS:
        raise KeybindingsError("keybindings.too_many_actions")
    clean: dict[str, list[str]] = {}
    for action, combos in data.items():
        if not isinstance(action, str) or len(action) > MAX_TOKEN_LENGTH or not NAME_RE.match(action):
            raise KeybindingsError("keybindings.bad_action")
        if not isinstance(combos, list) or len(combos) > MAX_COMBOS_PER_ACTION:
            raise KeybindingsError("keybindings.bad_combos")
        for combo in combos:
            if not isinstance(combo, str) or not 0 < len(combo) <= MAX_TOKEN_LENGTH or not COMBO_RE.match(combo):
                raise KeybindingsError("keybindings.bad_combo")
        clean[action] = list(combos)
    return clean
