"""Operational values of the game host. Django settings override each default (GAMEHOST_<NAME>)."""
from django.conf import settings

DEFAULTS = {
    "CHANNEL": "gamehost",            # channel the lobby and the game consumers send to
    "FLUSH_MS": 1000,                 # write buffered commands at least this often
    "MAX_IDLE_MS": 1000,              # longest a game loop sleeps without a timer or command
    "SCAN_S": 5,                      # look for STARTING / orphaned RUNNING games this often
    "SNAPSHOT_EVERY_ROLLS": 1,        # snapshot after this many dice rolls (0 = only start/end/shutdown)
    "SNAPSHOTS_KEPT": 5,              # older snapshots of a game are deleted
    "LEASE_TTL_MS": 10000,
    "LEASE_REFRESH_MS": 3000,
}


def get(name: str):
    return getattr(settings, f"GAMEHOST_{name}", DEFAULTS[name])
