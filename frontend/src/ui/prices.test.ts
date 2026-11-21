import { describe, expect, it } from "vitest";

import { priceCards, priceKinds } from "./Prices";

describe("price list", () => {
  it("lists the classic purchases, and the settler only when settlers stay", () => {
    expect(priceKinds({})).toEqual(["road", "settlement", "city", "dev_card"]);
    expect(priceKinds({ settlers: { leave_after_setup: false } })).toEqual(["road", "settlement", "city", "dev_card", "settler"]);
  });

  it("shows one card per resource, in hand order", () => {
    expect(priceCards({ ore: 3, grain: 2 })).toEqual(["grain", "grain", "ore", "ore", "ore"]);
  });
});
