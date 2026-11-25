// Game statistics for the HUD: where each player's points come from, the score
// history and what the dice paid. The split mirrors the engine's scoring
// (engine/rules/victory.py, longest_road.py, devcards.py, ages.py); whatever it cannot
// place (victory point cards) is the rest of the player's score.
import type { GameStateView, ResMap } from "../protocol/types";

export type PointSource = "settlement" | "city" | "megacity" | "longest_road" | "largest_army" | "largest_population" | "ages" | "victory_point";
export const POINT_SOURCES: PointSource[] = ["settlement", "city", "megacity", "longest_road", "largest_army", "largest_population", "ages", "victory_point"];

/** One part of a score: ``count`` pieces/awards/cards worth ``points`` together. */
export interface PointPart { source: PointSource; count: number; points: number }

type Settings = Record<string, unknown>;

function num(o: unknown, path: string[], fallback: number): number {
  let cur = o;
  for (const k of path) cur = cur && typeof cur === "object" ? (cur as Record<string, unknown>)[k] : undefined;
  return typeof cur === "number" ? cur : fallback;
}

/** Where ``seat``'s points come from (only the parts worth something). */
export function pointsBreakdown(settings: Settings, state: GameStateView, seat: number): PointPart[] {
  const bp = (kind: string, fallback: number) => num(settings, ["victory", "building_points", kind], fallback);
  const counts = { settlement: 0, city: 0, megacity: 0 };
  for (const b of state.buildings) {
    if (b.seat === seat && b.kind !== "road") counts[b.kind] += 1;
  }
  const parts: PointPart[] = [
    { source: "settlement", count: counts.settlement, points: counts.settlement * bp("settlement", 1) },
    { source: "city", count: counts.city, points: counts.city * bp("city", 2) },
    { source: "megacity", count: counts.megacity, points: counts.megacity * bp("megacity", 3) },
  ];
  if (state.longest_road?.holder === seat) {
    parts.push({ source: "longest_road", count: 1, points: num(settings, ["victory", "longest_road", "points"], 2) });
  }
  if (state.dev_cards?.army === seat) {
    parts.push({ source: "largest_army", count: 1, points: num(settings, ["victory", "largest_army", "points"], 2) });
  }
  if (state.largest_population?.holder === seat) {
    parts.push({ source: "largest_population", count: 1, points: num(settings, ["settlers", "largest_population", "points"], 2) });
  }
  const reached = Object.keys(state.ages?.players?.[String(seat)]?.reached ?? {});
  if (reached.length) {
    const pts = reached.reduce((a, age) => a + num(settings, ["ages", `age${age}`, "bonus", "points"], 0), 0);
    parts.push({ source: "ages", count: reached.length, points: pts });
  }
  const total = state.players.find((p) => p.seat === seat)?.points;
  if (total !== undefined) {
    const rest = total - parts.reduce((a, p) => a + p.points, 0);
    const per = num(settings, ["dev_cards", "victory_point_points"], 1) || 1;
    if (rest > 0) parts.push({ source: "victory_point", count: Math.max(1, Math.round(rest / per)), points: rest });
  }
  return parts.filter((p) => p.points > 0);
}

/** A player's score history as [game ms, points], ending at ``until`` with the current score. */
export function scoreLine(state: GameStateView, seat: number, until: number): [number, number][] {
  const line = [...(state.stats?.timeline[String(seat)] ?? [])];
  const points = state.players.find((p) => p.seat === seat)?.points;
  if (points === undefined && !line.length) return [];
  if (!line.length) line.push([0, 0]);
  const last = line[line.length - 1]!;
  const now = points ?? last[1];
  if (now !== last[1]) line.push([Math.max(until, last[0]), now]);
  else if (until > last[0]) line.push([until, now]);
  return line;
}

/** SVG path of a step line (the score holds until the next change). */
export function stepPath(line: [number, number][], x: (t: number) => number, y: (p: number) => number): string {
  if (!line.length) return "";
  let d = `M${x(line[0]![0]).toFixed(1)},${y(line[0]![1]).toFixed(1)}`;
  for (let i = 1; i < line.length; i++) {
    const [t, p] = line[i]!;
    d += `H${x(t).toFixed(1)}V${y(p).toFixed(1)}`;
  }
  return d;
}

export function producedTotal(m: ResMap | undefined): number {
  return Object.values(m ?? {}).reduce((a, n) => a + (n ?? 0), 0);
}

/** "12:05" for game milliseconds. */
export function clockText(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** When ``seat`` reached each age after the first, as [age, game ms], oldest first (empty with ages off). */
export function ageMarks(state: GameStateView, seat: number): [number, number][] {
  const reached = state.ages?.players?.[String(seat)]?.reached ?? {};
  return Object.entries(reached)
    .map(([age, at]): [number, number] => [Number(age), at])
    .filter(([age, at]) => age > 1 && Number.isFinite(at))
    .sort((a, b) => a[1] - b[1] || a[0] - b[0]);
}

/** The score of a step line at ``ms`` (the last change at or before it). */
export function scoreAt(line: [number, number][], ms: number): number {
  let points = line[0]?.[1] ?? 0;
  for (const [t, p] of line) {
    if (t > ms) break;
    points = p;
  }
  return points;
}
