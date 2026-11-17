import { describe, expect, it } from "vitest";

import { parseSocialFrame, SocialStore, type SocialFrame, type SocialMessage } from "./social";

const me = { id: 1, name: "ana" };
const hello = (extra: Partial<Record<string, unknown>> = {}): SocialFrame =>
  parseSocialFrame({ t: "social", me, privacy: "everyone", friends: [], incoming: [], outgoing: [], ...extra })!;
const dm = (id: number, from: number, to: number, text = `m${id}`): SocialMessage => ({
  id, from, to, text, at: id, name: from === 1 ? "ana" : from === 2 ? "bo" : "cy", to_name: to === 1 ? "ana" : to === 2 ? "bo" : "cy",
});

describe("social chat model", () => {
  it("parses frames and drops the rest", () => {
    expect(hello()).toMatchObject({ t: "social", me, privacy: "everyone" });
    expect(parseSocialFrame({ t: "social", me, privacy: "nobody" })).toBeNull();
    expect(parseSocialFrame({ t: "social", me, privacy: "friends", friends: [{ id: 2, name: "bo" }, { id: "x" }] }))
      .toMatchObject({ friends: [{ id: 2, name: "bo" }], incoming: [] });
    expect(parseSocialFrame({ t: "dm", msgs: [dm(1, 1, 2), { id: 2 }], history: true }))
      .toEqual({ t: "dm", msgs: [dm(1, 1, 2)], history: true });
    expect(parseSocialFrame({ t: "notice", code: "chat.no_user", params: { name: "x" } }))
      .toEqual({ t: "notice", code: "chat.no_user", params: { name: "x" } });
    expect(parseSocialFrame({ t: "changed" })).toBeNull();
    expect(parseSocialFrame(null)).toBeNull();
  });

  it("files private messages by the other person, even if they come before the state", () => {
    const store = new SocialStore();
    store.receive({ t: "dm", msgs: [dm(1, 1, 2, "hola bo"), dm(2, 3, 1, "hola ana")], history: true });
    expect(store.conversations.size).toBe(0);
    store.receive(hello());
    expect(store.sortedConversations().map((c) => c.with)).toEqual([{ id: 3, name: "cy" }, { id: 2, name: "bo" }]);
    expect(store.conversations.get(2)!.log.lines.map((l) => [l.uid, l.text])).toEqual([[1, "hola bo"]]);
    expect(store.attention()).toBe(0);  // history is never unread
  });

  it("counts unread private messages and friend requests", () => {
    const store = new SocialStore();
    store.receive(hello({ incoming: [{ id: 4, name: "di" }] }));
    store.receive({ t: "dm", msgs: [dm(5, 2, 1)], history: false });
    expect(store.attention()).toBe(2);
    store.conversations.get(2)!.log.setOpen(true);
    expect(store.attention()).toBe(1);
    expect(store.isPending(4)).toBe(true);
    expect(store.isFriend(4)).toBe(false);
  });

  it("puts public lines in the public log with their writer's id", () => {
    const store = new SocialStore();
    store.receive({ t: "public", msgs: [{ ...dm(7, 2, 0), to: null, to_name: null }], history: false });
    expect(store.publicLog.lines).toMatchObject([{ id: 7, uid: 2, name: "bo", text: "m7" }]);
  });

  it("keeps a refusal until the next message arrives", () => {
    const store = new SocialStore();
    store.receive(hello());
    store.receive({ t: "notice", code: "chat.dm_refused", params: { name: "bo" } });
    expect(store.error).toEqual({ code: "chat.dm_refused", params: { name: "bo" } });
    store.receive({ t: "dm", msgs: [dm(8, 1, 3)], history: false });
    expect(store.error).toBeNull();
  });
});
