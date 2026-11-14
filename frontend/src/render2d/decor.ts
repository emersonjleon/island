// Small hand-drawn details on the board: trees, sheep, wheat, clay, peaks, dunes and
// waves. Everything is drawn once per board into the board layer, and positions come
// from a hash of the hex id, so the island looks the same for every player and on
// every redraw.
import type { Graphics } from "pixi.js";

import type { Terrain } from "../protocol/types";

/** A cheap integer hash → [0, 1). Deterministic, no Math.random. */
export function hash01(a: number, b = 0): number {
  let h = (a * 374761393 + b * 668265263) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
}

/** Spots around a hex centre (in hex radii) that stay clear of the number token. */
export function decorSpots(id: number, count: number): { x: number; y: number; s: number }[] {
  const out: { x: number; y: number; s: number }[] = [];
  const start = Math.floor(hash01(id, 1) * 6);
  for (let i = 0; i < count; i++) {
    const slot = (start + Math.round((i * 6) / count)) % 6;
    const a = (Math.PI / 3) * slot + (hash01(id, 10 + i) - 0.5) * 0.5;
    const r = 0.52 + hash01(id, 20 + i) * 0.1;
    out.push({ x: Math.cos(a) * r, y: Math.sin(a) * r, s: 0.85 + hash01(id, 30 + i) * 0.3 });
  }
  return out;
}

/** Details are drawn a little larger than their spot so they read at the default zoom. */
const DECOR_SCALE = 1.3;

const COUNT: Record<Terrain, number> = { forest: 6, pasture: 4, fields: 5, hills: 3, mountains: 3, desert: 3 };

/** Draw the details of one land hex centred at (cx, cy) pixels; ``u`` is the hex radius in pixels. */
export function drawTerrainDecor(g: Graphics, terrain: Terrain, id: number, cx: number, cy: number, u: number): void {
  for (const spot of decorSpots(id, COUNT[terrain])) {
    const x = cx + spot.x * u;
    const y = cy + spot.y * u;
    const s = u * spot.s * DECOR_SCALE;
    DRAW[terrain](g, x, y, s, id);
  }
}

const DRAW: Record<Terrain, (g: Graphics, x: number, y: number, s: number, id: number) => void> = {
  forest(g, x, y, s) {
    g.ellipse(x, y + s * 0.13, s * 0.11, s * 0.035).fill({ color: 0x0b2e12, alpha: 0.35 });
    g.rect(x - s * 0.015, y + s * 0.05, s * 0.03, s * 0.08).fill(0x5b3a21);
    g.poly([x, y - s * 0.2, x + s * 0.1, y + s * 0.02, x - s * 0.1, y + s * 0.02]).fill(0x1b5e20);
    g.poly([x, y - s * 0.26, x + s * 0.075, y - s * 0.08, x - s * 0.075, y - s * 0.08]).fill(0x2e7d32);
    g.poly([x, y - s * 0.26, x + s * 0.075, y - s * 0.08, x, y - s * 0.1]).fill({ color: 0x0b3d10, alpha: 0.35 });
  },
  pasture(g, x, y, s, id) {
    if (hash01(id, Math.round(x)) < 0.5) {
      // a sheep
      g.ellipse(x, y + s * 0.07, s * 0.09, s * 0.025).fill({ color: 0x2f5a17, alpha: 0.3 });
      g.circle(x - s * 0.04, y, s * 0.045).circle(x + s * 0.02, y - s * 0.015, s * 0.05).circle(x + s * 0.05, y + s * 0.01, s * 0.04)
        .fill(0xfbf8ef);
      g.ellipse(x - s * 0.085, y - s * 0.01, s * 0.025, s * 0.02).fill(0x3a3a3a);
      g.rect(x - s * 0.04, y + s * 0.035, s * 0.012, s * 0.03).rect(x + s * 0.03, y + s * 0.035, s * 0.012, s * 0.03).fill(0x3a3a3a);
    } else {
      // a grass tuft
      for (const dx of [-0.04, 0, 0.04]) {
        g.moveTo(x + dx * s, y + s * 0.05).quadraticCurveTo(x + dx * s * 1.4, y - s * 0.02, x + dx * s * 2, y - s * 0.07);
      }
      g.stroke({ width: Math.max(1, s * 0.018), color: 0x5f9a2c, cap: "round" });
    }
  },
  fields(g, x, y, s) {
    for (const dx of [-0.06, 0, 0.06]) {
      const bx = x + dx * s;
      g.moveTo(bx, y + s * 0.08).lineTo(bx + dx * s * 0.4, y - s * 0.06);
    }
    g.stroke({ width: Math.max(1, s * 0.016), color: 0xa67c1a, cap: "round" });
    for (const dx of [-0.06, 0, 0.06]) {
      g.ellipse(x + dx * s * 1.4, y - s * 0.085, s * 0.022, s * 0.045);
    }
    g.fill(0xd99a16);
  },
  hills(g, x, y, s) {
    // a small stack of bricks on a clay mound
    g.ellipse(x, y + s * 0.06, s * 0.13, s * 0.05).fill(0x9a4527);
    const w = s * 0.07;
    const h = s * 0.035;
    for (const [bx, by] of [[-0.075, 0.01], [0.005, 0.01], [-0.035, -0.03]] as const) {
      g.rect(x + bx * s, y + by * s, w, h);
    }
    g.fill(0xe0835a).stroke({ width: Math.max(1, s * 0.01), color: 0x7a3218 });
  },
  mountains(g, x, y, s) {
    const w = s * 0.17;
    const h = s * 0.24;
    g.poly([x - w, y + s * 0.08, x, y + s * 0.08 - h, x + w, y + s * 0.08]).fill(0x6d7177);
    g.poly([x, y + s * 0.08 - h, x + w, y + s * 0.08, x + w * 0.1, y + s * 0.08]).fill(0x575b61);
    g.poly([x - w * 0.36, y + s * 0.08 - h * 0.64, x, y + s * 0.08 - h, x + w * 0.36, y + s * 0.08 - h * 0.64,
            x + w * 0.12, y + s * 0.08 - h * 0.56, x - w * 0.08, y + s * 0.08 - h * 0.68]).fill(0xf7f7f2);
  },
  desert(g, x, y, s, id) {
    if (hash01(id, Math.round(y)) < 0.4) {
      // a cactus
      g.roundRect(x - s * 0.02, y - s * 0.12, s * 0.04, s * 0.18, s * 0.02)
        .roundRect(x - s * 0.08, y - s * 0.06, s * 0.03, s * 0.08, s * 0.015)
        .roundRect(x + s * 0.05, y - s * 0.09, s * 0.03, s * 0.08, s * 0.015)
        .rect(x - s * 0.06, y - s * 0.005, s * 0.06, s * 0.025).rect(x, y - s * 0.03, s * 0.06, s * 0.025)
        .fill(0x5b8f3a);
    } else {
      g.moveTo(x - s * 0.13, y + s * 0.03).quadraticCurveTo(x - s * 0.03, y - s * 0.07, x + s * 0.07, y + s * 0.03)
        .moveTo(x - s * 0.02, y + s * 0.09).quadraticCurveTo(x + s * 0.06, y + s * 0.01, x + s * 0.14, y + s * 0.09)
        .stroke({ width: Math.max(1, s * 0.018), color: 0xc4a466, cap: "round" });
    }
  },
};

/** A couple of little wave marks on a sea hex. */
export function drawWaves(g: Graphics, id: number, cx: number, cy: number, u: number, colour: number, alpha: number): void {
  const n = hash01(id, 7) < 0.5 ? 1 : 2;
  for (let i = 0; i < n; i++) {
    const a = hash01(id, 40 + i) * Math.PI * 2;
    const r = 0.2 + hash01(id, 50 + i) * 0.45;
    const x = cx + Math.cos(a) * r * u;
    const y = cy + Math.sin(a) * r * u;
    const w = u * 0.1;
    g.moveTo(x - w * 1.5, y).quadraticCurveTo(x - w * 0.75, y - w * 0.6, x, y).quadraticCurveTo(x + w * 0.75, y - w * 0.6, x + w * 1.5, y);
  }
  g.stroke({ width: Math.max(1, u * 0.025), color: colour, alpha, cap: "round" });
}
