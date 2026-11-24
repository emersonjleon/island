import { describe, expect, it } from "vitest";
import { variantHelpKeys } from "./Guide";

describe("variantHelpKeys", () => {
  it("lists nothing for the classic game", () => {
    expect(variantHelpKeys({ ages: { enabled: false }, settlers: { leave_after_setup: true }, visibility: { map: "open", hidden_numbers: false } })).toEqual([]);
  });
  it("adds Largest Population only with ages and settlers together", () => {
    expect(variantHelpKeys({ ages: { enabled: true }, settlers: { leave_after_setup: true } })).toEqual(["ages"]);
    expect(variantHelpKeys({ ages: { enabled: true }, settlers: { leave_after_setup: false } })).toEqual(["ages", "settlers", "population"]);
  });
  it("explains the fog and hidden numbers", () => {
    expect(variantHelpKeys({ visibility: { map: "explored", hidden_numbers: true } })).toEqual(["fog", "numbers"]);
  });
});
