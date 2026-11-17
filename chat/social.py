"""The site-wide chat: a public room, friends and private messages, with a privacy setting.

Plain functions over the models; the WebSocket consumer (``chat.consumers.SocialConsumer``)
calls them. Privacy settings (see ``Privacy``):

* everyone - reads and writes the public room; anyone may send them private messages;
* friends  - no public room; private messages only to and from friends;
* games    - no public room and no private messages; only the game chats.

Friend requests are not messages, so they can be sent to anyone whatever their setting.
"""
from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from . import codes, conf
from .models import ChatSettings, Friendship, Privacy, SocialMessage
from .services import ChatError, clean_text

PUBLIC_GROUP = "social.public"


def user_group(user_id: int) -> str:
    return f"social.user.{user_id}"


def privacy_of(user_id: int) -> str:
    value = ChatSettings.objects.filter(user_id=user_id).values_list("privacy", flat=True).first()
    return value or Privacy.EVERYONE


def set_privacy(user, value: Any) -> str:
    if value not in Privacy.values:
        raise ChatError(codes.BAD_PRIVACY)
    ChatSettings.objects.update_or_create(user=user, defaults={"privacy": value})
    return value


def reads_public(user_id: int) -> bool:
    return privacy_of(user_id) == Privacy.EVERYONE


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
    """Everything the panel shows besides the messages: you, your setting, friends and requests."""
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
        "friends": sorted(friends, key=by_name),
        "incoming": sorted(incoming, key=by_name),
        "outgoing": sorted(outgoing, key=by_name),
    }


# --- messages ----------------------------------------------------------------

def to_wire(msg: SocialMessage) -> dict[str, Any]:
    return {
        "id": msg.pk,
        "from": msg.sender_id,
        "name": msg.name,
        "to": msg.recipient_id,
        "to_name": msg.recipient.public_name if msg.recipient_id else None,
        "text": msg.text,
        "at": int(msg.created_at.timestamp() * 1000),
    }


def post_public(user, text: Any) -> dict[str, Any]:
    if not reads_public(user.pk):
        raise ChatError(codes.PUBLIC_OFF)
    cleaned = clean_text(text)
    msg = SocialMessage.objects.create(sender=user, name=user.public_name[:64], text=cleaned)
    return to_wire(msg)


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


def post_dm(sender, recipient, text: Any) -> dict[str, Any]:
    check_dm(sender, recipient)
    cleaned = clean_text(text)
    msg = SocialMessage.objects.create(sender=sender, recipient=recipient, name=sender.public_name[:64], text=cleaned)
    return to_wire(msg)


def public_history(limit: int | None = None) -> list[dict[str, Any]]:
    n = conf.get("PUBLIC_HISTORY") if limit is None else limit
    latest = list(SocialMessage.objects.filter(recipient__isnull=True).order_by("-id")[:n])
    return [to_wire(m) for m in reversed(latest)]


def dm_history(user, limit: int | None = None) -> list[dict[str, Any]]:
    """The latest private messages to or from ``user``, every conversation together, oldest first."""
    n = conf.get("DM_HISTORY") if limit is None else limit
    latest = list(
        SocialMessage.objects.filter(Q(sender=user, recipient__isnull=False) | Q(recipient=user))
        .select_related("recipient").order_by("-id")[:n]
    )
    return [to_wire(m) for m in reversed(latest)]
