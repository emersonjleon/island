"""The site-wide chat: public rooms, friends and private messages, with a privacy setting.

Plain functions over the models; the WebSocket consumer (``chat.consumers.SocialConsumer``)
calls them. Privacy settings (see ``Privacy``):

* everyone - reads and writes the public room; anyone may send them private messages;
* friends  - no public room; private messages only to and from friends;
* games    - no public room and no private messages; only the game chats.

Friend requests are not messages, so they can be sent to anyone whatever their setting.
Everyone starts in the one general public room ("public:general"); a room per language
("public:es") can be picked afterwards. Private conversations are "dm:<a>:<b>"
channels whose two memberships keep what each person has read.
"""
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, F, Q

from . import codes, conf
from .models import Channel, ChannelKind, ChatSettings, Friendship, Membership, Message, Privacy
from .services import ChatError, channel_group, get_channel, page, write


def user_group(user_id: int) -> str:
    """Every open site-wide chat of one person (private messages, friend changes)."""
    return f"social.user.{user_id}"


def _settings(user_id: int) -> dict[str, str]:
    row = ChatSettings.objects.filter(user_id=user_id).values("privacy", "room").first()
    return row or {"privacy": Privacy.EVERYONE, "room": ""}


def privacy_of(user_id: int) -> str:
    return _settings(user_id)["privacy"]


def set_privacy(user, value: Any) -> str:
    if value not in Privacy.values:
        raise ChatError(codes.BAD_PRIVACY)
    ChatSettings.objects.update_or_create(user=user, defaults={"privacy": value})
    return value


def reads_public(user_id: int) -> bool:
    return privacy_of(user_id) == Privacy.EVERYONE


# --- public rooms ----------------------------------------------------------------

GENERAL = "general"


def rooms() -> list[str]:
    """The general room everyone starts in, then one room per site language."""
    return [GENERAL, *(code for code, _name in settings.LANGUAGES)]


def room_of(user) -> str:
    """The room picked in the settings; the general room until one is picked."""
    chosen = _settings(user.pk)["room"]
    return chosen if chosen in rooms() else GENERAL


def set_room(user, value: Any) -> str:
    if value not in rooms():
        raise ChatError(codes.BAD_ROOM)
    ChatSettings.objects.update_or_create(user=user, defaults={"room": value})
    return value


def public_key(room: str) -> str:
    return f"public:{room}"


def public_group(room: str) -> str:
    return channel_group(public_key(room))


# --- friends -----------------------------------------------------------------

def _person(user) -> dict[str, Any]:
    return {"id": user.pk, "name": user.public_name}


def are_friends(a_id: int, b_id: int) -> bool:
    return Friendship.objects.filter(
        Q(from_user_id=a_id, to_user_id=b_id) | Q(from_user_id=b_id, to_user_id=a_id), accepted=True,
    ).exists()


def friend_ids(user_id: int) -> set[int]:
    rows = Friendship.objects.filter(Q(from_user_id=user_id) | Q(to_user_id=user_id), accepted=True)
    return {r.to_user_id if r.from_user_id == user_id else r.from_user_id for r in rows}


def find_user(name: Any):
    """A user by username, else by display name when exactly one person has it (case does not matter)."""
    User = get_user_model()
    clean = name.strip() if isinstance(name, str) else ""
    if not clean:
        raise ChatError(codes.NO_USER, {"name": ""})
    user = User.objects.filter(username__iexact=clean, is_active=True).first()
    if user is None:
        named = list(User.objects.filter(display_name__iexact=clean, is_active=True)[:2])
        user = named[0] if len(named) == 1 else None
    if user is None:
        raise ChatError(codes.NO_USER, {"name": clean[:40]})
    return user


def get_user(user_id: Any):
    User = get_user_model()
    user = User.objects.filter(pk=user_id, is_active=True).first() if isinstance(user_id, int) else None
    if user is None:
        raise ChatError(codes.NO_USER, {"name": ""})
    return user


@transaction.atomic
def request_friend(user, other) -> bool:
    """Ask ``other`` to be friends. Returns True when that made them friends (they had asked first)."""
    if other.pk == user.pk:
        raise ChatError(codes.FRIEND_SELF)
    if are_friends(user.pk, other.pk):
        raise ChatError(codes.FRIEND_ALREADY, {"name": other.public_name})
    if Friendship.objects.filter(from_user=other, to_user=user).update(accepted=True):
        Friendship.objects.filter(from_user=user, to_user=other).delete()
        return True
    Friendship.objects.get_or_create(from_user=user, to_user=other)
    return False


def accept_friend(user, other) -> bool:
    return bool(Friendship.objects.filter(from_user=other, to_user=user, accepted=False).update(accepted=True))


def remove_friend(user, other) -> bool:
    """Unfriend, cancel a request you sent or decline one you got: whatever links the two goes."""
    deleted, _ = Friendship.objects.filter(
        Q(from_user=user, to_user=other) | Q(from_user=other, to_user=user)
    ).delete()
    return bool(deleted)


def state(user) -> dict[str, Any]:
    """Everything the panel shows besides message lines: you, your settings, friends, requests, conversations."""
    rows = Friendship.objects.filter(Q(from_user=user) | Q(to_user=user)).select_related("from_user", "to_user")
    friends, incoming, outgoing = [], [], []
    for r in rows:
        if r.accepted:
            friends.append(_person(r.to_user if r.from_user_id == user.pk else r.from_user))
        elif r.to_user_id == user.pk:
            incoming.append(_person(r.from_user))
        else:
            outgoing.append(_person(r.to_user))
    by_name = lambda p: p["name"].lower()  # noqa: E731
    return {
        "t": "social",
        "me": _person(user),
        "privacy": privacy_of(user.pk),
        "room": room_of(user),
        "rooms": rooms(),
        "friends": sorted(friends, key=by_name),
        "incoming": sorted(incoming, key=by_name),
        "outgoing": sorted(outgoing, key=by_name),
        "conversations": conversations(user),
    }


# --- messages ----------------------------------------------------------------

def to_wire(msg: Message) -> dict[str, Any]:
    return {"id": msg.pk, "from": msg.sender_id, "name": msg.name, "text": msg.text,
            "at": int(msg.created_at.timestamp() * 1000)}


def post_public(user, text: Any) -> tuple[str, dict[str, Any]]:
    """Write in the person's public room; returns the room and the message as sent to clients."""
    if not reads_public(user.pk):
        raise ChatError(codes.PUBLIC_OFF)
    room = room_of(user)
    channel = get_channel(public_key(room), ChannelKind.PUBLIC)
    return room, to_wire(write(channel, user, text))


def public_page(room: str, before: Any = None) -> tuple[list[dict[str, Any]], bool]:
    channel_id = Channel.objects.filter(key=public_key(room)).values_list("pk", flat=True).first()
    msgs, more = page(channel_id, before)
    return [to_wire(m) for m in msgs], more


def dm_key(a_id: int, b_id: int) -> str:
    low, high = sorted((a_id, b_id))
    return f"dm:{low}:{high}"


def check_dm(sender, recipient) -> None:
    """Raise unless ``sender`` may write privately to ``recipient`` under both people's settings."""
    if recipient.pk == sender.pk:
        raise ChatError(codes.NO_USER, {"name": recipient.public_name})
    mine = privacy_of(sender.pk)
    theirs = privacy_of(recipient.pk)
    if mine == Privacy.GAMES:
        raise ChatError(codes.DM_OFF)
    friends = None
    if mine == Privacy.FRIENDS:
        friends = are_friends(sender.pk, recipient.pk)
        if not friends:
            raise ChatError(codes.DM_FRIENDS_ONLY)
    if theirs == Privacy.GAMES or (
        theirs == Privacy.FRIENDS and not (friends if friends is not None else are_friends(sender.pk, recipient.pk))
    ):
        raise ChatError(codes.DM_REFUSED, {"name": recipient.public_name})


@transaction.atomic
def post_dm(sender, recipient, text: Any) -> dict[str, Any]:
    """Write privately; returns the message with ``to``/``to_name`` so both people can file it."""
    check_dm(sender, recipient)
    channel = get_channel(dm_key(sender.pk, recipient.pk), ChannelKind.DIRECT)
    msg = write(channel, sender, text)
    Membership.objects.get_or_create(channel=channel, user=recipient)
    mine, _ = Membership.objects.get_or_create(channel=channel, user=sender)
    Membership.objects.filter(pk=mine.pk).update(last_read_id=msg.pk)  # your own message is read
    return {**to_wire(msg), "to": recipient.pk, "to_name": recipient.public_name}


def dm_page(user, other_id: Any, before: Any = None) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    """A page of the conversation between ``user`` and someone else: (that person, messages, more)."""
    other = get_user(other_id)
    channel_id = Channel.objects.filter(key=dm_key(user.pk, other.pk)).values_list("pk", flat=True).first()
    msgs, more = page(channel_id, before)
    return _person(other), [to_wire(m) for m in msgs], more


def mark_read(user, other_id: Any, upto: Any) -> int | None:
    """Everything up to message id ``upto`` in the conversation with ``other_id`` is read. Returns the new mark."""
    if not isinstance(other_id, int) or not isinstance(upto, int):
        return None
    updated = Membership.objects.filter(
        channel__key=dm_key(user.pk, other_id), user=user, last_read_id__lt=upto,
    ).update(last_read_id=upto)
    return upto if updated else None


def conversations(user) -> list[dict[str, Any]]:
    """The latest private conversations: who with, the last message and how many are unread."""
    mine = list(
        Membership.objects.filter(user=user, channel__kind=ChannelKind.DIRECT, channel__last_message_id__isnull=False)
        .annotate(unread=Count("channel__messages", filter=Q(channel__messages__id__gt=F("last_read_id"))
                               & ~Q(channel__messages__sender=user)))
        .select_related("channel").order_by("-channel__last_message_id")[: conf.get("CONVERSATIONS")]
    )
    ids = [m.channel_id for m in mine]
    others = {
        m.channel_id: m.user
        for m in Membership.objects.filter(channel_id__in=ids).exclude(user=user).select_related("user")
    }
    last = {m.pk: m for m in Message.objects.filter(pk__in=[m.channel.last_message_id for m in mine])}
    out = []
    for m in mine:
        other = others.get(m.channel_id)
        msg = last.get(m.channel.last_message_id)
        if other is None or msg is None:
            continue
        out.append({"with": _person(other), "last": to_wire(msg), "unread": m.unread})
    return out
