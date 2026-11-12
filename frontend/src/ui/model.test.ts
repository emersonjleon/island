import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import i18next, { type TFunction } from "i18next";
import { beforeAll, describe, expect, it } from "vitest";

import type { BoardMsg, GameStateView } from "../protocol/types";
import { fixture } from "../testing/fixtures";
import enErrors from "../locales/en/errors.json";
import enEvents from "../locales/en/events.json";
import enHud from "../locales/en/hud.json";
import esErrors from "../locales/es/errors.json";
import esEvents from "../locales/es/events.json";
import esHud from "../locales/es/hud.json";
import {
  bestRatio, canAfford, checkTrade, costOf, countdownShare, csrfFromCookie, errorText, formatRes, logLine,
  ownedHarbors, prettyCombo, victoryTarget,
} from "./model";

const here = dirname(fileURLToPath(import.meta.url));
const codes = JSON.parse(readFileSync(join(here, "../../../protocol/codes.json"), "utf8")) as {
  errors: string[]; events: string[]; reasons: Record<string, string[]>;
};
// Codes the Django consumer sends (gameplay/codes.py).
const GAMEPLAY_CODES = ["game.busy", "game.not_running", "intent.bad_cid", "intent.rate_limited", "intent.spectator",
  "message.invalid", "message.too_large", "proto.unsupported"];

const SETTINGS = {
  economy: { costs: { road: { brick: 1, lumber: 1 }, city: { grain: 2, ore: 3 } }, trade: { bank_ratio: 4 } },
  trading: { harbor_trade: true },
  setup: { bank_trade_during_setup: false },
  victory: { target: 10 },
};

function state(over: Partial<GameStateView> = {}): GameStateView {
  return {
    phase: "running", now: 0, viewer: 0, bank: { ore: 5, lumber: 19 }, buildings: [], roads: [], settlers: [],
    constructions: [], robber: null, clock_started: true, next_roll_at: null, last_roll: null, dice_history: [],
    winner: null, finished_at: null,
    players: [{ seat: 0, name: "ana", colour: "red", pieces: {}, setup: { remaining: {}, done: true, settlements_built: 2 },
      settlers: [], hand: { lumber: 8, brick: 3, grain: 2, ore: 2 } }],
    ...over,
  };
}

let t: TFunction;
let tEs: TFunction;
beforeAll(async () => {
  const make = async (lng: string) => {
    const i = i18next.createInstance();
    await i.init({ lng, fallbackLng: "en", resources: {
      en: { hud: enHud, errors: enErrors, events: enEvents }, es: { hud: esHud, errors: esErrors, events: esEvents },
    }, interpolation: { escapeValue: false } });
    return i.t.bind(i) as TFunction;
  };
  t = await make("en");
  tEs = await make("es");
});

describe("costs and trade", () => {
  it("reads costs and the victory target from settings", () => {
    expect(costOf(SETTINGS, "city")).toEqual({ grain: 2, ore: 3 });
    expect(costOf({}, "city")).toEqual({});
    expect(victoryTarget(SETTINGS)).toBe(10);
    expect(canAfford({ grain: 2, ore: 3 }, costOf(SETTINGS, "city"))).toBe(true);
    expect(canAfford({ grain: 2, ore: 2 }, costOf(SETTINGS, "city"))).toBe(false);
    expect(canAfford(undefined, {})).toBe(true);
  });

  it("uses the best harbor the player has built on", () => {
    const board = fixture<BoardMsg>("board.json");
    const generic = board.harbors.findIndex((h) => h.resource === null);
    const lumber = board.harbors.findIndex((h) => h.resource === "lumber");
    const s = state();
    expect(bestRatio(SETTINGS, board, s, 0, "lumber")).toBe(4);
    if (generic >= 0) {
      s.buildings = [{ kind: "settlement", seat: 0, vertex: board.harbors[generic]!.vertices[0]! }];
      expect(ownedHarbors(board, s, 0)).toEqual([generic]);
      expect(bestRatio(SETTINGS, board, s, 0, "ore")).toBe(board.harbors[generic]!.ratio);
    }
    if (lumber >= 0) {
      s.buildings.push({ kind: "settlement", seat: 0, vertex: board.harbors[lumber]!.vertices[1]! });
      expect(bestRatio(SETTINGS, board, s, 0, "lumber")).toBe(board.harbors[lumber]!.ratio);
      expect(bestRatio({ ...SETTINGS, trading: { harbor_trade: false } }, board, s, 0, "lumber")).toBe(4);
    }
    // Someone else's building does not help.
    expect(bestRatio(SETTINGS, board, state({ buildings: [{ kind: "city", seat: 1, vertex: board.harbors[0]!.vertices[0]! }] }), 0, "lumber")).toBe(4);
  });

  it("pre-checks bank trades with the engine's reasons", () => {
    const board = fixture<BoardMsg>("board.json");
    const s = state();
    expect(checkTrade(SETTINGS, board, s, 0, "lumber", "ore", 2)).toEqual({ ok: true, ratio: 4 });
    expect(checkTrade(SETTINGS, board, s, 0, "lumber", "ore", 3).reason).toBe("trade.cannot_afford");
    expect(checkTrade(SETTINGS, board, s, 0, "ore", "ore", 1).reason).toBe("trade.same_resource");
    expect(checkTrade(SETTINGS, board, state({ bank: { ore: 0 } }), 0, "lumber", "ore", 1).reason).toBe("trade.bank_empty");
    const setup = state();
    setup.players[0]!.setup.done = false;
    expect(checkTrade(SETTINGS, board, setup, 0, "lumber", "ore", 1).reason).toBe("trade.setup_forbidden");
  });
});

describe("texts", () => {
  it("translates every error code the server can send, in every language", () => {
    for (const code of [...codes.errors, ...GAMEPLAY_CODES]) {
      expect(errorText(t, code)).not.toContain(code);
      expect(errorText(tEs, code)).not.toContain(code);
    }
    expect(errorText(t, "made.up")).toContain("made.up");
  });

  it("translates every construction cancel reason", () => {
    for (const r of codes.reasons.construction_cancelled!) {
      expect((enEvents.reason as Record<string, string>)[r]).toBeTruthy();
      expect((esEvents.reason as Record<string, string>)[r]).toBeTruthy();
    }
  });

  it("formats resources and log lines", () => {
    const name = (s: number) => ["ana", "ben"][s]!;
    expect(formatRes(t, { ore: 1, lumber: 2 })).toBe("2 lumber, 1 ore");
    expect(formatRes(tEs, { grain: 3 })).toBe("3 de trigo");
    expect(logLine(t, { k: "dice_rolled", sum: 8 }, name, 0)!.text).toBe("Rolled 8");
    expect(logLine(t, { k: "built", seat: 1, kind: "city" }, name, 0)!.text).toBe("ben built a city");
    expect(logLine(t, { k: "built", seat: 0, kind: "road" }, name, 0)!.text).toBe("You built a road");
    expect(logLine(t, { k: "produced", roll: 6, gains: { "0": { wool: 1 }, "1": { ore: 2 } } }, name, 0)!.text).toBe("You got 1 wool");
    expect(logLine(t, { k: "produced", roll: 6, gains: { "1": { ore: 2 } } }, name, 0)).toBeNull();
    expect(logLine(t, { k: "produced", roll: 2, gains: {} }, name, 0)!.text).toBe("Nobody produced anything");
    expect(logLine(t, { k: "construction_cancelled", seat: 1, reason: "conflict" }, name, 0)!.text)
      .toBe("ben: building stopped (someone else built there first)");
    expect(logLine(t, { k: "game_over", winner: 1, points: {} }, name, 0)!.text).toBe("ben won the game");
    expect(logLine(t, { k: "game_over", winner: 0, points: {} }, name, 0)!.text).toBe("You won the game");
    expect(logLine(t, { k: "starting_resources", seat: 0, gained: {} }, name, 0)).toBeNull();
    expect(logLine(t, { k: "settler_step" }, name, 0)).toBeNull();
    // Every event kind either has a line or is deliberately skipped, never throws.
    for (const k of codes.events) logLine(t, { k, seat: 0, gains: {}, give: {}, get: {} }, name, 0);
  });

  it("shows keys readably", () => {
    expect(prettyCombo("Shift+KeyW")).toBe("Shift + W");
    expect(prettyCombo("ArrowUp")).toBe("↑");
    expect(prettyCombo("Digit2")).toBe("2");
    expect(prettyCombo("Equal")).toBe("=");
  });
});

describe("misc", () => {
  it("countdown share", () => {
    expect(countdownShare(20_000, 10_000, 20_000)).toBe(0.5);
    expect(countdownShare(20_000, 30_000, 20_000)).toBe(0);
    expect(countdownShare(null, 0, 20_000)).toBe(0);
  });

  it("reads the CSRF cookie", () => {
    expect(csrfFromCookie("a=1; csrftoken=abc%3D; b=2")).toBe("abc=");
    expect(csrfFromCookie("a=1")).toBe("");
  });
});
