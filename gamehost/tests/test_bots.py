import asyncio

from asgiref.sync import async_to_sync
from channels.layers import InMemoryChannelLayer
from django.test import TestCase, TransactionTestCase, override_settings

from accounts.models import User
from gamehost import store
from gamehost.clock import ManualClock
from gamehost.leases import LocalLeases
from gamehost.models import GameCommand
from gamehost.runner import GameHost
from lobby import services
from lobby.models import Game

TIMEOUT = 5
STEP_MS = 100
MAX_MS = 3 * 3600 * 1000


def game_with_bots(levels: list[str], overrides: dict | None = None) -> tuple[Game, User]:
    host = User.objects.create_user("ana", "ana@example.com", "x")
    game = services.create_game(host, "classic", {"players": {"max": len(levels) + 1}, **(overrides or {})})
    for level in levels:
        services.add_bot(game, host, level)
    return services.start_game(game, host), host


class BotCoreTests(TestCase):
    def test_seats_and_drivers(self):
        game, host = game_with_bots(["easy", "hard"])
        seats = store.seats_for(game)
        bots = {p.seat: p for p in game.players.filter(user=None)}
        for info in seats:
            if info.seat in bots:
                self.assertIsNone(info.user_id)
                self.assertEqual(info.name, f"{bots[info.seat].bot_name} (bot)")
            else:
                self.assertEqual(info.user_id, host.pk)
        driver = store.bots_for(game, 0)
        self.assertEqual(sorted(b.seat for b in driver.bots), sorted(bots))
        self.assertEqual({b.seat: b.level.name for b in driver.bots}, {s: p.bot_level for s, p in bots.items()})

    def test_bots_play_a_whole_game_while_the_person_idles(self):
        game, _host = game_with_bots(["hard"], {"victory": {"target": 6}})
        core = store.create_core(game)
        bot_seat = core.bots.bots[0].seat
        now = 0
        while not core.finished and now < MAX_MS:
            core.advance(now)
            core.bots_act(now)
            now += STEP_MS
        self.assertTrue(core.finished)
        self.assertEqual(core.state.winner, bot_seat)
        self.assertGreater(core.cmd_seq, 0)
        self.assertEqual({rec.seat for _n, rec in core.pending}, {bot_seat})

    def test_next_wakeup_includes_bot_decisions(self):
        game, _host = game_with_bots(["easy"])
        core = store.create_core(game)
        self.assertEqual(core.next_wakeup(), min(core.bots.next_ms.values()))


@override_settings(GAMEHOST_FLUSH_MS=0, GAMEHOST_MAX_IDLE_MS=20, GAMEHOST_SNAPSHOT_EVERY_ROLLS=0)
class BotHostTests(TransactionTestCase):
    def test_bots_act_in_the_live_runner_and_come_back_after_restore(self):
        layer = InMemoryChannelLayer()
        clocks: list[ManualClock] = []

        def clock(start):
            c = ManualClock(start)
            clocks.append(c)
            return c

        game, _host = game_with_bots(["medium", "hard"])

        async def settle(runner):
            async def caught_up():
                while runner.core.state.now_ms < runner.clock.now() and not runner.core.finished:
                    await asyncio.sleep(0.005)
            await asyncio.wait_for(caught_up(), TIMEOUT)

        async def run():
            host = GameHost(layer=layer, leases=LocalLeases(), clock_factory=clock)
            await host.dispatch({"type": "game.start", "game_id": game.pk})
            runner = host.runners[game.pk]
            for _ in range(20):
                clocks[-1].advance(500)
                await settle(runner)
            await asyncio.sleep(0.05)
            accepted = runner.core.cmd_seq
            await host.shutdown()

            host2 = GameHost(layer=layer, leases=LocalLeases(), clock_factory=clock)
            await host2.scan()
            restored = len(host2.runners[game.pk].core.bots.bots)
            await host2.shutdown()
            return accepted, restored

        accepted, restored = async_to_sync(run)()
        self.assertGreater(accepted, 0)
        self.assertEqual(restored, 2)
        bot_seats = set(game.players.filter(user=None).values_list("seat", flat=True))
        self.assertEqual(set(GameCommand.objects.filter(game=game).values_list("seat", flat=True)), bot_seats)
