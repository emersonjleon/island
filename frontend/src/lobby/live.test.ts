import { describe, expect, it, vi } from "vitest";

import { handleMessage, parseMessage, wsUrl } from "./live";

describe("lobby live messages", () => {
  it("parses known messages and drops the rest", () => {
    expect(parseMessage('{"t":"changed"}')).toEqual({ t: "changed" });
    expect(parseMessage('{"t":"started","url":"/play/K7QX2/"}')).toEqual({ t: "started", url: "/play/K7QX2/" });
    expect(parseMessage('{"t":"started","url":"https://evil.example/"}')).toBeNull();
    expect(parseMessage('{"t":"other"}')).toBeNull();
    expect(parseMessage("not json")).toBeNull();
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
