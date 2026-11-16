import { describe, expect, it } from "vitest";

import type { GameStateView } from "../protocol/types";
import enHud from "../locales/en/hud.json";
import esHud from "../locales/es/hud.json";
import { TIPS, TIP_ROLLS, guideStep } from "./guide";

const player = (over: Record<string, unknown> = {}) => ({
  seat: 0, setup: { remaining: { settlement: 2, road: 2 }, done: false, settlements_built: 0 }, ...over,
});
const state = (over: Record<string, unknown> = {}) => ({
  phase: "setup", players: [player()], constructions: [], clock_started: false, dice_history: [], ...over,
}) as unknown as GameStateView;

describe("in-game guide", () => {
  it("walks a new player through the setup", () => {
    expect(guideStep(state(), 0, {})).toEqual({ key: "setup_settlement", step: 1, total: 4 });
    const afterFirst = player({ setup: { remaining: { settlement: 1, road: 2 }, done: false, settlements_built: 1 } });
    expect(guideStep(state({ players: [afterFirst] }), 0, {})).toEqual({ key: "setup_road", step: 2, total: 4 });
    const afterRoad = player({ setup: { remaining: { settlement: 1, road: 1 }, done: false, settlements_built: 1 } });
    expect(guideStep(state({ players: [afterRoad] }), 0, {})).toEqual({ key: "setup_settlement", step: 3, total: 4 });
    const building = state({ constructions: [{ seat: 0, kind: "road", setup: true }] });
    expect(guideStep(building, 0, {})).toEqual({ key: "building", kind: "road" });
  });

  it("gives tips once the setup is done and stays quiet for spectators", () => {
    const done = player({ setup: { remaining: {}, done: true, settlements_built: 2 } });
    expect(guideStep(state({ players: [done] }), 0, {})).toEqual({ key: "wait_clock" });
    const s = state({ players: [done], clock_started: true, phase: "running", dice_history: new Array(TIP_ROLLS).fill(8) });
    expect(guideStep(s, 0, {})).toEqual({ key: "tip", tip: TIPS[1], index: 1 });
    expect(guideStep(s, null, {})).toBeNull();
    expect(guideStep(state({ phase: "finished" }), 0, {})).toBeNull();
  });

  it("has every guide text in both languages", () => {
    for (const hud of [enHud, esHud] as unknown as { guide: Record<string, unknown>; help: Record<string, unknown> }[]) {
      for (const k of ["setup_settlement", "setup_road", "building", "wait_clock", "title", "hide", "show", "help"]) {
        expect(hud.guide[k], k).toBeTruthy();
      }
      for (const tip of TIPS) expect((hud.guide["tips"] as Record<string, string>)[tip], tip).toBeTruthy();
      for (const k of ["title", "goal", "dice", "build", "robber", "trade", "cards", "keys", "touch", "full"]) {
        expect(hud.help[k], k).toBeTruthy();
      }
    }
  });
});
