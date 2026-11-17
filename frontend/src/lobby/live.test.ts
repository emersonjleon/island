import { describe, expect, it, vi } from "vitest";

import { handleMessage, parseMessage, wsUrl } from "./live";

describe("lobby live messages", () => {
  it("parses known messages and drops the rest", () => {
    expect(parseMessage('{"t":"changed"}')).toEqual({ t: "changed" });
    expect(parseMessage('{"t":"started","url":"/play/K7QX2/"}')).toEqual({ t: "started", url: "/play/K7QX2/" });
    expect(parseMessage('{"t":"started","url":"https://evil.example/"}')).toBeNull();
    expect(parseMessage('{"t":"other"}')).toBeNull();
    expect(parseMessage("not json")).toBeNull();
    expect(parseMessage('{"t":"chat","msgs":[{"id":1,"name":"ana","text":"hola"}],"history":true}')).toEqual({
      t: "chat", history: true, msgs: [{ id: 1, name: "ana", text: "hola", colour: "", seat: null, player: false, at: 0 }],
    });
    expect(parseMessage('{"t":"notice","code":"chat.empty"}')).toEqual({ t: "notice", code: "chat.empty", params: {} });
  });

  it("passes chat lines and refusals to the page", async () => {
    const page = { refreshSeats: vi.fn(async () => {}), navigate: vi.fn(), chat: vi.fn(), notice: vi.fn() };
    await handleMessage(page, { t: "chat", msgs: [], history: false });
    await handleMessage(page, { t: "notice", code: "chat.rate_limited", params: {} });
    expect(page.chat).toHaveBeenCalledWith({ t: "chat", msgs: [], history: false });
    expect(page.notice).toHaveBeenCalledWith("chat.rate_limited", {});
    expect(page.refreshSeats).not.toHaveBeenCalled();
  });

  it("refreshes on change and navigates on start", async () => {
    const page = { refreshSeats: vi.fn(async () => {}), navigate: vi.fn() };
    await handleMessage(page, { t: "changed" });
    await handleMessage(page, { t: "started", url: "/play/ABCDE/" });
    expect(page.refreshSeats).toHaveBeenCalledTimes(1);
    expect(page.navigate).toHaveBeenCalledWith("/play/ABCDE/");
  });

  it("builds ws and wss urls", () => {
    expect(wsUrl("/ws/lobby/X/", { protocol: "https:", host: "a.b" } as Location)).toBe("wss://a.b/ws/lobby/X/");
    expect(wsUrl("/ws/lobby/X/", { protocol: "http:", host: "localhost:8000" } as Location)).toBe(
      "ws://localhost:8000/ws/lobby/X/",
    );
  });
});
