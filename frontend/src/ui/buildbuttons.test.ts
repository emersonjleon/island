import { describe, expect, it } from "vitest";
import { buildButtons } from "./Hud";

describe("build buttons", () => {
  it("adds the megacity once the player has a city and the game has megacities", () => {
    const kinds = (s: Record<string, unknown>, cities: number) => buildButtons(s, cities).map((b) => b.kind);
    expect(kinds({ pieces: { megacities: 4 } }, 0)).toEqual(["road", "settlement", "city"]);
    expect(kinds({ pieces: { megacities: 4 } }, 1)).toEqual(["road", "settlement", "city", "megacity"]);
    expect(kinds({ pieces: { megacities: 0 } }, 2)).toEqual(["road", "settlement", "city"]);
  });
});

describe("age locks", () => {
  it("reads the age each construction needs only when ages are on", async () => {
    const { unlockAge } = await import("../state/ages");
    const ages = { ages: { enabled: true, unlock: { road: 1, settlement: 1, city: 1, megacity: 3 } } };
    expect(unlockAge(ages, "megacity")).toBe(3);
    expect(unlockAge(ages, "city")).toBe(1);
    expect(unlockAge({ ages: { enabled: false, unlock: { megacity: 3 } } }, "megacity")).toBe(1);
    expect(unlockAge({}, "megacity")).toBe(1);
  });
});
