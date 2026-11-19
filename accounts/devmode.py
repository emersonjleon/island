"""Developer panel: who is registered and what is happening on the platform.

Only the usernames in ``settings.DEVELOPER_USERNAMES`` can open it; everyone else gets a 404,
so the page does not reveal that it exists. Everything here is read-only.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Max, Q, QuerySet
from django.db.models.expressions import OrderBy
from django.db.models.functions import TruncDate
from django.http import Http404, HttpRequest
from django.utils import timezone

from chat.models import Channel, ChannelKind, ChatSettings, Friendship, Message, Privacy
from lobby.models import BOT_LEVELS, Game, GamePlayer, GameStatus, SavedSettings
from lobby.presets import preset_label

from .models import User

CHART_DAYS = 14
RECENT_GAMES = 20
RECENT_USERS = 10
TOP_PLAYERS = 10
USERS_PER_PAGE = 50

# Sort keys the users table accepts, mapped to ORM orderings.
USER_SORTS = {
    "joined": "-date_joined",
    "login": "-last_login",
    "games": "-games",
    "wins": "-wins",
    "messages": "-messages",
    "name": "username",
}
DEFAULT_USER_SORT = "joined"


def developer_required(view):
    """Logged-in developers only; a 404 for anyone else."""

    @login_required
    @wraps(view)
    def wrapper(request: HttpRequest, *args, **kwargs):
        if not request.user.is_developer:
            raise Http404
        return view(request, *args, **kwargs)

    return wrapper


@dataclass
class DayCount:
    day: date
    count: int
    percent: int  # bar width relative to the busiest day, 0..100


def _counted(rows) -> list[tuple[str, int]]:
    """(value, count) rows, biggest first."""
    return sorted(((value, n) for value, n in rows), key=lambda row: (-row[1], str(row[0])))


def _labelled(rows, labels: dict) -> list[tuple[str, int]]:
    return [(labels.get(value, value), n) for value, n in _counted(rows)]


def _since(now: datetime, days: int) -> datetime:
    return now - timedelta(days=days)


def user_stats(now: datetime) -> dict:
    users = User.objects.all()
    played = GamePlayer.objects.filter(user__isnull=False).values("user").distinct()
    return {
        "total": users.count(),
        "new_7d": users.filter(date_joined__gte=_since(now, 7)).count(),
        "new_30d": users.filter(date_joined__gte=_since(now, 30)).count(),
        "active_24h": users.filter(last_login__gte=_since(now, 1)).count(),
        "active_7d": users.filter(last_login__gte=_since(now, 7)).count(),
        "active_30d": users.filter(last_login__gte=_since(now, 30)).count(),
        "never_played": users.exclude(pk__in=played).count(),
        "languages": _labelled(users.values_list("preferred_language").annotate(n=Count("id")),
                               dict(settings.LANGUAGES)),
    }


def _minutes(games: QuerySet) -> list[int]:
    spans = games.filter(started_at__isnull=False, finished_at__isnull=False).values_list("started_at", "finished_at")
    return [int((end - start).total_seconds()) // 60 for start, end in spans if end >= start]


def game_stats(now: datetime) -> dict:
    games = Game.objects.all()
    by_status = dict(games.values_list("status").annotate(n=Count("id")))
    statuses = [(label, by_status.get(value, 0)) for value, label in GameStatus.choices]
    durations = _minutes(games.filter(status=GameStatus.FINISHED))
    seats = GamePlayer.objects.all()
    running = seats.filter(game__status=GameStatus.RUNNING)
    return {
        "total": games.count(),
        "statuses": statuses,
        "created_24h": games.filter(created_at__gte=_since(now, 1)).count(),
        "created_7d": games.filter(created_at__gte=_since(now, 7)).count(),
        "finished": by_status.get(GameStatus.FINISHED, 0),
        "running": by_status.get(GameStatus.RUNNING, 0),
        "waiting": by_status.get(GameStatus.LOBBY, 0),
        "playing_now": running.filter(user__isnull=False).values("user").distinct().count(),
        "avg_minutes": sum(durations) // len(durations) if durations else None,
        "longest_minutes": max(durations) if durations else None,
        "human_seats": seats.filter(user__isnull=False).count(),
        "bot_seats": seats.filter(user__isnull=True).count(),
        "bot_levels": _labelled(seats.filter(user__isnull=True).values_list("bot_level").annotate(n=Count("id")),
                                dict(BOT_LEVELS)),
        "presets": [(preset_label(name), n) for name, n in _counted(games.values_list("preset").annotate(n=Count("id")))],
        "saved_settings": SavedSettings.objects.count(),
    }


def games_per_day(now: datetime, days: int = CHART_DAYS) -> list[DayCount]:
    first = (now - timedelta(days=days - 1)).date()
    rows = (Game.objects.filter(created_at__date__gte=first).annotate(day=TruncDate("created_at"))
            .values("day").annotate(n=Count("id")))
    counts = {row["day"]: row["n"] for row in rows}
    series = [(first + timedelta(days=i), counts.get(first + timedelta(days=i), 0)) for i in range(days)]
    busiest = max((n for _, n in series), default=0) or 1
    return [DayCount(day, n, n * 100 // busiest) for day, n in series]


def chat_stats(now: datetime) -> dict:
    messages = Message.objects.all()
    by_kind = dict(messages.values_list("channel__kind").annotate(n=Count("id")))
    privacy = _labelled(ChatSettings.objects.values_list("privacy").annotate(n=Count("user")), dict(Privacy.choices))
    return {
        "total": messages.count(),
        "last_24h": messages.filter(created_at__gte=_since(now, 1)).count(),
        "last_7d": messages.filter(created_at__gte=_since(now, 7)).count(),
        "kinds": [(label, by_kind.get(value, 0)) for value, label in ChannelKind.choices],
        "conversations": Channel.objects.filter(kind=ChannelKind.DIRECT).count(),
        "public_rooms": Channel.objects.filter(kind=ChannelKind.PUBLIC).count(),
        "writers_7d": messages.filter(created_at__gte=_since(now, 7), sender__isnull=False)
        .values("sender").distinct().count(),
        "friends": Friendship.objects.filter(accepted=True).count(),
        "friend_requests": Friendship.objects.filter(accepted=False).count(),
        "privacy": privacy,
    }


def annotated_users() -> QuerySet:
    return User.objects.annotate(
        games=Count("game_seats", distinct=True),
        wins=Count("game_seats", filter=Q(game_seats__is_winner=True), distinct=True),
        hosted=Count("hosted_games", distinct=True),
        messages=Count("chat_messages", distinct=True),
        last_game=Max("game_seats__joined_at"),
    )


def user_table(query: str, sort: str) -> QuerySet:
    users = annotated_users()
    if query:
        users = users.filter(Q(username__icontains=query) | Q(display_name__icontains=query)
                             | Q(email__icontains=query))
    ordering = USER_SORTS.get(sort, USER_SORTS[DEFAULT_USER_SORT])
    return users.order_by(_nulls_last(ordering), "-id")


def _nulls_last(ordering: str) -> OrderBy:
    """Order by one field, with empty values (never logged in) at the end either way."""
    expr = F(ordering.lstrip("-"))
    return expr.desc(nulls_last=True) if ordering.startswith("-") else expr.asc(nulls_last=True)


def top_players(limit: int = TOP_PLAYERS) -> list:
    return list(annotated_users().filter(games__gt=0).order_by("-wins", "-games", "username")[:limit])


def recent_games(limit: int = RECENT_GAMES) -> list[Game]:
    return list(Game.objects.select_related("host").prefetch_related("players__user")
                .annotate(seat_count=Count("players"))[:limit])


def recent_users(limit: int = RECENT_USERS) -> list:
    return list(annotated_users().order_by("-date_joined")[:limit])


def overview(now: datetime | None = None) -> dict:
    now = now or timezone.now()
    return {
        "now": now,
        "users": user_stats(now),
        "games": game_stats(now),
        "per_day": games_per_day(now),
        "chat": chat_stats(now),
        "top_players": top_players(),
        "recent_games": recent_games(),
        "recent_users": recent_users(),
    }
