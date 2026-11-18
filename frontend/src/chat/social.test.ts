import { describe, expect, it } from "vitest";

import { parseSocialFrame, SocialStore, type SocialFrame, type SocialMessage } from "./social";

const me = { id: 1, name: "ana" };
const bo = { id: 2, name: "bo" };
const cy = { id: 3, name: "cy" };
const msg = (id: number, from: number, text = `m${id}`): SocialMessage =>
  ({ id, from, name: from === 1 ? "ana" : from === 2 ? "bo" : "cy", text, at: id });
const hello = (extra: Record<string, unknown> = {}): SocialFrame => parseSocialFrame({
  t: "social", me, privacy: "everyone", room: "es", rooms: ["en", "es"], friends: [], incoming: [], outgoing: [],
  conversations: [], ...extra,
})!;

function storeWithSends(): { store: SocialStore; sent: object[] } {
  const sent: object[] = [];
  const store = new SocialStore((f) => { sent.push(f); return true; });
  return { store, sent };
}

describe("social chat model", () => {
  it("parses frames and drops the rest", () => {
    expect(hello()).toMatchObject({ t: "social", me, privacy: "everyone", room: "es", rooms: ["en", "es"] });
    expect(parseSocialFrame({ t: "social", me, privacy: "nobody" })).toBeNull();
    expect(parseSocialFrame({ t: "social", me, privacy: "friends", friends: [bo, { id: "x" }],
                              conversations: [{ with: bo, last: msg(4, 2), unread: 1 }, { with: bo }] }))
      .toMatchObject({ friends: [bo], incoming: [], conversations: [{ with: bo, last: msg(4, 2), unread: 1 }] });
    expect(parseSocialFrame({ t: "dm", with: bo, msgs: [msg(1, 1), { id: 2 }], history: true, more: true }))
      .toEqual({ t: "dm", with: bo, msgs: [msg(1, 1)], history: true, more: true });
    expect(parseSocialFrame({ t: "dm", msgs: [] })).toBeNull();
    expect(parseSocialFrame({ t: "public", room: "es", msgs: [msg(3, 2)], history: false }))
      .toEqual({ t: "public", room: "es", msgs: [msg(3, 2)], history: false, more: false });
    expect(parseSocialFrame({ t: "read", with: 2, upto: 9 })).toEqual({ t: "read", with: 2, upto: 9 });
    expect(parseSocialFrame({ t: "notice", code: "chat.no_user", params: { name: "x" } }))
      .toEqual({ t: "notice", code: "chat.no_user", params: { name: "x" } });
    expect(parseSocialFrame({ t: "changed" })).toBeNull();
    expect(parseSocialFrame(null)).toBeNull();
  });

  it("lists conversations from the state and loads one when it is opened", () => {
    const { store, sent } = storeWithSends();
    store.receive(hello({ conversations: [{ with: cy, last: msg(9, 3), unread: 2 }, { with: bo, last: msg(5, 1), unread: 0 }] }));
    expect(store.sortedConversations().map((c) => [c.with.name, c.unread])).toEqual([["cy", 2], ["bo", 0]]);
    expect(store.attention()).toBe(2);
    store.open(3);
    expect(sent).toEqual([{ t: "history", with: 3 }, { t: "read", with: 3, upto: 9 }]);
    expect(store.unreadMessages()).toBe(0);
    store.receive({ t: "dm", with: cy, msgs: [msg(8, 1), msg(9, 3)], history: true, more: true });
    const convo = store.conversations.get(3)!;
    expect([convo.loaded, convo.more, convo.log.lines.map((l) => l.text)]).toEqual([true, true, ["m8", "m9"]]);
    store.loadOlder(3);
    expect(sent.at(-1)).toEqual({ t: "history", with: 3, before: 8 });
    store.receive({ t: "dm", with: cy, msgs: [msg(7, 3)], history: true, more: false });
    expect([convo.more, convo.log.lines.map((l) => l.id)]).toEqual([false, [7, 8, 9]]);
  });

  it("counts new lines as unread unless that conversation is on screen", () => {
    const { store, sent } = storeWithSends();
    store.receive(hello({ incoming: [{ id: 4, name: "di" }] }));
    store.receive({ t: "dm", with: bo, msgs: [msg(5, 2)], history: false, more: false });
    store.receive({ t: "dm", with: cy, msgs: [msg(6, 1)], history: false, more: false });  // one I wrote
    expect([store.unreadMessages(), store.attention()]).toEqual([1, 2]);
    store.open(2);
    store.receive({ t: "dm", with: bo, msgs: [msg(7, 2)], history: false, more: false });
    expect(store.unreadMessages()).toBe(0);
    expect(sent.filter((f) => (f as { t: string }).t === "read").at(-1)).toEqual({ t: "read", with: 2, upto: 7 });
    store.open(null);
    store.receive({ t: "dm", with: bo, msgs: [msg(8, 2)], history: false, more: false });
    expect(store.unreadMessages()).toBe(1);
    store.receive({ t: "read", with: 2, upto: 8 });  // read in another tab
    expect(store.unreadMessages()).toBe(0);
    expect(store.isPending(4)).toBe(true);
  });

  it("keeps the public room's lines and starts over when the room changes", () => {
    const { store, sent } = storeWithSends();
    store.receive(hello());
    store.receive({ t: "public", room: "es", msgs: [msg(7, 2)], history: true, more: true });
    store.receive({ t: "public", room: "es", msgs: [msg(8, 3)], history: false, more: false });
    expect(store.publicLog.lines).toMatchObject([{ id: 7, uid: 2, name: "bo" }, { id: 8 }]);
    store.loadOlder(null);
    expect(sent.at(-1)).toEqual({ t: "history", with: null, before: 7 });
    store.receive(hello({ room: "en" }));
    expect(store.publicLog.lines).toEqual([]);
    store.receive({ t: "public", room: "es", msgs: [msg(9, 2)], history: false, more: false });  // late line from the old room
    expect(store.publicLog.lines).toEqual([]);
    store.receive({ t: "public", room: "en", msgs: [msg(10, 2)], history: true, more: false });
    expect(store.publicRoom.room).toBe("en");
    expect(store.publicLog.lines.map((l) => l.id)).toEqual([10]);
  });

  it("keeps a refusal until the next message arrives", () => {
    const { store } = storeWithSends();
    store.receive(hello());
    store.receive({ t: "notice", code: "chat.dm_refused", params: { name: "bo" } });
    expect(store.error).toEqual({ code: "chat.dm_refused", params: { name: "bo" } });
    store.receive({ t: "dm", with: cy, msgs: [msg(8, 1)], history: false, more: false });
    expect(store.error).toBeNull();
  });
});
