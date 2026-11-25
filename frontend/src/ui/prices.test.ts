import { describe, expect, it } from "vitest";

import { priceCards, priceKinds, priceRows } from "./Prices";

describe("price list", () => {
  it("lists the classic purchases, and the settler only when settlers stay", () => {
    expect(priceKinds({})).toEqual(["road", "settlement", "city", "dev_card"]);
    expect(priceKinds({ settlers: { leave_after_setup: false } })).toEqual(["road", "settlement", "city", "dev_card", "settler"]);
  });

  it("adds the megacity when the game has megacities, and the ages when they are on", () => {
    expect(priceKinds({ pieces: { megacities: 4 } })).toEqual(["road", "settlement", "city", "megacity", "dev_card"]);
    expect(priceKinds({ pieces: { megacities: 0 } })).toEqual(["road", "settlement", "city", "dev_card"]);
    const settings = { ages: { enabled: true, age2: { cost: { fish: 2, ore: 1 } }, age3: { cost: { fish: 3 } } } };
    const rows = priceRows(settings);
    expect(rows.map((r) => r.key)).toEqual(["road", "settlement", "city", "dev_card", "age2", "age3"]);
    expect(rows[5]!.cost).toEqual({ fish: 3 });
    expect(priceRows({ ages: { enabled: false, age2: { cost: { fish: 2 } } } }).map((r) => r.key)).not.toContain("age2");
  });

  it("shows one card per resource, in hand order", () => {
    expect(priceCards({ ore: 3, grain: 2 })).toEqual(["grain", "grain", "ore", "ore", "ore"]);
  });
});
