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
