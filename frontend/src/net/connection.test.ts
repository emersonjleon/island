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

  it("reconnects after the socket closes", () => {
    vi.useFakeTimers();
    const { sockets } = setup();
    sockets[0]!.close();
    vi.advanceTimersByTime(600);
    expect(sockets).toHaveLength(2);
    vi.useRealTimers();
  });
});
