import { describe, expect, it } from "vitest";

import type { BoardMsg } from "../protocol/types";
import { fixture } from "../testing/fixtures";
import { BoardGeometry, dist2, hexCenter, hexCorners } from "./geometry";

const board = fixture<BoardMsg>("board.json");
const geo = new BoardGeometry(board);

describe("board geometry", () => {
  it("places hex centres on the axial layout", () => {
    expect(hexCenter(0, 0)).toEqual({ x: 0, y: 0 });
    expect(hexCenter(1, 0).x).toBeCloseTo(Math.sqrt(3));
    expect(hexCenter(0, 1)).toEqual({ x: Math.sqrt(3) / 2, y: 1.5 });
  });

  it("puts every vertex on a corner of each hex it touches", () => {
    for (const v of board.vertices) {
      for (const h of v.hexes) {
        const hex = board.hexes[h]!;
        const corners = hexCorners(hex.q, hex.r);
        expect(Math.min(...corners.map((c) => dist2(c, geo.vertex[v.id]!)))).toBeLessThan(1e-9);
      }
    }
  });

  it("makes every edge one unit long", () => {
    for (const e of board.edges) {
      const [a, b] = geo.edgeEnds(e.id);
      expect(Math.sqrt(dist2(a, b))).toBeCloseTo(1);
    }
  });

  it("picks the nearest vertex and edge", () => {
    const v = board.vertices[10]!;
    expect(geo.nearestVertex({ x: geo.vertex[v.id]!.x + 0.1, y: geo.vertex[v.id]!.y })).toBe(v.id);
    expect(geo.nearestEdge(geo.edgeMid[5]!)).toBe(5);
    expect(geo.nearestVertex({ x: 1000, y: 1000 })).toBeNull();
  });
});
