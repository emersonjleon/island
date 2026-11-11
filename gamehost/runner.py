"""The game host: one asyncio task per live game, fed by the ``gamehost`` channel."""
import asyncio
import logging
from typing import Any

from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer

from lobby.services import started_message

from . import conf, store
from .clock import MonotonicClock
from .core import GameCore, Outgoing
from .leases import make_leases
from .models import GameSnapshot

log = logging.getLogger(__name__)
db = sync_to_async  # ORM calls run in the default thread executor
RECEIVE_RETRY_S = 0.1


class GameRunner:
    def __init__(self, core: GameCore, layer, clock=None):
        self.core = core
        self.layer = layer
        self.clock = clock or MonotonicClock(core.state.now_ms)
        self.inbox: asyncio.Queue = asyncio.Queue()
        self._last_flush = self.clock.now()

    async def send(self, out: list[Outgoing]) -> None:
        for o in out:
            if o.kind == "group":
                await self.layer.group_send(o.target, o.message)
            else:
                await self.layer.send(o.target, o.message)

    def _timeout(self) -> float:
        now = self.clock.now()
        wake = self.core.next_wakeup()
        limit = conf.get("MAX_IDLE_MS")
        delay = limit if wake is None else max(0, min(wake - now, limit))
        return delay / 1000

    async def step(self, item: dict[str, Any] | None) -> None:
        """Fire due timers, handle one inbox item, persist when due."""
        now = self.clock.now()
        out = self.core.advance(now)
        if item is not None:
            kind = item.get("type")
            if kind == "game.intent":
                out += self.core.intent(now, item)
            elif kind == "game.sync":
                out += self.core.sync(item)
        out += self.core.bots_act(now)
        await self.send(out)
        await self.persist()

    async def persist(self, force_flush: bool = False) -> None:
        core = self.core
        every = conf.get("SNAPSHOT_EVERY_ROLLS")
        if core.finished:
            return
        if every and core.rolls_since_snapshot >= every:
            await db(store.save_snapshot)(core, GameSnapshot.Kind.ROLL)
            self._last_flush = self.clock.now()
        elif core.pending and (force_flush or self.clock.now() - self._last_flush >= conf.get("FLUSH_MS")):
            await db(store.flush_commands)(core)
            self._last_flush = self.clock.now()

    async def run(self) -> None:
        while not self.core.finished:
            try:
                item = await asyncio.wait_for(self.inbox.get(), self._timeout())
            except TimeoutError:
                item = None
            if item is not None and item.get("type") == "stop":
                return
            await self.step(item)
        await db(store.finish_game)(self.core)


class GameHost:
    """Owns the running games of this process."""

    def __init__(self, layer=None, leases=None, clock_factory=MonotonicClock):
        self.layer = layer or get_channel_layer()
        self.leases = leases or make_leases()
        self.clock_factory = clock_factory
        self.runners: dict[int, GameRunner] = {}
        self.tasks: dict[int, asyncio.Task] = {}
        self._taking: set[int] = set()
        self.channel = conf.get("CHANNEL")

    # ----------------------------------------------------------- taking games
    async def take(self, game_id: int) -> GameRunner | None:
        """Start (STARTING) or restore (RUNNING) a game if no other host holds it."""
        if game_id in self.runners:
            return self.runners[game_id]
        if game_id in self._taking:  # a game.start and a scan can race for the same game
            return None
        self._taking.add(game_id)
        try:
            return await self._take(game_id)
        finally:
            self._taking.discard(game_id)

    async def _take(self, game_id: int) -> GameRunner | None:
        game = await db(store.get_game)(game_id)
        if game is None or game.status not in ("STARTING", "RUNNING"):
            return None
        if not await self.leases.acquire(game_id):
            return None
        try:
            if game.status == "STARTING":
                core = await db(store.create_core)(game)
                resumed = False
            else:
                core = await db(store.restore_core)(game)
                resumed = True
        except Exception:
            log.exception("could not load game %s", game_id)
            await self.leases.release(game_id)
            if game.status == "STARTING":
                await db(store.abort_game)(game_id)
            return None
        runner = GameRunner(core, self.layer, self.clock_factory(core.state.now_ms))
        self.runners[game_id] = runner
        if resumed:
            await runner.send(core.resumed_messages())
        else:
            await self.layer.group_send(game.group_name, started_message(game))
        self.tasks[game_id] = asyncio.create_task(self._run(game_id, runner), name=f"game-{game.code}")
        log.info("%s game %s", "restored" if resumed else "started", game.code)
        return runner

    async def _run(self, game_id: int, runner: GameRunner) -> None:
        try:
            await runner.run()
        except Exception:
            log.exception("game %s crashed; it will be restored from its last snapshot", game_id)
        finally:
            self.runners.pop(game_id, None)
            self.tasks.pop(game_id, None)
            await self.leases.release(game_id)

    async def scan(self) -> None:
        starting, running = await db(store.games_to_take)()
        for game_id in starting + [g for g in running if g not in self.runners]:
            await self.take(game_id)

    # ----------------------------------------------------------- messages
    async def dispatch(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        game_id = message.get("game_id")
        if kind == "game.start":
            await self.take(game_id)
            return
        runner = self.runners.get(game_id)
        if runner is None:
            reply = message.get("reply_channel")
            if reply and kind == "game.intent":
                await self.layer.send(reply, {"type": "game.out", "msg": {
                    "t": "reject", "cid": message.get("cid"), "code": "game.not_running", "params": {}}})
            return
        if kind == "game.ping":
            # Answered at once (not queued) so the round trip measures the network, not the game loop.
            reply = message.get("reply_channel")
            if reply:
                await self.layer.send(reply, {"type": "game.out", "msg": {
                    "t": "pong", "c": message.get("c"), "now": runner.clock.now()}})
        elif kind in ("game.intent", "game.sync"):
            runner.inbox.put_nowait(message)

    async def receive_loop(self) -> None:
        while True:
            try:
                message = await self.layer.receive(self.channel)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # e.g. a Redis read timeout while idle: nothing was taken off the channel, so retry.
                log.debug("gamehost receive failed (%r); retrying", exc)
                await asyncio.sleep(RECEIVE_RETRY_S)
                continue
            try:
                await self.dispatch(message)
            except Exception:
                log.exception("bad gamehost message %r", message.get("type"))

    async def scan_loop(self) -> None:
        while True:
            try:
                await self.scan()
                for game_id in list(self.runners):
                    if not await self.leases.refresh(game_id):
                        log.warning("lost lease on game %s; stopping it", game_id)
                        await self.stop_game(game_id, snapshot=False)
            except Exception:
                log.exception("scan failed")
            await asyncio.sleep(min(conf.get("SCAN_S"), conf.get("LEASE_REFRESH_MS") / 1000))

    # ----------------------------------------------------------- shutdown
    async def stop_game(self, game_id: int, snapshot: bool = True) -> None:
        runner = self.runners.get(game_id)
        task = self.tasks.get(game_id)
        if runner is None or task is None:
            return
        runner.inbox.put_nowait({"type": "stop"})
        await task
        if snapshot and not runner.core.finished:
            await db(store.save_snapshot)(runner.core, GameSnapshot.Kind.SHUTDOWN)

    async def shutdown(self) -> None:
        """Flush, snapshot every game and release the leases."""
        for game_id in list(self.runners):
            await self.stop_game(game_id)

    async def serve(self, stop: asyncio.Event) -> None:
        workers = [asyncio.create_task(self.receive_loop()), asyncio.create_task(self.scan_loop())]
        await stop.wait()
        for w in workers:
            w.cancel()
        await self.shutdown()
