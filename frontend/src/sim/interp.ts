// Client-time interpolation: where settlers are and how far constructions got.
import type { BoardGeometry, Pt } from "../board/geometry";
import { lerp } from "../board/geometry";
import type { ConstructionView, SettlerView } from "../protocol/types";

export function clamp01(t: number): number {
  return t < 0 ? 0 : t > 1 ? 1 : t;
}

/** Where a settler is now, or null when it stands where this player cannot see (Growing sight). */
export function settlerPosition(geo: BoardGeometry, s: SettlerView, now: number): Pt | null {
  if (s.step) {
    const a = geo.vertex[s.step.from_v];
    const b = geo.vertex[s.step.to_v];
    if (!a || !b) return null;
    const span = s.step.t1 - s.step.t0;
    const t = span > 0 ? clamp01((now - s.step.t0) / span) : 1;
    return lerp(a, b, t);
  }
  return geo.vertex[s.vertex] ?? null;
}

export function constructionProgress(c: ConstructionView, now: number): number {
  const span = c.t1 - c.t0;
  return span > 0 ? clamp01((now - c.t0) / span) : 1;
}

/** Milliseconds until the next dice roll (0 when due or unknown). */
export function msUntil(at: number | null, now: number): number {
  return at === null ? 0 : Math.max(0, at - now);
}
