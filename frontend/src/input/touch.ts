// Touch gestures for the board: one finger taps or pans, two fingers pinch-zoom
// and pan together. Pure bookkeeping (no DOM), so it can be tested directly; the
// input controller feeds it pointer events and acts on what it returns.
import type { Pt } from "../board/geometry";

export interface TouchFeel {
  /** A finger that moves less than this (px) and lifts is a tap. */
  tapPx: number;
  /** ...and only if it lifts within this many ms. */
  tapMs: number;
}

export type Gesture =
  | { kind: "none" }
  | { kind: "pan"; dx: number; dy: number }
  | { kind: "pinch"; factor: number; at: Pt; dx: number; dy: number };

interface Finger { start: Pt; at: Pt; t0: number }

const NONE: Gesture = { kind: "none" };

function mid(a: Pt, b: Pt): Pt {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

function gap(a: Pt, b: Pt): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

export class TouchGestures {
  private fingers = new Map<number, Finger>();
  /** Set once the touch can no longer be a tap (moved, a second finger, held too long). */
  private spoiled = false;

  constructor(private feel: TouchFeel) {}

  get active(): number {
    return this.fingers.size;
  }

  down(id: number, p: Pt, t: number): void {
    if (this.fingers.size >= 1) this.spoiled = true;
    if (this.fingers.size >= 2) return;
    this.fingers.set(id, { start: p, at: p, t0: t });
  }

  /** A finger moved: the camera change it asks for. */
  move(id: number, p: Pt): Gesture {
    const f = this.fingers.get(id);
    if (!f) return NONE;
    const others = [...this.fingers.entries()].filter(([k]) => k !== id).map(([, v]) => v);
    const prev = f.at;
    if (!this.spoiled && gap(p, f.start) <= this.feel.tapPx) {
      f.at = p;
      return NONE;
    }
    this.spoiled = true;
    f.at = p;
    const other = others[0];
    if (!other) return { kind: "pan", dx: p.x - prev.x, dy: p.y - prev.y };
    const before = gap(prev, other.at);
    const after = gap(p, other.at);
    const m0 = mid(prev, other.at);
    const m1 = mid(p, other.at);
    return { kind: "pinch", factor: before > 0 ? after / before : 1, at: m1, dx: m1.x - m0.x, dy: m1.y - m0.y };
  }

  /** A finger lifted (or was cancelled): the tap point, if this was a tap. */
  up(id: number, t: number, cancelled = false): Pt | null {
    const f = this.fingers.get(id);
    if (!f) return null;
    this.fingers.delete(id);
    const tap = !cancelled && !this.spoiled && this.fingers.size === 0 && t - f.t0 <= this.feel.tapMs;
    if (this.fingers.size === 0) this.spoiled = false;
    return tap ? f.start : null;
  }

  reset(): void {
    this.fingers.clear();
    this.spoiled = false;
  }
}
