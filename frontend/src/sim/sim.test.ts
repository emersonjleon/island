import { describe, expect, it } from "vitest";

import { BoardGeometry } from "../board/geometry";
import type { BoardMsg } from "../protocol/types";
import { fixture } from "../testing/fixtures";
import { ServerClock } from "./clock";
import { constructionProgress, msUntil, settlerPosition } from "./interp";

describe("interpolation", () => {
  const geo = new BoardGeometry(fixture<BoardMsg>("board.json"));
  const e = fixture<BoardMsg>("board.json").edges[3]!;

  it("moves a settler along its step", () => {
    const s = { id: 1, seat: 0, vertex: e.v[0], path: [], step: { edge: e.id, from_v: e.v[0], to_v: e.v[1], t0: 1000, t1: 2000 } };
    expect(settlerPosition(geo, s, 500)).toEqual(geo.vertex[e.v[0]]);
    const mid = settlerPosition(geo, s, 1500);
    expect(mid.x).toBeCloseTo(geo.edgeMid[e.id]!.x);
    expect(settlerPosition(geo, s, 9999)).toEqual(geo.vertex[e.v[1]]);
    expect(settlerPosition(geo, { ...s, step: null }, 1500)).toEqual(geo.vertex[e.v[0]]);
  });

  it("reports construction progress and countdowns", () => {
    const c = { id: 1, seat: 0, kind: "road" as const, target: 1, builder: null, t0: 0, t1: 3000, paid: {} };
    expect(constructionProgress(c, 1500)).toBeCloseTo(0.5);
    expect(constructionProgress(c, 5000)).toBe(1);
    expect(msUntil(20000, 15000)).toBe(5000);
    expect(msUntil(null, 1)).toBe(0);
  });
});

describe("ServerClock", () => {
  it("uses the lowest round trip sample", () => {
    let local = 0;
    const clock = new ServerClock(() => local);
    clock.hint(50_000);
    expect(clock.now()).toBe(50_000);
    local = 100; // ping sent at 0, pong after 100 ms carrying server time 60_000
    clock.sample(0, 60_000);
    expect(clock.now()).toBe(60_050);
    local = 400; // a slower sample (300 ms) is ignored
    clock.sample(100, 70_000);
    expect(clock.now()).toBe(60_350);
  });
});
