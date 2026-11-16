// The in-game guide: what a new player should do next. Pure (no DOM), so it is
// unit-tested; Guide.tsx shows the step and the help dialog.
import type { GameStateView } from "../protocol/types";

type Settings = Record<string, unknown>;

/** Tips shown in turn once your setup is done; each stays for ``TIP_ROLLS`` rolls. */
export const TIPS = ["produce", "roads", "settle", "city", "trade", "robber", "cards", "goal"] as const;
export const TIP_ROLLS = 3;

export type GuideStep =
  | { key: "setup_settlement" | "setup_road"; step: number; total: number }
  | { key: "building"; kind: string }
  | { key: "wait_clock" }
  | { key: "tip"; tip: (typeof TIPS)[number]; index: number };

function setupCount(settings: Settings, kind: "settlements" | "roads", fallback: number): number {
  const setup = settings["setup"] as Record<string, unknown> | undefined;
  const v = setup?.[kind];
  return typeof v === "number" ? v : fallback;
}

/** The guide's step for ``seat``, or null when there is nothing to say (spectator, game over). */
export function guideStep(state: GameStateView, seat: number | null, settings: Settings): GuideStep | null {
  if (seat === null || state.phase === "finished") return null;
  const me = state.players.find((p) => p.seat === seat);
  if (!me || me.resigned) return null;
  if (!me.setup.done) {
    const mine = state.constructions.find((c) => c.seat === seat && c.setup);
    if (mine) return { key: "building", kind: mine.kind };
    const left = me.setup.remaining;
    const settlements = left.settlement ?? 0;
    const roads = left.road ?? 0;
    const total = setupCount(settings, "settlements", 2) + setupCount(settings, "roads", 2);
    const step = total - settlements - roads + 1;
    const key = settlements > 0 && roads <= settlements ? "setup_settlement" : "setup_road";
    return { key, step, total };
  }
  if (!state.clock_started) return { key: "wait_clock" };
  const index = Math.floor(state.dice_history.length / TIP_ROLLS) % TIPS.length;
  return { key: "tip", tip: TIPS[index]!, index };
}
