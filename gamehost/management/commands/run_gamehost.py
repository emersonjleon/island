import asyncio
import logging
import signal

from django.core.management.base import BaseCommand

from gamehost.runner import GameHost


class Command(BaseCommand):
    help = "Run the game host: owns live games, fires the dice clock and persists commands."

    def handle(self, *args, **options):
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        asyncio.run(self._main())

    async def _main(self):
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        self.stdout.write("game host running (Ctrl-C to stop)")
        await GameHost().serve(stop)
        self.stdout.write("game host stopped; games snapshotted")
