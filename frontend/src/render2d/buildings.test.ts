import { describe, expect, it } from "vitest";

import { peaks } from "./buildings";

describe("age pennants", () => {
  it("stand above each kind of building, two on a megacity", () => {
    for (const kind of ["settlement", "city", "megacity"]) {
      const at = peaks(kind, 100, 100, 60);
      expect(at.length).toBe(kind === "megacity" ? 2 : 1);
      for (const [, y] of at) expect(y).toBeLessThan(100);
    }
  });
});
