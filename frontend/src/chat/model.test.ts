import { describe, expect, it } from "vitest";

import { ChatLog, parseChatFrame, splitResources, type ChatLine } from "./model";

const line = (id: number, text = `m${id}`, name = "ana"): ChatLine =>
  ({ id, name, colour: "red", seat: 0, player: true, text, at: id });

describe("chat model", () => {
  it("turns resource emoji into icons, with or without the variation selector", () => {
    expect(splitResources("doy 🌲🌲 por ⛰️ o ⛰")).toEqual(
      ["doy ", { res: "lumber" }, { res: "lumber" }, " por ", { res: "ore" }, " o ", { res: "ore" }]);
    expect(splitResources("hola")).toEqual(["hola"]);
    expect(splitResources("🐟")).toEqual([{ res: "fish" }]);
  });

  it("parses chat frames and drops the rest", () => {
    expect(parseChatFrame({ t: "chat", msgs: [line(1), { id: "x" }], history: true })).toEqual(
      { t: "chat", msgs: [line(1)], history: true });
    expect(parseChatFrame({ t: "changed" })).toBeNull();
    expect(parseChatFrame(null)).toBeNull();
    const watcher = parseChatFrame({ t: "chat", msgs: [{ id: 2, name: "eve", text: "hi" }] })!;
    expect(watcher.msgs[0]).toEqual({ id: 2, name: "eve", text: "hi", colour: "", seat: null, player: false, at: 0 });
  });

  it("keeps lines in order without repeats, history included", () => {
    const log = new ChatLog(3);
    log.receive({ t: "chat", msgs: [line(2), line(1)], history: true });
    log.receive({ t: "chat", msgs: [line(2), line(3)], history: true });
    log.receive({ t: "chat", msgs: [line(4)], history: false });
    expect(log.lines.map((l) => l.id)).toEqual([2, 3, 4]);
  });

  it("counts unread lines from others while closed", () => {
    const log = new ChatLog();
    const seen: number[] = [];
    log.subscribe((_, fresh) => seen.push(fresh.length));
    log.receive({ t: "chat", msgs: [line(1)], history: true });
    expect(log.unread).toBe(0);
    log.markSent("  mine   too ");
    log.receive({ t: "chat", msgs: [line(2, "mine too")], history: false });
    expect(log.unread).toBe(0);
    log.receive({ t: "chat", msgs: [line(3), line(4)], history: false });
    expect(log.unread).toBe(2);
    log.setOpen(true);
    expect(log.unread).toBe(0);
    log.receive({ t: "chat", msgs: [line(5)], history: false });
    expect(log.unread).toBe(0);
    expect(seen).toEqual([0, 0, 2, 0, 1]);
  });
});
