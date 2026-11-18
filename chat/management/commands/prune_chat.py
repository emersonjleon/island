"""Delete public-room messages older than CHAT["PUBLIC_RETENTION_DAYS"]. Run it daily (cron or a scheduler).

Game chats go with their game and private conversations are kept; only the public rooms,
which grow with every visitor, are trimmed.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from chat import conf
from chat.models import ChannelKind, Message


class Command(BaseCommand):
    help = "Delete public chat messages older than the retention period."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=None, help="Override CHAT['PUBLIC_RETENTION_DAYS'].")

    def handle(self, *args, days=None, **options):
        keep = conf.get("PUBLIC_RETENTION_DAYS") if days is None else days
        cutoff = timezone.now() - timedelta(days=keep)
        deleted, _ = Message.objects.filter(channel__kind=ChannelKind.PUBLIC, created_at__lt=cutoff).delete()
        self.stdout.write(f"Deleted {deleted} public chat messages older than {keep} days.")
