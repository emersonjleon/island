import { describe, expect, it } from "vitest";

import { BoardGeometry, walkableNeighbours } from "../board/geometry";
import type { BoardMsg } from "../protocol/types";
import { fixture } from "../testing/fixtures";
import { heldDirection, neighbourToward } from "./directions";

describe("keyboard directions", () => {
  it("combines held keys into a direction", () => {
    expect(heldDirection(new Set(["move_up"]))).toEqual({ x: 0, y: -1 });
    expect(heldDirection(new Set(["move_left", "move_right"]))).toBeNull();
    const d = heldDirection(new Set(["move_up", "move_right"]))!;
    expect(d.x).toBeCloseTo(Math.SQRT1_2);
    expect(d.y).toBeCloseTo(-Math.SQRT1_2);
  });

  it("picks the closest neighbour within 90 degrees", () => {
    const from = { x: 0, y: 0 };
    const ns = [{ id: 1, at: { x: 0, y: -1 } }, { id: 2, at: { x: -0.87, y: 0.5 } }, { id: 3, at: { x: 0.87, y: 0.5 } }];
    expect(neighbourToward(from, ns, { x: 0, y: -1 }, -1)!.id).toBe(1);
    expect(neighbourToward(from, ns, { x: -1, y: 0 }, -1)!.id).toBe(2);
    // Straight down sits between 2 and 3: lean decides, so alternating zigzags.
    const left = neighbourToward(from, ns, { x: 0, y: 1 }, -1)!;
    const right = neighbourToward(from, ns, { x: 0, y: 1 }, 1)!;
    expect(new Set([left.id, right.id])).toEqual(new Set([2, 3]));
    expect(left.side).toBe(-1);
    expect(right.side).toBe(1);
    // Nothing within 90 degrees.
    expect(neighbourToward(from, [{ id: 1, at: { x: 0, y: -1 } }], { x: 0, y: 1 }, 1)).toBeNull();
  });

  it("walking one direction on the real board keeps going that way", () => {
    const board = fixture<BoardMsg>("board.json");
    const geo = new BoardGeometry(board);
    const start = board.vertices.find((v) => walkableNeighbours(board, v.id).length === 3)!.id;
    for (const dir of [{ x: 0, y: -1 }, { x: 1, y: 0 }, { x: 0, y: 1 }, { x: -1, y: 0 }]) {
      let v = start;
      let lean = -1;
      for (let i = 0; i < 4; i++) {
        const ns = walkableNeighbours(board, v).map((id) => ({ id, at: geo.vertex[id]! }));
        const pick = neighbourToward(geo.vertex[v]!, ns, dir, lean);
        if (!pick) break;
        const a = geo.vertex[v]!;
        const b = geo.vertex[pick.id]!;
        expect((b.x - a.x) * dir.x + (b.y - a.y) * dir.y).toBeGreaterThan(0);
        if (pick.side) lean = -pick.side;
        v = pick.id;
      }
    }
  });

  it("walkable neighbours are land vertices joined by land edges", () => {
    const board = fixture<BoardMsg>("board.json");
    for (const v of board.vertices) {
      for (const n of walkableNeighbours(board, v.id)) {
        expect(board.vertices[n]!.adj_v).toContain(v.id);
        expect(board.vertices[n]!.hexes.some((h) => board.hexes[h]!.land)).toBe(true);
      }
    }
  });
});
