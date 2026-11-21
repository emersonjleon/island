import { describe, expect, it } from "vitest";

import { customValues, formatStat, keepText, nextBase, presetValues, savesOnEnter, type PresetsData } from "./create";

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

  it("starts a custom game from the type chosen before it", () => {
    const withBlitz: PresetsData = {
      ...data,
      presets: { ...data.presets, blitz: { players: 4, values: { "4": { land_hexes: 19, target: 7, robber: true } } } },
    };
    expect(presetValues(withBlitz, "custom", 4, () => "", "blitz")?.target).toBe(7);
    expect(presetValues(withBlitz, "custom", 4, () => "", "classic")?.target).toBe(10);
    expect(presetValues(withBlitz, "blitz", 4, () => "12", "classic")?.target).toBe(7);
  });

  it("formats summary lines", () => {
    expect(formatStat({ a: 15, b: 5, c: 4 }, ["a", "b", "c"], "Yes", "No")).toBe("15 / 5 / 4");
    expect(formatStat({ robber: false }, ["robber"], "Sí", "No")).toBe("No");
  });

  it("names the base type's choice in the keep option", () => {
    const options = [{ value: "", text: "–" }, { value: "1", text: "Yes" }, { value: "0", text: "No" }];
    expect(keepText(options, "0")).toBe("(No)");
    expect(keepText(options, undefined)).toBe("–");
  });
});

describe("savesOnEnter", () => {
  it("saves only from the name box", () => {
    expect(savesOnEnter("Enter", "save_name")).toBe(true);
    expect(savesOnEnter("Enter", "target")).toBe(false);
    expect(savesOnEnter("a", "save_name")).toBe(false);
  });
});

describe("nextBase", () => {
  it("picks an experimental type, and unpicks it back to the regular one", () => {
    expect(nextBase("classic", "settlers", "classic")).toBe("settlers");
    expect(nextBase("settlers", "explorer", "blitz")).toBe("explorer");
    expect(nextBase("explorer", "explorer", "blitz")).toBe("blitz");
  });
});
