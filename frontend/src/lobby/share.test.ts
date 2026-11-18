import { describe, expect, it } from "vitest";

import { hasCode } from "./share";

describe("settings code field", () => {
  it("ignores blank space", () => {
    expect(hasCode("")).toBe(false);
    expect(hasCode("  \n\t")).toBe(false);
    expect(hasCode(" classic.1. ")).toBe(true);
  });
});
