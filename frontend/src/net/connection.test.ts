import { describe, expect, it, vi } from "vitest";

import { GameStore } from "../state/store";
import { GameConnection, type SocketLike } from "./connection";

class FakeSocket implements SocketLike {
  readyState = 0;
  sent: Record<string, unknown>[] = [];
  onopen: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: ((ev: unknown) => void) | null = null;
  send(data: string) { this.sent.push(JSON.parse(data)); }
  close() { this.onclose?.({}); }
  open() { this.readyState = 1; this.onopen?.({}); }
  deliver(msg: object) { this.onmessage?.({ data: JSON.stringify(msg) }); }
}

function setup() {
  const sockets: FakeSocket[] = [];
  const store = new GameStore();
  const onReject = vi.fn();
  const conn = new GameConnection({
    url: "ws://x/ws/play/A/", lang: "es", store, onReject, pingMs: 60_000,
    socketFactory: () => { const s = new FakeSocket(); sockets.push(s); return s; },
  });
  conn.start();
  sockets[0]!.open();
  return { sockets, store, conn, onReject, socket: sockets[0]! };
}

describe("GameConnection", () => {
  it("says hello and pings on open", () => {
    const { socket } = setup();
    expect(socket.sent[0]).toEqual({ t: "hello", proto: 1, lang: "es" });
    expect(socket.sent[1]!.t).toBe("ping");
  });

  it("asks for a sync when an events batch skips a seq", () => {
    const { socket, store } = setup();
    socket.deliver({ t: "state", seq: 2, now: 0, state: { players: [], settlers: [], constructions: [], buildings: [], roads: [], dice_history: [] } });
    expect(store.seq).toBe(2);
    socket.deliver({ t: "events", seq: 4, now: 10, events: [] });
    expect(socket.sent.at(-1)).toEqual({ t: "sync", from_seq: 2 });
  });

  it("matches rejects to the intent that caused them", () => {
    const { socket, conn, onReject } = setup();
    const cid = conn.send({ a: "build", kind: "road", edge: 3 });
    expect(socket.sent.at(-1)).toEqual({ t: "intent", cid, a: "build", kind: "road", edge: 3 });
    socket.deliver({ t: "reject", cid, code: "build.not_connected", params: {} });
    expect(onReject).toHaveBeenCalledWith(expect.objectContaining({ code: "build.not_connected" }), { a: "build", kind: "road", edge: 3 });
  });

  it("passes chat frames on and keeps chat lines until the socket opens", () => {
    const sockets: FakeSocket[] = [];
    const onChat = vi.fn();
    const conn = new GameConnection({
      url: "ws://x/", lang: "es", store: new GameStore(), onChat, pingMs: 60_000,
      socketFactory: () => { const s = new FakeSocket(); sockets.push(s); return s; },
    });
    conn.start();
    expect(conn.say("early")).toBe(true);
    for (let i = 0; i < 4; i++) conn.say(`q${i}`);
    expect(conn.say("one too many")).toBe(false);
    sockets[0]!.open();
    expect(sockets[0]!.sent.filter((m) => m.t === "chat").map((m) => m.text)).toEqual(["early", "q0", "q1", "q2", "q3"]);
    expect(conn.say("hola")).toBe(true);
    expect(sockets[0]!.sent.at(-1)).toEqual({ t: "chat", text: "hola" });
    sockets[0]!.deliver({ t: "chat", msgs: [], history: true });
    expect(onChat).toHaveBeenCalledWith({ t: "chat", msgs: [], history: true });
  });

  it("reconnects after the socket closes", () => {
    vi.useFakeTimers();
    const { sockets } = setup();
    sockets[0]!.close();
    vi.advanceTimersByTime(600);
    expect(sockets).toHaveLength(2);
    vi.useRealTimers();
  });

  it("refuses orders while the socket is down instead of losing them", () => {
    vi.useFakeTimers();
    const { sockets, conn, onReject } = setup();
    sockets[0]!.close();
    expect(conn.send({ a: "buy_dev_card" })).toBeNull();
    expect(onReject).toHaveBeenCalledWith(expect.objectContaining({ code: "net.offline" }), { a: "buy_dev_card" });
    vi.useRealTimers();
  });

  it("drops a socket that went quiet and reports the retries", () => {
    vi.useFakeTimers();
    const sockets: FakeSocket[] = [];
    const statuses: [string, number][] = [];
    const conn = new GameConnection({
      url: "ws://x/", lang: "es", store: new GameStore(), pingMs: 1000, events: null,
      onStatus: (st, info) => statuses.push([st, info.attempt]),
      socketFactory: () => { const s = new FakeSocket(); sockets.push(s); return s; },
    });
    conn.start();
    sockets[0]!.open();
    vi.advanceTimersByTime(3000);                 // pings answered by nothing...
    expect(sockets).toHaveLength(1);
    vi.advanceTimersByTime(1000);                 // ...past three intervals: dropped
    expect(statuses.at(-1)).toEqual(["closed", 1]);
    conn.retryNow();                              // no need to wait for the backoff
    expect(sockets).toHaveLength(2);
    sockets[1]!.open();
    expect(statuses.at(-1)).toEqual(["open", 0]);
    conn.stop();
    vi.useRealTimers();
  });

  it("follows the browser's online and offline events", () => {
    vi.useFakeTimers();
    const target = new EventTarget();
    const sockets: FakeSocket[] = [];
    const conn = new GameConnection({
      url: "ws://x/", lang: "es", store: new GameStore(), pingMs: 60_000, events: target as unknown as Window,
      socketFactory: () => { const s = new FakeSocket(); sockets.push(s); return s; },
    });
    conn.start();
    sockets[0]!.open();
    target.dispatchEvent(new Event("offline"));
    expect(conn.isOpen).toBe(false);
    target.dispatchEvent(new Event("online"));
    expect(sockets).toHaveLength(2);
    conn.stop();
    vi.useRealTimers();
  });

  it("tracks who is connected", () => {
    const { socket, store } = setup();
    socket.deliver({ t: "welcome", game: "A", seat: 0, proto: 1, settings: {} });
    socket.deliver({ t: "presence", seat: 1, online: true });
    socket.deliver({ t: "presence", seat: 2, online: false });
    expect([...store.offline]).toEqual([2]);
    socket.deliver({ t: "presence", seat: 2, online: true });
    expect([...store.offline]).toEqual([]);
    // after a reconnect, people seen before count as away until they answer
    socket.deliver({ t: "welcome", game: "A", seat: 0, proto: 1, settings: {} });
    expect([...store.offline].sort()).toEqual([1, 2]);
  });
});
