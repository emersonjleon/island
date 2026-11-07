import { describe, expect, it } from "vitest";

import { TouchGestures } from "./touch";

const feel = { tapPx: 10, tapMs: 500 };

describe("TouchGestures", () => {
  it("reports a short, still touch as a tap at its start point", () => {
    const g = new TouchGestures(feel);
    g.down(1, { x: 100, y: 100 }, 0);
    expect(g.move(1, { x: 104, y: 103 })).toEqual({ kind: "none" });
    expect(g.up(1, 120)).toEqual({ x: 100, y: 100 });
  });

  it("is not a tap when held too long or cancelled", () => {
    const g = new TouchGestures(feel);
    g.down(1, { x: 0, y: 0 }, 0);
    expect(g.up(1, 900)).toBeNull();
    g.down(2, { x: 0, y: 0 }, 1000);
    expect(g.up(2, 1010, true)).toBeNull();
  });

  it("pans with one finger once it moves past the tap slop, and is then no tap", () => {
    const g = new TouchGestures(feel);
    g.down(1, { x: 0, y: 0 }, 0);
    expect(g.move(1, { x: 30, y: 0 })).toEqual({ kind: "pan", dx: 30, dy: 0 });
    expect(g.move(1, { x: 35, y: 10 })).toEqual({ kind: "pan", dx: 5, dy: 10 });
    expect(g.up(1, 100)).toBeNull();
    // The next touch starts fresh.
    g.down(2, { x: 50, y: 50 }, 200);
    expect(g.up(2, 250)).toEqual({ x: 50, y: 50 });
  });

  it("pinches with two fingers: zoom by the change in spread around the midpoint", () => {
    const g = new TouchGestures(feel);
    g.down(1, { x: 100, y: 100 }, 0);
    g.down(2, { x: 200, y: 100 }, 10);
    const p = g.move(2, { x: 300, y: 100 });
    expect(p.kind).toBe("pinch");
    if (p.kind !== "pinch") return;
    expect(p.factor).toBeCloseTo(2);
    expect(p.at).toEqual({ x: 200, y: 100 });
    expect(p.dx).toBe(50);
    // Lifting both fingers after a pinch is never a tap; the last finger keeps panning.
    expect(g.up(2, 50)).toBeNull();
    expect(g.move(1, { x: 110, y: 100 })).toEqual({ kind: "pan", dx: 10, dy: 0 });
    expect(g.up(1, 60)).toBeNull();
    expect(g.active).toBe(0);
  });

  it("ignores a third finger", () => {
    const g = new TouchGestures(feel);
    g.down(1, { x: 0, y: 0 }, 0);
    g.down(2, { x: 10, y: 0 }, 0);
    g.down(3, { x: 20, y: 0 }, 0);
    expect(g.active).toBe(2);
    expect(g.move(3, { x: 50, y: 0 })).toEqual({ kind: "none" });
  });
});
