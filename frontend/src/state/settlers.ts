// Settlers variation (stage 3): buying settlers and their gathering numbers, read
// from the game settings the server sent. Mirrors engine/rules/settlers.py.
import type { GameStateView } from "../protocol/types";

type Settings = Record<string, unknown>;

function group(settings: Settings): Record<string, unknown> {
  const g = settings["settlers"];
  return g && typeof g === "object" ? (g as Record<string, unknown>) : {};
}

/** Settlers stay after setup, so players can buy more (engine: leave_after_setup off). */
export function settlersStay(settings: Settings): boolean {
  return group(settings)["leave_after_setup"] === false;
}

function num(settings: Settings, key: string): number {
  const v = group(settings)[key];
  return typeof v === "number" ? v : 0;
}

/** How many settlers ``seat`` may have now: per_settlement per settlement plus per_city
 * per city (megacities too), at least 1, capped by max; both 0 means just max.
 * Mirrors engine/rules/settlers.settler_limit. */
export function settlerLimit(settings: Settings, state: GameStateView | null, seat: number | null): number {
  const cap = num(settings, "max");
  const perSettlement = num(settings, "per_settlement");
  const perCity = num(settings, "per_city");
  if (perSettlement === 0 && perCity === 0) return cap;
  const allowed = (state?.buildings ?? [])
    .filter((b) => b.seat === seat)
    .reduce((n, b) => n + (b.kind === "settlement" ? perSettlement : perCity), 0);
  return Math.min(cap, Math.max(1, allowed));
}

export function gatherOn(settings: Settings): boolean {
  return group(settings)["gather"] === true;
}

/** Numbers of the player's ``index``-th settler (0-based, repeating), or [] when gathering is off. */
export function gatherNumbers(settings: Settings, index: number): number[] {
  const rolls = group(settings)["gather_rolls"];
  if (!gatherOn(settings) || !Array.isArray(rolls) || rolls.length === 0 || index < 0) return [];
  const r = rolls[index % rolls.length];
  return Array.isArray(r) ? r.filter((n): n is number => typeof n === "number") : [];
}

/** Settler id -> its gathering numbers, for ``seat``'s own settlers (ids in ascending order). */
export function ownGatherNumbers(settings: Settings, state: GameStateView | null, seat: number | null): Map<number, number[]> {
  const out = new Map<number, number[]>();
  const p = seat === null ? undefined : state?.players.find((x) => x.seat === seat);
  if (!p) return out;
  [...p.settlers].sort((a, b) => a - b).forEach((id, i) => {
    const nums = gatherNumbers(settings, i);
    if (nums.length) out.set(id, nums);
  });
  return out;
}

/** Why ``seat`` cannot buy a settler now (an error code), or null when it can (cost aside). */
export function buySettlerBlock(settings: Settings, state: GameStateView | null, seat: number | null): string | null {
  const p = seat === null ? undefined : state?.players.find((x) => x.seat === seat);
  if (!p || !settlersStay(settings)) return "settler.not_available";
  if (!p.setup.done) return "settler.setup_not_done";
  if (p.settlers.length >= settlerLimit(settings, state, seat)) return "settler.max";
  if (!state!.buildings.some((b) => b.seat === seat)) return "settler.no_building";
  return null;
}
