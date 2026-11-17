import { describe, expect, it } from "vitest";

import { customValues, formatStat, presetValues, type PresetsData } from "./create";

const data: PresetsData = {
  presets: {
    classic: { players: 4, values: { "4": { land_hexes: 19, target: 10, robber: true } } },
    custom: { players: 4, values: { "4": { land_hexes: 19, target: 10, robber: true } } },
  },
  stats: [],
  custom: "custom",
};

describe("create-game form", () => {
  it("uses typed values in a custom game and falls back to the base", () => {
    const typed: Record<string, boolean | string> = { land_hexes: " 30 ", target: "", robber: false };
    const base = { land_hexes: 19, target: 10, robber: true };
    expect(customValues(base, (n) => typed[n])).toEqual({
      land_hexes: 30, target: 10, robber: false,
    });
    expect(customValues({ target: 10 }, () => "abc")).toEqual({ target: 10 });
  });

  it("ignores the fields for other game types", () => {
    expect(presetValues(data, "classic", 4, () => "99")).toEqual({ land_hexes: 19, target: 10, robber: true });
    expect(presetValues(data, "custom", 4, () => "12")?.target).toBe(12);
    expect(presetValues(data, "classic", 7, () => undefined)).toBeNull();
  });

  it("formats summary lines", () => {
    expect(formatStat({ a: 15, b: 5, c: 4 }, ["a", "b", "c"], "Yes", "No")).toBe("15 / 5 / 4");
    expect(formatStat({ robber: false }, ["robber"], "Sí", "No")).toBe("No");
  });
});
