// Small inline icons for the HUD: one per resource, and dice faces with pips.
import type { JSX } from "preact";

import type { Resource } from "../protocol/types";

const RES_PATHS: Record<Resource, JSX.Element> = {
  lumber: (
    <>
      <path d="M12 2 5 12h4l-3 5h12l-3-5h4z" fill="currentColor" />
      <rect x="10.5" y="17" width="3" height="5" rx="1" fill="currentColor" opacity="0.7" />
    </>
  ),
  brick: (
    <>
      <rect x="2" y="13" width="9" height="5" rx="1" fill="currentColor" />
      <rect x="13" y="13" width="9" height="5" rx="1" fill="currentColor" />
      <rect x="7.5" y="7" width="9" height="5" rx="1" fill="currentColor" opacity="0.8" />
    </>
  ),
  wool: (
    <>
      <path d="M8 9a3 3 0 0 1 5-1.5A3 3 0 0 1 18 10a3 3 0 0 1-1 5.5H8A3 3 0 0 1 8 9z" fill="currentColor" />
      <ellipse cx="5" cy="11" rx="2.6" ry="2.1" fill="currentColor" opacity="0.75" />
      <path d="M9 15.5v3.5M15 15.5v3.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" opacity="0.75" />
    </>
  ),
  grain: (
    <>
      <path d="M12 22V8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
      {[5, 9, 13].map((y) => (
        <g key={y}>
          <ellipse cx="9.3" cy={y + 1} rx="1.8" ry="3" transform={`rotate(-30 9.3 ${y + 1})`} fill="currentColor" />
          <ellipse cx="14.7" cy={y + 1} rx="1.8" ry="3" transform={`rotate(30 14.7 ${y + 1})`} fill="currentColor" />
        </g>
      ))}
      <ellipse cx="12" cy="4" rx="1.6" ry="2.6" fill="currentColor" />
    </>
  ),
  ore: (
    <>
      <path d="M3 19 8 9l4 3 3-6 6 13z" fill="currentColor" />
      <path d="m8 9 1.6 4L12 12M15 6l1 5" stroke="#fff" stroke-width="1.2" fill="none" opacity="0.5" />
    </>
  ),
  fish: (
    <>
      <path d="M3 12c3-5 9-6 13-3l5-3v12l-5-3c-4 3-10 2-13-3z" fill="currentColor" />
      <circle cx="7.5" cy="11" r="1.2" fill="#fff" opacity="0.8" />
    </>
  ),
};

export function ResIcon({ res, size = 18 }: { res: Resource; size?: number }) {
  return (
    <svg class="res-icon" viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">{RES_PATHS[res]}</svg>
  );
}

/** Pip positions on a 3×3 grid (0..2) for each die face. */
const PIPS: Record<number, [number, number][]> = {
  1: [[1, 1]],
  2: [[0, 0], [2, 2]],
  3: [[0, 0], [1, 1], [2, 2]],
  4: [[0, 0], [2, 0], [0, 2], [2, 2]],
  5: [[0, 0], [2, 0], [1, 1], [0, 2], [2, 2]],
  6: [[0, 0], [2, 0], [0, 1], [2, 1], [0, 2], [2, 2]],
};

export function Die({ value }: { value: number }) {
  const pips = PIPS[value];
  if (!pips) return <span class="die">{value}</span>;
  return (
    <svg class="die" viewBox="0 0 24 24" width="26" height="26" role="img" aria-label={String(value)}>
      <rect x="1" y="1" width="22" height="22" rx="5" class="die-face" />
      {pips.map(([x, y], i) => <circle key={i} cx={6 + x * 6} cy={6 + y * 6} r="2.1" class="die-pip" />)}
    </svg>
  );
}
