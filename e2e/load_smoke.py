"""Game host load smoke: many bot games in one game host process, measuring loop lag.

    python e2e/load_smoke.py [--games 200] [--seconds 60] [--players 3] [--max-late-p99-ms 250]

It uses e2e/load_settings.py (a fresh e2e_load.sqlite3; the Redis channel layer and
leases when REDIS_URL is set, the in-memory ones otherwise) and runs, in one asyncio
loop, a real ``GameHost`` with its receive and scan loops. Games are created and started
through the lobby services, so the host takes them from its ``game.start`` message, as
in production. Greedy bots send their intents with a reply
channel on the ``gamehost`` channel, as the web consumers do.

Measured:

* **timer lateness** -- how long after its due time each engine timer (dice rolls,
  settler steps, builds) is fired. Logical game time is exact anyway; this is the delay
  players would see.
* **loop lag** -- how late a 50 ms sleep in the same loop wakes up.
* **intent round trip** -- dispatch to ack/reject.

The bots think in the same process, so their CPU time counts against the host; the
report shows how much of it was theirs. Exits 1 when a game crashed or the p99 timer
lateness is over the limit.
"""
from __future__ import annotations

import argparse
import asyncio
import itertools
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE_S = 0.05


@dataclass
class Stats:
    late_ms: list[int] = field(default_factory=list)
    lag_ms: list[float] = field(default_factory=list)
    rtt_ms: list[float] = field(default_factory=list)
    acks: int = 0
    rejects: int = 0
    bot_cpu_s: float = 0.0
    start_ms: list[float] = field(default_factory=list)


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, int(len(s) * p / 100))]


def summary(name: str, values: list[float]) -> str:
    return (f"{name:<20} n={len(values):<7} p50={pct(values, 50):7.1f}  p95={pct(values, 95):7.1f}  "
            f"p99={pct(values, 99):7.1f}  max={max(values, default=0):7.1f} ms")


def setup_django() -> None:
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "e2e.load_settings")
    import django

    django.setup()
    from django.conf import settings
    from django.core.management import call_command

    db = settings.DATABASES["default"]
    if db["ENGINE"].endswith("sqlite3"):
        Path(db["NAME"]).unlink(missing_ok=True)
    call_command("migrate", verbosity=0)


def make_users(count: int):
    """Bulk users without password hashing (hashing 600 passwords would take minutes)."""
    from accounts.models import User

    User.objects.bulk_create([User(username=f"load{i}", email=f"load{i}@example.com", password="!")
                              for i in range(count)])
    return list(User.objects.filter(username__startswith="load").order_by("id"))


def start_one(users, overrides) -> int:
    from lobby import services

    game = services.create_game(users[0], "classic", overrides)
    for u in users[1:]:
        services.join_game(game, u)
        services.set_ready(game, u, True)
    return services.start_game(game, users[0]).pk


def instrument(stats: Stats) -> None:
    """Record how late due timers are when the game core gets to them."""
    from gamehost.core import GameCore

    original = GameCore.advance

    def advance(self, now):
        timers = self.state.timers
        due = timers.next_due()
        if due is not None and due <= now and not self.finished:
            stats.late_ms.append(now - due)
        return original(self, now)

    GameCore.advance = advance


async def probe(stats: Stats, stop: asyncio.Event) -> None:
    while not stop.is_set():
        t0 = time.perf_counter()
        await asyncio.sleep(PROBE_S)
        stats.lag_ms.append((time.perf_counter() - t0 - PROBE_S) * 1000)


async def drive(host, game_id: int, stats: Stats, stop: asyncio.Event, think_s: float, seed: int) -> None:
    """Greedy bots for one game, sending intents the way the web consumer does."""
    from engine.sim.bots import GreedyBot

    while game_id not in host.runners:
        if stop.is_set():
            return
        await asyncio.sleep(0.05)
    runner = host.runners[game_id]
    bots = [GreedyBot(p.seat, seed * 10 + p.seat) for p in runner.core.state.players]
    reply = await host.layer.new_channel()
    cids = itertools.count()
    # Spread the games over the think period so they don't all act at once.
    await asyncio.sleep(think_s * (seed % 97) / 97)
    while not stop.is_set() and not runner.core.finished and game_id in host.runners:
        for bot in bots:
            t0 = time.process_time()
            intents = bot.decide(runner.core.state)
            stats.bot_cpu_s += time.process_time() - t0
            for payload in intents:
                cid = str(next(cids))
                sent = time.perf_counter()
                # Through the gamehost channel, like the web consumer (not a direct dispatch).
                await host.layer.send(host.channel, {"type": "game.intent", "game_id": game_id, "seat": bot.seat,
                                                     "cid": cid, "payload": payload, "reply_channel": reply})
                while True:
                    msg = (await host.layer.receive(reply))["msg"]
                    if msg.get("cid") == cid and msg["t"] in ("ack", "reject"):
                        break
                stats.rtt_ms.append((time.perf_counter() - sent) * 1000)
                if msg["t"] == "ack":
                    stats.acks += 1
                else:
                    stats.rejects += 1
        await asyncio.sleep(think_s)


async def run(args) -> int:
    from asgiref.sync import sync_to_async
    from django.conf import settings

    from gamehost.runner import GameHost
    from lobby.models import Game

    stats = Stats()
    instrument(stats)
    users = await sync_to_async(make_users)(args.games * args.players)
    overrides = {"players": {"max": args.players}, "clock": {"roll_interval_ms": args.roll_ms}}

    host = GameHost()
    stop_host, stop_load = asyncio.Event(), asyncio.Event()
    serving = asyncio.create_task(host.serve(stop_host))
    probing = asyncio.create_task(probe(stats, stop_load))
    layer = type(host.layer).__name__
    print(f"{args.games} games x {args.players} players, roll every {args.roll_ms} ms, "
          f"{args.seconds} s, layer {layer}, db {settings.DATABASES['default']['ENGINE'].rsplit('.', 1)[-1]}")

    cpu0, wall0 = time.process_time(), time.perf_counter()
    drivers = []
    for i in range(args.games):
        t0 = time.perf_counter()
        seats = users[i * args.players:(i + 1) * args.players]
        game_id = await sync_to_async(start_one)(seats, overrides)
        stats.start_ms.append((time.perf_counter() - t0) * 1000)
        drivers.append(asyncio.create_task(drive(host, game_id, stats, stop_load, args.think_s, i + 1)))
    deadline = time.perf_counter() + 30
    while len(host.runners) < args.games and time.perf_counter() < deadline:
        await asyncio.sleep(0.1)
    started = len(host.runners)
    print(f"started {started}/{args.games} games in {time.perf_counter() - wall0:.1f} s")
    # Measure the steady state only, not the start-up burst.
    stats.late_ms.clear(), stats.lag_ms.clear(), stats.rtt_ms.clear()
    cpu1, wall1, bot1 = time.process_time(), time.perf_counter(), stats.bot_cpu_s

    await asyncio.sleep(args.seconds)
    stop_load.set()
    await asyncio.gather(*drivers, probing)
    wall, cpu, bot = time.perf_counter() - wall1, time.process_time() - cpu1, stats.bot_cpu_s - bot1
    running = len(host.runners)
    finished = await sync_to_async(Game.objects.filter(status="FINISHED").count)()

    t0 = time.perf_counter()
    stop_host.set()
    await serving
    shutdown_s = time.perf_counter() - t0

    late = [float(x) for x in stats.late_ms]
    print(summary("game start (lobby)", stats.start_ms))
    print(summary("timer lateness", late))
    print(summary("loop lag", stats.lag_ms))
    print(summary("intent round trip", stats.rtt_ms))
    print(f"intents: {stats.acks} accepted, {stats.rejects} refused; "
          f"{stats.acks / wall:.0f} accepted/s")
    print(f"cpu: {100 * cpu / wall:.0f}% of one core ({100 * bot / wall:.0f}% bots, "
          f"{100 * (cpu - bot) / wall:.0f}% host)")
    print(f"games: {running} running, {finished} finished; shutdown snapshot took {shutdown_s:.1f} s")

    crashed = args.games - running - finished
    failures = []
    if started < args.games:
        failures.append(f"only {started} of {args.games} games started")
    if crashed > 0:
        failures.append(f"{crashed} games stopped without finishing (see the log)")
    if pct(late, 99) > args.max_late_p99_ms:
        failures.append(f"p99 timer lateness {pct(late, 99):.0f} ms > {args.max_late_p99_ms} ms")
    for f in failures:
        print("FAIL:", f)
    if not failures:
        print("PASS")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--games", type=int, default=200)
    parser.add_argument("--players", type=int, default=3)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--roll-ms", type=int, default=5000, help="dice interval (the fastest the settings allow)")
    parser.add_argument("--think-s", type=float, default=1.0, help="each game's bots act this often")
    parser.add_argument("--max-late-p99-ms", type=float, default=250)
    args = parser.parse_args()
    setup_django()
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
