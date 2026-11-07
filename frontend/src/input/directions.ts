// Keyboard walking: pick the neighbouring vertex whose on-screen direction best
// matches the held keys (docs/STAGE1_PLAN.md, "Keyboard movement").
import type { Pt } from "../board/geometry";

export type Dir = Pt;

/** Unit-ish screen vector from held direction actions; null when they cancel out. */
export function heldDirection(held: ReadonlySet<string>): Dir | null {
  const x = (held.has("move_right") ? 1 : 0) - (held.has("move_left") ? 1 : 0);
  const y = (held.has("move_down") ? 1 : 0) - (held.has("move_up") ? 1 : 0);
  if (x === 0 && y === 0) return null;
  const len = Math.hypot(x, y);
  return { x: x / len, y: y / len };
}

const TIE = 1e-3;

/**
 * The neighbour whose screen direction is within 90° of ``dir`` and closest to it.
 * When two neighbours are equally good (holding "up" on a vertex whose neighbours
 * go up-left and up-right), ``lean`` (-1 left/up, +1 right/down) picks the side,
 * so alternating ``lean`` walks a straight zigzag. Returns null if no neighbour fits.
 */
export function neighbourToward(
  from: Pt, neighbours: { id: number; at: Pt }[], dir: Dir, lean: number,
): { id: number; side: number } | null {
  let best: { id: number; side: number; score: number } | null = null;
  for (const n of neighbours) {
    const dx = n.at.x - from.x;
    const dy = n.at.y - from.y;
    const len = Math.hypot(dx, dy);
    if (len === 0) continue;
    const score = (dx * dir.x + dy * dir.y) / len;          // cos of the angle
    if (score <= 0) continue;                                // more than 90° off
    // Which side of the key direction the neighbour lies on (cross product sign).
    const side = Math.sign(dir.x * dy - dir.y * dx) || 0;
    if (!best || score > best.score + TIE || (Math.abs(score - best.score) <= TIE && side === lean)) {
      best = { id: n.id, side, score };
    }
  }
  return best && { id: best.id, side: best.side };
}
