# Chat: how it is organised and how it grows

Every conversation on the site is a **channel** with **messages**. The kinds differ only in
who may read and write, never in how lines are stored, paged or cleaned up.

| Kind | Key | Who | Where it is shown | Lifetime |
|---|---|---|---|---|
| `public` | `public:general`, `public:<lang>` | everyone whose privacy is *Everyone*, in that room (the general one until they pick a language room) | lobby panel, "Public" tab | pruned after `PUBLIC_RETENTION_DAYS` |
| `game` | `game:<game id>` | players and watchers of that game | waiting room and game page | deleted with the game |
| `direct` | `dm:<low id>:<high id>` | the two people (a `Membership` each) | lobby panel, "Messages" tab | kept |

Models (`chat/models.py`): `Channel(kind, key, game?, last_message_id)`,
`Message(channel, sender, name, colour, seat, text, created_at)` indexed by `(channel, id)`,
`Membership(channel, user, last_read_id)`, plus `Friendship` and `ChatSettings(privacy, room)`.

## Sockets

* Waiting room and game: the page's own socket (`/ws/lobby/<code>/`, `/ws/play/<code>/`) carries
  `{"t": "chat"}` frames through `ChatMixin`; one group per game channel (`chat.game.<id>`).
* Site-wide: `/ws/social/` (`SocialConsumer`). It joins two groups: the person's own
  (`social.user.<id>`: private lines, friend changes, "read" marks for their other tabs) and the
  public room they are in (`chat.public.general` unless they picked a language room such as
  `chat.public.es`), only if their privacy allows it.

Nothing is sent in bulk on connect: the state frame lists friends, requests and the latest
`CONVERSATIONS` private conversations (who, last line, unread count from `last_read_id`); the
public room sends one `PAGE` of lines; each private conversation sends its lines a page at a time
when it is opened (`{"t": "history", "with": id, "before": msg_id}`).

## Privacy

*Everyone* (public room and private messages from anyone), *Only friends* (no public room; private
messages only with friends), *Only in games* (no public room and no private messages). Game chats
always work. Friend requests are not messages and are always allowed.
The rules live in `chat/social.py` (`check_dm`, `reads_public`); every write goes through them.

## Why this shape scales

* **One table, one index.** All history reads are `WHERE channel_id = ? AND id < ? ORDER BY id DESC
  LIMIT n` on `(channel, id)`, whatever the kind; cost does not grow with the table.
* **No fan-out to everyone.** A line goes to one group: a game's players, one public room, or two
  people. Everyone starts in the general room; rooms per language are there for people who
  want them, and the shards below split a room that gets too busy.
* **Unread counts on the server** (`Membership.last_read_id`), so badges follow a person across tabs
  and devices, and opening the panel does not download every private message.
* **Bounded growth.** Public rooms are pruned (`manage.py prune_chat`, run daily); game chats leave
  with their game; `CONVERSATIONS` and `PAGE` cap what any one connection loads.
* **Rate limits per connection** (`RATE_PER_SECOND`, `BURST`) on every write.

## Next steps when the numbers call for them

1. **Room shards.** When a public room is too busy to read, split it (`public:es:1`,
   `public:es:2`, ...) and assign people by load; the key format already allows it.
2. **Presence.** "Online" for friends from a Redis set per user with a TTL refreshed by the socket's
   ping; announce changes to friends' `social.user.<id>` groups.
3. **Blocking and reports.** A `Block(user, blocked)` table checked in `check_dm` and filtered from
   the public room for the person who blocked; a report button that stores the message id.
   Moderators already see every channel in the admin.
4. **One socket per page.** The lobby list opens `/ws/social/`; the waiting room and game pages could
   carry the same social frames over their sockets (as `ChatMixin` does for game chat) instead of a
   second connection.
5. **More channel kinds** (clubs, tournament rooms, a party before a game) are a new `kind` plus
   memberships; storage, paging, unread counts and pruning come for free.
6. **Storage.** At very large volume, partition `Message` by time or move old private history to
   cold storage; the API (`page()`) does not change.
