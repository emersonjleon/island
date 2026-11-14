// Settlements, cities and megacities, drawn as small buildings in the owner's colour:
// a cottage, a town hall with a tower, and a walled city with three towers and a
// gold dome. Walls carry the player colour, roofs a darker shade of it, so pieces stay
// easy to tell apart at a glance. ``alpha`` below 1 draws a piece under construction.
import type { Graphics } from "pixi.js";

import * as P from "./palette";

const WINDOW = 0xffe9a3;
const GOLD = 0xf0c94f;
const GOLD_DARK = 0xa67c1a;

/** Multiply each channel by ``f`` (f < 1 darkens, f > 1 lightens towards white). */
export function shade(colour: number, f: number): number {
  const ch = (shift: number) => {
    const v = (colour >> shift) & 0xff;
    return Math.max(0, Math.min(255, Math.round(f <= 1 ? v * f : v + (255 - v) * (f - 1))));
  };
  return (ch(16) << 16) | (ch(8) << 8) | ch(0);
}

class Pen {
  constructor(private g: Graphics, private alpha: number, private line: number) {}

  /** A wall from the ground line ``y0`` up, with its right half in shade. */
  wall(x0: number, y0: number, w: number, h: number, fill: number): void {
    this.g.rect(x0, y0 - h, w, h).fill({ color: fill, alpha: this.alpha })
      .stroke({ width: this.line, color: P.OUTLINE, alpha: this.alpha, join: "round" });
    this.g.rect(x0 + w * 0.55, y0 - h, w * 0.45, h).fill({ color: 0x000000, alpha: 0.16 * this.alpha });
  }

  /** A pitched roof sitting on a wall whose top edge is at ``yTop``. */
  roof(x0: number, yTop: number, w: number, rise: number, over: number, fill: number): void {
    const mid = x0 + w / 2;
    this.g.poly([x0 - over, yTop, mid, yTop - rise, x0 + w + over, yTop]).fill({ color: fill, alpha: this.alpha })
      .stroke({ width: this.line, color: P.OUTLINE, alpha: this.alpha, join: "round" });
    this.g.poly([mid, yTop - rise, x0 + w + over, yTop, mid, yTop]).fill({ color: 0x000000, alpha: 0.18 * this.alpha });
  }

  rect(x: number, y: number, w: number, h: number, fill: number, outlined = false): void {
    this.g.rect(x, y, w, h).fill({ color: fill, alpha: this.alpha });
    if (outlined) this.g.stroke({ width: this.line * 0.7, color: P.OUTLINE, alpha: this.alpha });
  }

  /** A door with a round top. */
  door(x: number, y0: number, w: number, h: number): void {
    this.g.roundRect(x - w / 2, y0 - h, w, h + w / 2, w / 2).fill({ color: P.OUTLINE, alpha: 0.85 * this.alpha });
  }

  circle(x: number, y: number, r: number, fill: number, edge: number): void {
    this.g.circle(x, y, r).fill({ color: fill, alpha: this.alpha }).stroke({ width: this.line * 0.8, color: edge, alpha: this.alpha });
  }

  shadow(x: number, y: number, rx: number, ry: number): void {
    this.g.ellipse(x, y, rx, ry).fill({ color: P.SHADOW, alpha: 0.35 * this.alpha });
  }

  poly(points: number[], fill: number, edge: number): void {
    this.g.poly(points).fill({ color: fill, alpha: this.alpha })
      .stroke({ width: this.line * 0.8, color: edge, alpha: this.alpha, join: "round" });
  }
}

/** Draw one building centred on its vertex at (x, y) pixels; ``u`` is the hex radius in pixels. */
export function drawBuilding(g: Graphics, kind: string, x: number, y: number, u: number, colour: number, alpha: number): void {
  const pen = new Pen(g, alpha, Math.max(1.2, u * 0.028));
  const roof = shade(colour, 0.62);
  if (kind === "settlement") settlement(pen, x, y, u * 0.17, colour, roof);
  else if (kind === "city") city(pen, x, y, u * 0.19, colour, roof);
  else megacity(pen, x, y, u * 0.2, colour, roof);
}

function settlement(pen: Pen, x: number, y: number, s: number, wall: number, roof: number): void {
  const ground = y + s * 0.95;
  pen.shadow(x + s * 0.15, ground, s * 1.35, s * 0.32);
  pen.rect(x + s * 0.35, y - s * 1.15, s * 0.32, s * 0.8, roof, true); // chimney
  pen.wall(x - s * 0.9, ground, s * 1.8, s * 1.15, wall);
  pen.roof(x - s * 0.9, ground - s * 1.15, s * 1.8, s * 0.95, s * 0.22, roof);
  pen.door(x - s * 0.35, ground - s * 0.14, s * 0.42, s * 0.5);
  pen.rect(x + s * 0.2, ground - s * 0.82, s * 0.42, s * 0.4, WINDOW, true);
}

function city(pen: Pen, x: number, y: number, s: number, wall: number, roof: number): void {
  const ground = y + s * 0.95;
  pen.shadow(x + s * 0.15, ground, s * 1.9, s * 0.38);
  // The tower stands behind the hall.
  pen.wall(x + s * 0.15, ground, s * 1.15, s * 2.1, wall);
  pen.roof(x + s * 0.15, ground - s * 2.1, s * 1.15, s * 1.0, s * 0.18, roof);
  pen.rect(x + s * 0.52, ground - s * 1.8, s * 0.4, s * 0.45, WINDOW, true);
  pen.rect(x + s * 0.52, ground - s * 1.05, s * 0.4, s * 0.45, WINDOW, true);
  // The hall.
  pen.wall(x - s * 1.5, ground, s * 1.85, s * 1.1, wall);
  pen.roof(x - s * 1.5, ground - s * 1.1, s * 1.85, s * 0.8, s * 0.18, roof);
  pen.door(x - s * 0.95, ground - s * 0.13, s * 0.42, s * 0.5);
  pen.rect(x - s * 0.45, ground - s * 0.8, s * 0.4, s * 0.38, WINDOW, true);
}

function megacity(pen: Pen, x: number, y: number, s: number, wall: number, roof: number): void {
  const ground = y + s * 1.0;
  pen.shadow(x + s * 0.2, ground, s * 2.3, s * 0.45);
  // Two side towers with pointed roofs.
  for (const side of [-1, 1]) {
    const x0 = x + side * s * 1.25 - s * 0.5;
    pen.wall(x0, ground, s, s * 2.0, wall);
    pen.roof(x0, ground - s * 2.0, s, s * 0.95, s * 0.16, roof);
    pen.rect(x0 + s * 0.32, ground - s * 1.7, s * 0.36, s * 0.42, WINDOW, true);
  }
  // The keep, with a gold dome and spire.
  pen.wall(x - s * 0.65, ground, s * 1.3, s * 2.7, shade(wall, 1.12));
  pen.rect(x - s * 0.06, ground - s * 4.05, s * 0.12, s * 0.7, GOLD_DARK);
  pen.circle(x, ground - s * 4.05, s * 0.16, GOLD, GOLD_DARK);
  pen.poly([x - s * 0.75, ground - s * 2.7, x - s * 0.62, ground - s * 3.15, x - s * 0.3, ground - s * 3.45, x, ground - s * 3.55,
            x + s * 0.3, ground - s * 3.45, x + s * 0.62, ground - s * 3.15, x + s * 0.75, ground - s * 2.7], GOLD, GOLD_DARK);
  pen.rect(x - s * 0.2, ground - s * 2.35, s * 0.4, s * 0.5, WINDOW, true);
  pen.rect(x - s * 0.2, ground - s * 1.6, s * 0.4, s * 0.5, WINDOW, true);
  // The curtain wall in front, with battlements and a gate.
  const half = s * 1.95;
  pen.wall(x - half, ground, half * 2, s * 0.95, shade(wall, 0.9));
  const teeth = 7;
  const tw = (half * 2) / (teeth * 2 - 1);
  for (let i = 0; i < teeth; i++) pen.rect(x - half + i * 2 * tw, ground - s * 0.95 - tw * 0.8, tw, tw * 0.8, shade(wall, 0.9), true);
  pen.door(x, ground - s * 0.16, s * 0.55, s * 0.5);
}
