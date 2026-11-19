from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import TestCase, TransactionTestCase, override_settings

from accounts.models import User
from chat import codes, social
from chat.models import Channel, Friendship, Privacy
from chat.routing import websocket_urlpatterns as chat_ws
from chat.services import ChatError

TIMEOUT = 5


def make_user(name: str, display: str = "") -> User:
    return User.objects.create_user(name, f"{name}@example.com", "x", display_name=display)


def befriend(a: User, b: User) -> None:
    social.request_friend(a, b)
    social.accept_friend(b, a)


class FriendTests(TestCase):
    def setUp(self):
        self.ana, self.bo, self.cy = make_user("ana"), make_user("bo"), make_user("cy")

    def test_request_then_accept(self):
        self.assertFalse(social.request_friend(self.ana, self.bo))
        self.assertFalse(social.are_friends(self.ana.pk, self.bo.pk))
        st_a, st_b = social.state(self.ana), social.state(self.bo)
        self.assertEqual((st_a["outgoing"], st_b["incoming"]), ([{"id": self.bo.pk, "name": "bo"}], [{"id": self.ana.pk, "name": "ana"}]))
        self.assertTrue(social.accept_friend(self.bo, self.ana))
        self.assertTrue(social.are_friends(self.bo.pk, self.ana.pk))
        self.assertEqual(social.state(self.ana)["friends"], [{"id": self.bo.pk, "name": "bo"}])
        self.assertEqual(social.state(self.bo)["friends"], [{"id": self.ana.pk, "name": "ana"}])
        self.assertEqual(social.friend_ids(self.ana.pk), {self.bo.pk})

    def test_only_the_asked_person_can_accept(self):
        social.request_friend(self.ana, self.bo)
        self.assertFalse(social.accept_friend(self.ana, self.bo))
        self.assertFalse(social.are_friends(self.ana.pk, self.bo.pk))

    def test_asking_back_makes_friends(self):
        social.request_friend(self.ana, self.bo)
        self.assertTrue(social.request_friend(self.bo, self.ana))
        self.assertTrue(social.are_friends(self.ana.pk, self.bo.pk))
        self.assertEqual(Friendship.objects.count(), 1)

    def test_refuses_self_and_twice(self):
        with self.assertRaises(ChatError) as ctx:
            social.request_friend(self.ana, self.ana)
        self.assertEqual(ctx.exception.code, codes.FRIEND_SELF)
        befriend(self.ana, self.bo)
        with self.assertRaises(ChatError) as ctx:
            social.request_friend(self.bo, self.ana)
        self.assertEqual((ctx.exception.code, ctx.exception.params), (codes.FRIEND_ALREADY, {"name": "ana"}))

    def test_remove_unfriends_cancels_and_declines(self):
        befriend(self.ana, self.bo)
        self.assertTrue(social.remove_friend(self.bo, self.ana))
        self.assertFalse(social.are_friends(self.ana.pk, self.bo.pk))
        social.request_friend(self.ana, self.cy)
        self.assertTrue(social.remove_friend(self.cy, self.ana))  # declined
        self.assertEqual(social.state(self.ana)["outgoing"], [])

    def test_find_by_username_or_unique_display_name(self):
        lu = make_user("lucia", "Lu")
        self.assertEqual(social.find_user(" LUCIA ").pk, lu.pk)
        self.assertEqual(social.find_user("lu").pk, lu.pk)
        make_user("lupe", "Lu")
        with self.assertRaises(ChatError) as ctx:
            social.find_user("Lu")  # two people use that name
        self.assertEqual(ctx.exception.code, codes.NO_USER)
        with self.assertRaises(ChatError):
            social.find_user("")


class PrivacyTests(TestCase):
    def setUp(self):
        self.ana, self.bo = make_user("ana"), make_user("bo")

    def refuses(self, code, fn, *args):
        with self.assertRaises(ChatError) as ctx:
            fn(*args)
        self.assertEqual(ctx.exception.code, code)

    def test_default_is_everyone(self):
        self.assertEqual(social.privacy_of(self.ana.pk), Privacy.EVERYONE)
        room, msg = social.post_public(self.ana, " hola  a todos ")
        self.assertEqual((room, msg["name"], msg["text"]), ("general", "ana", "hola a todos"))
        dm = social.post_dm(self.ana, self.bo, "hola bo")
        self.assertEqual((dm["from"], dm["to"], dm["to_name"]), (self.ana.pk, self.bo.pk, "bo"))

    def test_refuses_unknown_setting(self):
        self.refuses(codes.BAD_PRIVACY, social.set_privacy, self.ana, "nobody")

    def test_friends_only(self):
        social.set_privacy(self.bo, Privacy.FRIENDS)
        self.refuses(codes.PUBLIC_OFF, social.post_public, self.bo, "hi")
        self.refuses(codes.DM_REFUSED, social.post_dm, self.ana, self.bo, "hi")
        self.refuses(codes.DM_FRIENDS_ONLY, social.post_dm, self.bo, self.ana, "hi")
        befriend(self.ana, self.bo)
        social.post_dm(self.ana, self.bo, "hi")
        social.post_dm(self.bo, self.ana, "hey")

    def test_games_only(self):
        befriend(self.ana, self.bo)
        social.set_privacy(self.bo, Privacy.GAMES)
        self.refuses(codes.PUBLIC_OFF, social.post_public, self.bo, "hi")
        self.refuses(codes.DM_REFUSED, social.post_dm, self.ana, self.bo, "hi")
        self.refuses(codes.DM_OFF, social.post_dm, self.bo, self.ana, "hi")
        # Friend requests are still possible: they are not messages.
        cy = make_user("cy")
        social.request_friend(cy, self.bo)

    def test_no_message_to_yourself(self):
        self.refuses(codes.NO_USER, social.post_dm, self.ana, self.ana, "hi")

    @override_settings(CHAT={"PAGE": 2})
    def test_everyone_starts_in_the_general_room(self):
        # Whatever their language, everyone meets in one room until they pick another.
        self.bo.preferred_language = "es"
        self.bo.save()
        self.assertEqual((social.room_of(self.ana), social.room_of(self.bo)), ("general", "general"))
        social.post_public(self.ana, "hello")
        social.post_public(self.bo, "hola")
        self.assertEqual([m["text"] for m in social.public_page("general")[0]], ["hello", "hola"])
        self.assertEqual(social.rooms()[0], "general")

    @override_settings(CHAT={"PAGE": 2})
    def test_language_rooms_can_be_picked_with_pages(self):
        social.set_room(self.bo, "es")
        for i in range(3):
            social.post_public(self.bo, f"p{i}")
        room, _msg = social.post_public(self.ana, "hello")
        self.assertEqual((room, social.room_of(self.bo)), ("general", "es"))
        msgs, more = social.public_page("es")
        self.assertEqual(([m["text"] for m in msgs], more), (["p1", "p2"], True))
        msgs, more = social.public_page("es", before=msgs[0]["id"])
        self.assertEqual(([m["text"] for m in msgs], more), (["p0"], False))
        self.assertEqual([m["text"] for m in social.public_page("general")[0]], ["hello"])
        social.set_room(self.bo, "general")
        self.assertEqual(social.post_public(self.bo, "hi")[0], "general")
        self.refuses(codes.BAD_ROOM, social.set_room, self.bo, "xx")

    @override_settings(CHAT={"PAGE": 2})
    def test_conversations_pages_and_unread(self):
        cy = make_user("cy")
        social.post_dm(self.ana, self.bo, "d0")
        social.post_dm(cy, self.ana, "d1")
        social.post_dm(self.bo, cy, "not ana's")
        last = social.post_dm(self.bo, self.ana, "d2")
        social.post_dm(self.bo, self.ana, "d3")
        convos = social.conversations(self.ana)
        self.assertEqual([(c["with"]["name"], c["last"]["text"], c["unread"]) for c in convos],
                         [("bo", "d3", 2), ("cy", "d1", 1)])
        self.assertEqual(social.conversations(self.bo)[0]["unread"], 0)  # your own lines are read
        person, msgs, more = social.dm_page(self.ana, self.bo.pk)
        self.assertEqual((person["name"], [m["text"] for m in msgs], more), ("bo", ["d2", "d3"], True))
        self.assertEqual([m["text"] for m in social.dm_page(self.ana, self.bo.pk, msgs[0]["id"])[1]], ["d0"])
        self.assertEqual(social.mark_read(self.ana, self.bo.pk, last["id"]), last["id"])
        self.assertEqual(social.conversations(self.ana)[0]["unread"], 1)
        self.assertIsNone(social.mark_read(self.ana, self.bo.pk, 1))  # never goes back
        self.assertEqual(social.dm_page(self.ana, cy.pk)[1][0]["text"], "d1")
        self.assertEqual(social.dm_page(self.bo, cy.pk)[1][0]["text"], "not ana's")
        self.assertEqual(social.dm_page(make_user("di"), self.bo.pk)[1:], ([], False))

    def test_refused_message_leaves_no_conversation(self):
        social.set_privacy(self.bo, Privacy.GAMES)
        self.refuses(codes.DM_REFUSED, social.post_dm, self.ana, self.bo, "hi")
        social.set_privacy(self.bo, Privacy.EVERYONE)
        self.refuses(codes.EMPTY, social.post_dm, self.ana, self.bo, "  ")
        self.assertFalse(Channel.objects.exists())
        self.assertEqual(social.conversations(self.bo), [])


class SocialSocketTests(TransactionTestCase):
    def setUp(self):
        async_to_sync(get_channel_layer().flush)()
        self.ana, self.bo = make_user("ana"), make_user("bo")

    async def open(self, user) -> WebsocketCommunicator:
        comm = WebsocketCommunicator(URLRouter(chat_ws), "/ws/social/")
        comm.scope["user"] = user
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        return comm

    async def recv(self, comm, kind: str) -> dict:
        while True:
            msg = await comm.receive_json_from(timeout=TIMEOUT)
            if msg["t"] == kind:
                return msg

    def test_anonymous_is_refused(self):
        from django.contrib.auth.models import AnonymousUser

        async def run():
            comm = WebsocketCommunicator(URLRouter(chat_ws), "/ws/social/")
            comm.scope["user"] = AnonymousUser()
            connected, _ = await comm.connect()
            self.assertFalse(connected)

        async_to_sync(run)()

    def test_public_friends_and_private_messages(self):
        async def run():
            a = await self.open(self.ana)
            b = await self.open(self.bo)
            hello = await self.recv(a, "social")
            self.assertEqual((hello["me"]["name"], hello["privacy"], hello["friends"]), ("ana", "everyone", []))
            self.assertEqual(hello["conversations"], [])
            self.assertEqual(await self.recv(a, "public"), {"t": "public", "room": "general", "msgs": [], "history": True, "more": False})
            await self.recv(b, "public")

            await a.send_json_to({"t": "say", "to": None, "text": "¿alguien juega?"})
            for comm in (a, b):
                got = await self.recv(comm, "public")
                self.assertEqual([(m["name"], m["text"]) for m in got["msgs"]], [("ana", "¿alguien juega?")])

            # A friend request by name; both people see it, then bo accepts by id.
            await a.send_json_to({"t": "friend", "op": "add", "name": "BO"})
            self.assertEqual((await self.recv(a, "social"))["outgoing"], [{"id": self.bo.pk, "name": "bo"}])
            self.assertEqual((await self.recv(b, "social"))["incoming"], [{"id": self.ana.pk, "name": "ana"}])
            await b.send_json_to({"t": "friend", "op": "accept", "id": self.ana.pk})
            self.assertEqual((await self.recv(a, "social"))["friends"], [{"id": self.bo.pk, "name": "bo"}])
            await self.recv(b, "social")

            # bo goes friends-only: no more public room, but ana (a friend) can still write.
            await b.send_json_to({"t": "privacy", "value": "friends"})
            self.assertEqual((await self.recv(b, "social"))["privacy"], "friends")
            await a.send_json_to({"t": "say", "to": None, "text": "solo para todos"})
            await self.recv(a, "public")
            await a.send_json_to({"t": "say", "to": self.bo.pk, "text": "hola amigo"})
            for comm, other in ((a, "bo"), (b, "ana")):
                got = await self.recv(comm, "dm")
                self.assertEqual(got["with"]["name"], other)
                self.assertEqual([(m["from"], m["text"]) for m in got["msgs"]], [(self.ana.pk, "hola amigo")])
            sent_id = got["msgs"][0]["id"]
            self.assertTrue(await b.receive_nothing(timeout=0.2))  # the public line never reached bo
            # bo reads it in one tab; bo's other tabs hear about it.
            b_tab = await self.open(self.bo)
            self.assertEqual((await self.recv(b_tab, "social"))["conversations"][0]["unread"], 1)
            await b.send_json_to({"t": "read", "with": self.ana.pk, "upto": sent_id})
            self.assertEqual(await self.recv(b_tab, "read"), {"t": "read", "with": self.ana.pk, "upto": sent_id})
            await b_tab.disconnect()

            # bo goes games-only: ana's message is refused.
            await b.send_json_to({"t": "privacy", "value": "games"})
            await self.recv(b, "social")
            await a.send_json_to({"t": "say", "to": self.bo.pk, "text": "¿sigues?"})
            refused = await self.recv(a, "notice")
            self.assertEqual((refused["code"], refused["params"]), (codes.DM_REFUSED, {"name": "bo"}))
            await a.disconnect()
            await b.disconnect()

            # Reconnecting lists the conversation; its lines come when it is opened.
            b2 = await self.open(self.bo)
            convo = (await self.recv(b2, "social"))["conversations"][0]
            self.assertEqual((convo["with"]["name"], convo["last"]["text"], convo["unread"]), ("ana", "hola amigo", 0))
            await b2.send_json_to({"t": "history", "with": self.ana.pk})
            history = await self.recv(b2, "dm")
            self.assertEqual(([m["text"] for m in history["msgs"]], history["more"]), (["hola amigo"], False))
            await b2.disconnect()

        async_to_sync(run)()

    def test_unknown_person_and_bad_frames(self):
        async def run():
            a = await self.open(self.ana)
            await self.recv(a, "public")
            await a.send_json_to({"t": "friend", "op": "add", "name": "nadie"})
            self.assertEqual((await self.recv(a, "notice"))["params"], {"name": "nadie"})
            await a.send_json_to({"t": "say", "to": "x", "text": "hi"})
            self.assertEqual((await self.recv(a, "notice"))["code"], codes.NO_USER)
            await a.send_json_to({"t": "say", "to": None, "text": "  "})
            self.assertEqual((await self.recv(a, "notice"))["code"], codes.EMPTY)
            await a.send_json_to(["not", "a", "dict"])
            await a.send_json_to({"t": "ping"})
            self.assertEqual(await a.receive_json_from(timeout=TIMEOUT), {"t": "pong"})
            await a.disconnect()

        async_to_sync(run)()

    @override_settings(CHAT={"BURST": 2, "RATE_PER_SECOND": 0.001})
    def test_rate_limit(self):
        async def run():
            a = await self.open(self.ana)
            await self.recv(a, "public")
            for i in range(3):
                await a.send_json_to({"t": "say", "to": None, "text": f"m{i}"})
            await self.recv(a, "public")
            await self.recv(a, "public")
            self.assertEqual((await self.recv(a, "notice"))["code"], codes.RATE_LIMITED)
            await a.disconnect()

        async_to_sync(run)()
