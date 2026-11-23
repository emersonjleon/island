// Ages (stage 3, WP26): who is in which age and who is advancing, read from the
// game settings and the ``ages`` part of the state. Mirrors engine/rules/ages.py.
import type { GameEvent, GameStateView, ResMap } from "../protocol/types";

type Settings = Record<string, unknown>;

export interface AgeAdvancing { age: number; t0: number; t1: number }
export interface AgePlayer { age: number; advancing: AgeAdvancing | null; reached: Record<string, number> }
export interface AgesView { players: Record<string, AgePlayer> }

export const LAST_AGE = 3;

function group(settings: Settings): Record<string, unknown> {
  const g = settings["ages"];
  return g && typeof g === "object" ? (g as Record<string, unknown>) : {};
}

export function agesOn(settings: Settings): boolean {
  return group(settings)["enabled"] === true;
}

/** The settings of advancing to ``age`` (2 or 3): cost, needed cities and points, time. */
export function ageStep(settings: Settings, age: number): { cost: ResMap; cities: number; points: number; timeMs: number } | null {
  const s = group(settings)[`age${age}`];
  if (!s || typeof s !== "object") return null;
  const step = s as Record<string, unknown>;
  const req = (step["requires"] ?? {}) as Record<string, unknown>;
  const cost: ResMap = {};
  for (const [r, n] of Object.entries((step["cost"] ?? {}) as Record<string, unknown>)) {
    if (typeof n === "number" && n > 0) cost[r as keyof ResMap] = n;
  }
  const n = (v: unknown) => (typeof v === "number" ? v : 0);
  return { cost, cities: n(req["cities"]), points: n(req["points"]), timeMs: n(step["time_ms"]) };
}

export function agePlayer(state: GameStateView | null, seat: number | null): AgePlayer {
  const p = seat === null ? undefined : state?.ages?.players[String(seat)];
  return p ?? { age: 1, advancing: null, reached: {} };
}

/** Why ``seat`` cannot start the next age now (an error code), or null (cost aside). */
export function advanceBlock(settings: Settings, state: GameStateView | null, seat: number | null): string | null {
  const p = seat === null ? undefined : state?.players.find((x) => x.seat === seat);
  if (!p || !agesOn(settings)) return "age.disabled";
  if (!p.setup.done) return "age.setup_not_done";
  const me = agePlayer(state, seat);
  if (me.advancing) return "age.in_progress";
  if (me.age >= LAST_AGE) return "age.max";
  const step = ageStep(settings, me.age + 1);
  const cities = (state?.buildings ?? []).filter((b) => b.seat === seat && b.kind !== "settlement").length;
  if (step && cities < step.cities) return "age.need_cities";
  if (step && (p.points ?? 0) < step.points) return "age.need_points";
  return null;
}

/** Folds an age event into the state (the server sends these to everyone). */
export function applyAgeEvent(state: GameStateView, ev: GameEvent): void {
  const seat = ev["seat"] as number;
  state.ages ??= { players: {} };
  const p = (state.ages.players[String(seat)] ??= { age: 1, advancing: null, reached: {} });
  if (ev.k === "age_advance_started") {
    p.advancing = { age: ev["age"] as number, t0: ev["t0"] as number, t1: ev["t1"] as number };
  } else if (ev.k === "age_advance_cancelled") {
    p.advancing = null;
  } else if (ev.k === "age_reached") {
    p.age = ev["age"] as number;
    p.advancing = null;
    p.reached[String(p.age)] = ev.at ?? 0;
  }
}
