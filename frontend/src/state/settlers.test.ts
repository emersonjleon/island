import { describe, expect, it } from "vitest";
import type { GameStateView } from "../protocol/types";
import { buySettlerBlock, gatherNumbers, ownGatherNumbers, settlerLimit, settlersStay } from "./settlers";

const SETTINGS = { settlers: { leave_after_setup: false, max: 3, gather: true, gather_rolls: [[3], [11], [2, 12]] } };

function state(settlers: number[], done = true): GameStateView {
  return {
    players: [{ seat: 0, name: "a", colour: "red", pieces: {}, setup: { remaining: {}, done, settlements_built: 2 }, settlers }],
    buildings: [{ kind: "settlement", seat: 0, vertex: 4 }],
  } as unknown as GameStateView;
}

describe("settlers", () => {
  it("reads the settings", () => {
    expect(settlersStay(SETTINGS)).toBe(true);
    expect(settlersStay({ settlers: { leave_after_setup: true } })).toBe(false);
    expect(gatherNumbers(SETTINGS, 0)).toEqual([3]);
    expect(gatherNumbers(SETTINGS, 2)).toEqual([2, 12]);
    expect(gatherNumbers(SETTINGS, 3)).toEqual([3]);
    expect(gatherNumbers({ settlers: { gather: false, gather_rolls: [[3]] } }, 0)).toEqual([]);
  });

  it("numbers own settlers by id", () => {
    const m = ownGatherNumbers(SETTINGS, state([9, 2]), 0);
    expect(m.get(2)).toEqual([3]);
    expect(m.get(9)).toEqual([11]);
    expect(ownGatherNumbers(SETTINGS, state([2]), null).size).toBe(0);
  });

  it("says why a settler cannot be bought", () => {
    expect(buySettlerBlock(SETTINGS, state([1]), 0)).toBeNull();
    expect(buySettlerBlock(SETTINGS, state([1, 2, 3]), 0)).toBe("settler.max");
    expect(buySettlerBlock(SETTINGS, state([1], false), 0)).toBe("settler.setup_not_done");
    expect(buySettlerBlock({ settlers: { leave_after_setup: true } }, state([1]), 0)).toBe("settler.not_available");
  });

  it("allows one settler per settlement and two per city", () => {
    const dyn = { settlers: { leave_after_setup: false, max: 20, per_settlement: 1, per_city: 2 } };
    const st = (kinds: string[]) => ({ buildings: kinds.map((kind, i) => ({ kind, seat: 0, vertex: i })) }) as unknown as GameStateView;
    expect(settlerLimit(dyn, st([]), 0)).toBe(1);
    expect(settlerLimit(dyn, st(["settlement", "settlement"]), 0)).toBe(2);
    expect(settlerLimit(dyn, st(["settlement", "city"]), 0)).toBe(3);
    expect(settlerLimit({ settlers: { ...dyn.settlers, max: 2 } }, st(["city", "city"]), 0)).toBe(2);
    expect(settlerLimit(SETTINGS, st([]), 0)).toBe(3);
    expect(buySettlerBlock(dyn, state([1]), 0)).toBe("settler.max");
  });
});
