import { describe, expect, it } from "vitest";
import type { GameStateView } from "../protocol/types";
import { advanceBlock, ageStep, agePlayer, applyAgeEvent } from "./ages";

const settings = {
  ages: { enabled: true, age2: { cost: { fish: 2, grain: 2, wool: 1, brick: 1, ore: 0 }, time_ms: 30000, requires: { cities: 1, points: 0 } } },
};

function state(): GameStateView {
  return {
    players: [{ seat: 0, points: 3, setup: { done: true } }],
    buildings: [{ seat: 0, kind: "settlement", vertex: 1 }],
  } as unknown as GameStateView;
}

describe("ages", () => {
  it("reads the next step and its needs", () => {
    expect(ageStep(settings, 2)?.cost).toEqual({ fish: 2, grain: 2, wool: 1, brick: 1 });
    const s = state();
    expect(advanceBlock(settings, s, 0)).toBe("age.need_cities");
    s.buildings.push({ seat: 0, kind: "city", vertex: 2 });
    expect(advanceBlock(settings, s, 0)).toBeNull();
    expect(advanceBlock({}, s, 0)).toBe("age.disabled");
  });

  it("follows the age events", () => {
    const s = state();
    applyAgeEvent(s, { k: "age_advance_started", seat: 0, age: 2, t0: 0, t1: 30000 });
    expect(agePlayer(s, 0).advancing).toEqual({ age: 2, t0: 0, t1: 30000 });
    expect(advanceBlock(settings, s, 0)).toBe("age.in_progress");
    applyAgeEvent(s, { k: "age_reached", seat: 0, age: 2, at: 30000 });
    expect(agePlayer(s, 0)).toEqual({ age: 2, advancing: null, reached: { "2": 30000 } });
    expect(agePlayer(s, 1).age).toBe(1);
  });
});
