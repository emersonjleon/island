"""Which game host owns a game. Redis keys with a TTL in production; in-process for dev/tests."""
import uuid

from django.conf import settings

from . import conf


def lease_key(game_id: int) -> str:
    return f"gamehost:lease:{game_id}"


class LocalLeases:
    """Single-process stand-in (no Redis configured)."""

    def __init__(self):
        self.owner = uuid.uuid4().hex
        self._held: set[int] = set()

    async def acquire(self, game_id: int) -> bool:
        if game_id in self._held:
            return True
        self._held.add(game_id)
        return True

    async def refresh(self, game_id: int) -> bool:
        return game_id in self._held

    async def release(self, game_id: int) -> None:
        self._held.discard(game_id)


_RELEASE = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
_REFRESH = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('pexpire', KEYS[1], ARGV[2]) else return 0 end"


class RedisLeases:
    def __init__(self, url: str):
        import redis.asyncio as aioredis

        self.redis = aioredis.from_url(url)
        self.owner = uuid.uuid4().hex
        self.ttl = conf.get("LEASE_TTL_MS")

    async def acquire(self, game_id: int) -> bool:
        key = lease_key(game_id)
        if await self.redis.set(key, self.owner, nx=True, px=self.ttl):
            return True
        return (await self.redis.get(key)) == self.owner.encode()

    async def refresh(self, game_id: int) -> bool:
        return bool(await self.redis.eval(_REFRESH, 1, lease_key(game_id), self.owner, self.ttl))

    async def release(self, game_id: int) -> None:
        await self.redis.eval(_RELEASE, 1, lease_key(game_id), self.owner)


def make_leases():
    url = getattr(settings, "REDIS_URL", "")
    backend = settings.CHANNEL_LAYERS.get("default", {}).get("BACKEND", "")
    if url and "redis" in backend.lower():
        return RedisLeases(url)
    return LocalLeases()
