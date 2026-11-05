// World geometry shared by every renderer (§6): pointy-top hexes of circumradius 1,
// centre x = √3·(q + r/2), y = 1.5·r, with y pointing down the screen.
import type { BoardMsg } from "../protocol/types";

export interface Pt { x: number; y: number }

const SQRT3 = Math.sqrt(3);

export function hexCenter(q: number, r: number): Pt {
  return { x: SQRT3 * (q + r / 2), y: 1.5 * r };
}

/** The six corners of a hex, clockwise from N. */
export function hexCorners(q: number, r: number): Pt[] {
  const c = hexCenter(q, r);
  return [0, 1, 2, 3, 4, 5].map((i) => {
    const a = (Math.PI / 3) * i - Math.PI / 2;
    return { x: c.x + Math.cos(a), y: c.y + Math.sin(a) };
  });
}

export function vertexPos(q: number, r: number, c: "N" | "S"): Pt {
  const h = hexCenter(q, r);
  return { x: h.x, y: h.y + (c === "N" ? -1 : 1) };
}

export function lerp(a: Pt, b: Pt, t: number): Pt {
  return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
}

export function dist2(a: Pt, b: Pt): number {
  return (a.x - b.x) ** 2 + (a.y - b.y) ** 2;
}

/** Positions of every hex, vertex and edge of a board, indexed by wire id. */
export class BoardGeometry {
  readonly hex: Pt[];
  readonly vertex: Pt[];
  readonly edgeMid: Pt[];
  readonly bounds: { minX: number; minY: number; maxX: number; maxY: number };

  constructor(readonly board: BoardMsg) {
    this.hex = [];
    for (const h of board.hexes) this.hex[h.id] = hexCenter(h.q, h.r);
    this.vertex = [];
    for (const v of board.vertices) this.vertex[v.id] = vertexPos(v.q, v.r, v.c);
    this.edgeMid = [];
    for (const e of board.edges) this.edgeMid[e.id] = lerp(this.vertex[e.v[0]]!, this.vertex[e.v[1]]!, 0.5);
    const pts = board.hexes.flatMap((h) => hexCorners(h.q, h.r));
    this.bounds = {
      minX: Math.min(...pts.map((p) => p.x)), minY: Math.min(...pts.map((p) => p.y)),
      maxX: Math.max(...pts.map((p) => p.x)), maxY: Math.max(...pts.map((p) => p.y)),
    };
  }

  edgeEnds(edge: number): [Pt, Pt] {
    const [a, b] = this.board.edges[edge]!.v;
    return [this.vertex[a]!, this.vertex[b]!];
  }

  /** Nearest vertex to a world point, if within ``maxDist`` (picking for any renderer). */
  nearestVertex(p: Pt, maxDist = 0.45): number | null {
    return nearest(this.vertex, p, maxDist);
  }

  nearestEdge(p: Pt, maxDist = 0.35): number | null {
    return nearest(this.edgeMid, p, maxDist);
  }

  nearestHex(p: Pt, maxDist = 1): number | null {
    return nearest(this.hex, p, maxDist);
  }
}

function nearest(points: Pt[], p: Pt, maxDist: number): number | null {
  let best: number | null = null;
  let bestD = maxDist * maxDist;
  points.forEach((q, id) => {
    const d = dist2(p, q);
    if (d <= bestD) {
      bestD = d;
      best = id;
    }
  });
  return best;
}
